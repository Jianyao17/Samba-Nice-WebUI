import hashlib
import json
import logging
import os
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.config_diff import ShareDiff, diff_contents
from src.core.models import BackupSnapshot

logger = logging.getLogger(__name__)

_METADATA = "metadata.json"
_ID_PATTERN = re.compile(
    r"^(?:snapshot_\d{8}T\d{6}_[0-9a-f]{8}(?:_\d+)?|snapshot_\d{8}_\d{6}_\d{6})$"
)


@dataclass
class SnapshotResult:
    snapshot: BackupSnapshot | None
    created: bool
    message: str


class BackupManager:
    """
    Linear, hash-deduplicated history of the managed Samba include file.

    Each entry represents the configuration after a successful change. Undoing
    an entry restores the state before that change and removes the entry plus
    all newer entries, keeping the timeline linear and easy to follow.
    """

    def __init__(self, backup_dir: Path, include_conf_path: Path):
        self.backup_dir = backup_dir
        self.include_conf_path = include_conf_path
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Snapshot lifecycle
    # ------------------------------------------------------------------

    def create_snapshot(self, description: str = "Automatic snapshot") -> SnapshotResult:
        """Capture the current include file unless it matches the newest snapshot."""
        with self._lock:
            try:
                data = self.include_conf_path.read_bytes()
            except FileNotFoundError:
                return SnapshotResult(None, False, "No configuration file to back up.")

            file_hash = hashlib.sha256(data).hexdigest()

            # 1. Skip duplicate content compared with the newest snapshot
            snapshots = self.list_snapshots()
            if snapshots and self._file_hash(snapshots[0]) == file_hash:
                newest = snapshots[0]
                return SnapshotResult(
                    newest,
                    False,
                    f"No changes; identical to snapshot '{newest.snapshot_id}'.",
                )

            # 2. Build a local-time ID with the short file hash
            now = datetime.now()
            snapshot_id = f"snapshot_{now:%Y%m%dT%H%M%S}_{file_hash[:8]}"
            target = self.backup_dir / snapshot_id
            suffix = 1
            while target.exists():
                target = self.backup_dir / f"{snapshot_id}_{suffix}"
                suffix += 1

            snapshot = BackupSnapshot(
                snapshot_id=target.name,
                created_at=now,
                description=description,
                files=[self.include_conf_path.name],
                file_hash=file_hash,
            )

            # 3. Write the config and metadata; clean up on failure
            try:
                target.mkdir()
                (target / self.include_conf_path.name).write_bytes(data)
                (target / _METADATA).write_text(
                    snapshot.model_dump_json(indent=2), encoding="utf-8"
                )
            except OSError:
                logger.exception("Failed to create snapshot '%s'", snapshot.snapshot_id)
                shutil.rmtree(target, ignore_errors=True)
                raise

            return SnapshotResult(
                snapshot,
                True,
                f"Snapshot '{snapshot.snapshot_id}' created.",
            )

    def list_snapshots(self) -> list[BackupSnapshot]:
        """Return readable snapshots, newest first."""
        try:
            entries = list(self.backup_dir.iterdir())
        except OSError:
            logger.exception("Failed to scan backup directory '%s'", self.backup_dir)
            return []

        snapshots: list[BackupSnapshot] = []
        for item in entries:
            if item.is_symlink() or not item.is_dir() or not _ID_PATTERN.fullmatch(item.name):
                continue
            snapshot = self._load_snapshot(item)
            if snapshot is not None:
                snapshots.append(snapshot)

        snapshots.sort(
            key=lambda s: (s.created_at.timestamp(), s.snapshot_id), reverse=True
        )
        return snapshots

    def undo_change(self, snapshot_id: str) -> bool:
        """Restore the state before a change and remove that change plus newer entries."""
        with self._lock:
            snapshots = self.list_snapshots()
            index = next(
                (i for i, snapshot in enumerate(snapshots) if snapshot.snapshot_id == snapshot_id),
                None,
            )
            if index is None or index + 1 >= len(snapshots):
                return False

            # 1. Restore the state before the selected change
            previous = snapshots[index + 1]
            if not self._restore_state(previous):
                return False

            # 2. Trim the timeline: selected entry and every newer entry
            for snapshot in snapshots[: index + 1]:
                self._remove_snapshot(snapshot.snapshot_id)

            return True

    def has_unrecorded_changes(self) -> bool:
        """Return True when the active file no longer matches the newest entry."""
        snapshots = self.list_snapshots()
        if not snapshots or not self.include_conf_path.is_file():
            return False

        latest_hash = self._file_hash(snapshots[0])
        if not latest_hash:
            return False

        try:
            current_hash = hashlib.sha256(self.include_conf_path.read_bytes()).hexdigest()
        except OSError:
            return False

        return current_hash != latest_hash

    # ------------------------------------------------------------------
    # On-demand diffs
    # ------------------------------------------------------------------

    def get_previous_diff(self, snapshot_id: str) -> ShareDiff | None:
        """Compare a snapshot with the snapshot immediately before it."""
        snapshots = self.list_snapshots()
        index = next(
            (i for i, snapshot in enumerate(snapshots) if snapshot.snapshot_id == snapshot_id),
            None,
        )
        if index is None:
            return None

        target = self._snapshot_text(snapshots[index])
        if target is None:
            return None

        if index + 1 >= len(snapshots):
            return diff_contents(None, target)

        previous = self._snapshot_text(snapshots[index + 1])
        return diff_contents(previous, target) if previous is not None else None

    def get_undo_diff(self, snapshot_id: str) -> ShareDiff | None:
        """Preview the changes that undo would apply to the active configuration."""
        snapshots = self.list_snapshots()
        index = next(
            (i for i, snapshot in enumerate(snapshots) if snapshot.snapshot_id == snapshot_id),
            None,
        )
        if index is None or index + 1 >= len(snapshots):
            return None

        previous_text = self._snapshot_text(snapshots[index + 1])
        if previous_text is None:
            return None

        try:
            current = (
                self.include_conf_path.read_text(encoding="utf-8", errors="replace")
                if self.include_conf_path.is_file()
                else None
            )
        except OSError:
            return None

        return diff_contents(current, previous_text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _restore_state(self, snapshot: BackupSnapshot) -> bool:
        source = self._snapshot_file(snapshot)
        if source is None:
            return False

        try:
            data = source.read_bytes()
        except OSError:
            logger.exception("Failed to read snapshot '%s'", snapshot.snapshot_id)
            return False

        if snapshot.file_hash and hashlib.sha256(data).hexdigest() != snapshot.file_hash:
            logger.warning("Integrity check failed for snapshot '%s'", snapshot.snapshot_id)
            return False

        temp = self.include_conf_path.with_name(
            f".{self.include_conf_path.name}.restore.tmp"
        )
        try:
            self.include_conf_path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(data)
            os.replace(temp, self.include_conf_path)
        except OSError:
            logger.exception("Failed to restore snapshot '%s'", snapshot.snapshot_id)
            return False

        return True

    def _remove_snapshot(self, snapshot_id: str) -> bool:
        directory = self._snapshot_dir(snapshot_id)
        if directory is None or not directory.is_dir():
            return False
        try:
            shutil.rmtree(directory)
            return True
        except OSError:
            logger.exception("Failed to remove snapshot '%s'", snapshot_id)
            return False

    def _load_snapshot(self, directory: Path) -> BackupSnapshot | None:
        try:
            data = json.loads((directory / _METADATA).read_text(encoding="utf-8"))
            snapshot = BackupSnapshot(**data)
        except (OSError, ValueError, TypeError):
            logger.warning("Skipping unreadable snapshot '%s'", directory.name)
            return None

        return snapshot if snapshot.snapshot_id == directory.name else None

    def _snapshot_dir(self, snapshot_id: str) -> Path | None:
        if not _ID_PATTERN.fullmatch(snapshot_id):
            return None
        candidate = (self.backup_dir / snapshot_id).resolve()
        return candidate if candidate.parent == self.backup_dir.resolve() else None

    def _snapshot_file(self, snapshot: BackupSnapshot) -> Path | None:
        directory = self._snapshot_dir(snapshot.snapshot_id)
        if directory is None:
            return None

        for name in [self.include_conf_path.name, *snapshot.files]:
            if Path(name).name != name:
                continue
            path = directory / name
            if path.is_file():
                return path
        return None

    def _file_hash(self, snapshot: BackupSnapshot) -> str:
        if snapshot.file_hash:
            return snapshot.file_hash
        path = self._snapshot_file(snapshot)
        if path is None:
            return ""
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return ""

    def _snapshot_text(self, snapshot: BackupSnapshot) -> str | None:
        path = self._snapshot_file(snapshot)
        if path is None:
            return None
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
