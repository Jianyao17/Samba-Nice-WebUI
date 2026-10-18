import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.models import BackupSnapshot


class BackupManager:
    """
    Manages versioned snapshots and rollbacks for Samba configuration files.

    Maintains a rolling directory of timestamped backups prior to any share creation,
    modification, or deletion. Enables safe single-click rollback of configuration states.
    """

    def __init__(self, backup_dir: Path, include_conf_path: Path, main_conf_path: Optional[Path] = None):
        # 1. Initialize directory references and ensure backup storage directory exists
        self.backup_dir = backup_dir
        self.include_conf_path = include_conf_path
        self.main_conf_path = main_conf_path

        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_snapshot(self, description: str = "Automatic backup before change") -> BackupSnapshot:
        # 1. Generate timestamped snapshot directory name with microseconds for uniqueness
        now = datetime.now()
        snapshot_id = now.strftime("snapshot_%Y%m%d_%H%M%S_%f")
        target_dir = self.backup_dir / snapshot_id
        target_dir.mkdir(parents=True, exist_ok=True)

        copied_files: list[str] = []

        # 2. Copy dedicated include configuration file
        if self.include_conf_path.exists():
            dest = target_dir / self.include_conf_path.name
            shutil.copy2(self.include_conf_path, dest)
            copied_files.append(self.include_conf_path.name)

        # 3. Copy main smb.conf file if it exists
        if self.main_conf_path and self.main_conf_path.exists():
            dest_main = target_dir / self.main_conf_path.name
            shutil.copy2(self.main_conf_path, dest_main)
            copied_files.append(self.main_conf_path.name)

        # 4. Save metadata descriptor JSON file
        snapshot = BackupSnapshot(
            snapshot_id=snapshot_id,
            created_at=now,
            description=description,
            files=copied_files
        )

        metadata_file = target_dir / "metadata.json"
        metadata_file.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")

        return snapshot

    def list_snapshots(self) -> list[BackupSnapshot]:
        # 1. Scan backup root for valid snapshot subdirectories
        snapshots: list[BackupSnapshot] = []

        for item in sorted(self.backup_dir.iterdir(), reverse=True):
            if item.is_dir() and item.name.startswith("snapshot_"):
                metadata_path = item / "metadata.json"

                if metadata_path.exists():
                    try:
                        data = json.loads(metadata_path.read_text(encoding="utf-8"))
                        snapshots.append(BackupSnapshot(**data))
                    except (json.JSONDecodeError, Exception):
                        continue

        # 2. Return snapshots sorted newest first
        return snapshots

    def restore_snapshot(self, snapshot_id: str) -> bool:
        # 1. Locate and validate snapshot directory
        target_dir = self.backup_dir / snapshot_id
        if not target_dir.exists() or not target_dir.is_dir():
            return False

        # 2. Restore dedicated include configuration file
        source_include = target_dir / self.include_conf_path.name
        if source_include.exists():
            self.include_conf_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_include, self.include_conf_path)

        # 3. Restore main smb.conf if present in the snapshot
        if self.main_conf_path:
            source_main = target_dir / self.main_conf_path.name
            if source_main.exists():
                shutil.copy2(source_main, self.main_conf_path)

        return True

    def delete_snapshot(self, snapshot_id: str) -> bool:
        # 1. Safely remove snapshot directory
        target_dir = self.backup_dir / snapshot_id
        if target_dir.exists() and target_dir.is_dir():
            shutil.rmtree(target_dir)
            return True

        return False
