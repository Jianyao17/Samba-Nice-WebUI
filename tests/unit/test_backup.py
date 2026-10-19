import hashlib
import json
import re

from src.core.models import ShareConfig
from src.samba.parser import parse_conf_file, serialize_all_shares


def _write_share(include_conf, name: str = "share1") -> None:
    share = ShareConfig(name=name, path=f"/storage/{name}")
    include_conf.write_text(serialize_all_shares([share]), encoding="utf-8")


def _ids(backup_mgr) -> list[str]:
    return [snapshot.snapshot_id for snapshot in backup_mgr.list_snapshots()]


def test_snapshot_id_metadata_and_hash(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]
    _write_share(include_conf, "share1")

    result = backup_mgr.create_snapshot("Initial configuration")
    assert result.created is True
    snapshot = result.snapshot
    assert snapshot is not None
    assert re.fullmatch(r"snapshot_\d{8}T\d{6}_[0-9a-f]{8}", snapshot.snapshot_id)
    assert snapshot.file_hash == hashlib.sha256(include_conf.read_bytes()).hexdigest()
    assert snapshot.files == [include_conf.name]


def test_duplicate_content_is_not_snapshotted(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]
    _write_share(include_conf, "share1")

    # 1. First entry is created
    first = backup_mgr.create_snapshot("Initial configuration")
    assert first.created is True
    assert first.snapshot is not None
    snapshot_count = len(backup_mgr.list_snapshots())

    # 2. Creating another entry without changing the file is skipped
    second = backup_mgr.create_snapshot("Duplicate")
    assert second.created is False
    assert second.snapshot is not None
    assert second.snapshot.snapshot_id == first.snapshot.snapshot_id
    assert len(backup_mgr.list_snapshots()) == snapshot_count


def test_metadata_is_minimal(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]
    _write_share(include_conf, "share1")

    result = backup_mgr.create_snapshot("Metadata test")
    assert result.snapshot is not None

    snapshot_dir = temp_workspace["backup_dir"] / result.snapshot.snapshot_id
    metadata = json.loads((snapshot_dir / "metadata.json").read_text(encoding="utf-8"))

    assert set(metadata.keys()) == {
        "snapshot_id",
        "created_at",
        "description",
        "files",
        "file_hash",
    }
    assert metadata["file_hash"] == result.snapshot.file_hash


def test_previous_diff(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]

    _write_share(include_conf, "share1")
    first = backup_mgr.create_snapshot("Initial configuration")
    assert first.snapshot is not None

    _write_share(include_conf, "share2")
    second = backup_mgr.create_snapshot("Saved share2")
    assert second.snapshot is not None

    diff = backup_mgr.get_previous_diff(second.snapshot.snapshot_id)
    assert diff is not None
    assert diff.added == ["share2"]
    assert diff.removed == ["share1"]


def test_undo_latest_restores_previous_state(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]

    _write_share(include_conf, "share1")
    first = backup_mgr.create_snapshot("Initial configuration")
    assert first.snapshot is not None

    _write_share(include_conf, "share2")
    second = backup_mgr.create_snapshot("Saved share2")
    assert second.snapshot is not None

    snapshot_count = len(backup_mgr.list_snapshots())
    assert backup_mgr.undo_change(second.snapshot.snapshot_id) is True

    assert [share.name for share in parse_conf_file(include_conf)] == ["share1"]
    assert len(backup_mgr.list_snapshots()) == snapshot_count - 1
    assert _ids(backup_mgr) == [first.snapshot.snapshot_id]


def test_undo_older_removes_target_and_newer(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]

    _write_share(include_conf, "share1")
    first = backup_mgr.create_snapshot("Initial configuration")
    assert first.snapshot is not None

    _write_share(include_conf, "share2")
    second = backup_mgr.create_snapshot("Saved share2")
    assert second.snapshot is not None

    _write_share(include_conf, "share3")
    third = backup_mgr.create_snapshot("Saved share3")
    assert third.snapshot is not None

    # Undo the middle change: it and the newer entry disappear
    assert backup_mgr.undo_change(second.snapshot.snapshot_id) is True

    assert [share.name for share in parse_conf_file(include_conf)] == ["share1"]
    assert _ids(backup_mgr) == [first.snapshot.snapshot_id]


def test_undo_oldest_returns_false(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]
    _write_share(include_conf, "share1")

    first = backup_mgr.create_snapshot("Initial configuration")
    assert first.snapshot is not None

    assert backup_mgr.undo_change(first.snapshot.snapshot_id) is False
    assert _ids(backup_mgr) == [first.snapshot.snapshot_id]


def test_undo_diff_previews_restoration(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]

    _write_share(include_conf, "share1")
    first = backup_mgr.create_snapshot("Initial configuration")
    assert first.snapshot is not None

    _write_share(include_conf, "share2")
    second = backup_mgr.create_snapshot("Saved share2")
    assert second.snapshot is not None

    diff = backup_mgr.get_undo_diff(second.snapshot.snapshot_id)
    assert diff is not None
    assert diff.added == ["share1"]
    assert diff.removed == ["share2"]


def test_undo_rejects_tampered_previous(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]

    _write_share(include_conf, "share1")
    first = backup_mgr.create_snapshot("Initial configuration")
    assert first.snapshot is not None

    _write_share(include_conf, "share2")
    second = backup_mgr.create_snapshot("Saved share2")
    assert second.snapshot is not None

    # 1. Tamper with the previous state that undo needs
    stored_file = (
        temp_workspace["backup_dir"] / first.snapshot.snapshot_id / include_conf.name
    )
    stored_file.write_text(
        serialize_all_shares([ShareConfig(name="tampered", path="/storage/tampered")]),
        encoding="utf-8",
    )

    # 2. Undo fails, the active configuration and history stay untouched
    assert backup_mgr.undo_change(second.snapshot.snapshot_id) is False
    assert [share.name for share in parse_conf_file(include_conf)] == ["share2"]
    assert set(_ids(backup_mgr)) == {
        first.snapshot.snapshot_id,
        second.snapshot.snapshot_id,
    }


def test_has_unrecorded_changes(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]

    _write_share(include_conf, "share1")
    first = backup_mgr.create_snapshot("Initial configuration")
    assert first.snapshot is not None
    assert backup_mgr.has_unrecorded_changes() is False

    _write_share(include_conf, "share2")
    assert backup_mgr.has_unrecorded_changes() is True

    backup_mgr.create_snapshot("Manual configuration change")
    assert backup_mgr.has_unrecorded_changes() is False


def test_invalid_snapshot_id_rejected(backup_mgr):
    assert backup_mgr.undo_change("../outside") is False
    assert backup_mgr.undo_change("/tmp/outside") is False


def test_legacy_snapshot_can_be_used_as_previous(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]
    legacy_id = "snapshot_20260101_120000_000000"
    legacy_dir = temp_workspace["backup_dir"] / legacy_id
    legacy_dir.mkdir(parents=True)

    # 1. Create a legacy entry without file_hash metadata
    legacy_content = serialize_all_shares(
        [ShareConfig(name="legacy", path="/storage/legacy")]
    )
    (legacy_dir / include_conf.name).write_text(legacy_content, encoding="utf-8")
    (legacy_dir / "metadata.json").write_text(
        json.dumps(
            {
                "snapshot_id": legacy_id,
                "created_at": "2026-01-01T12:00:00",
                "description": "Legacy configuration",
                "files": [include_conf.name],
            }
        ),
        encoding="utf-8",
    )

    # 2. Add a newer entry, then undo it back to the legacy state
    _write_share(include_conf, "current")
    current = backup_mgr.create_snapshot("Saved current")
    assert current.snapshot is not None

    assert backup_mgr.undo_change(current.snapshot.snapshot_id) is True
    assert [share.name for share in parse_conf_file(include_conf)] == ["legacy"]
    assert _ids(backup_mgr) == [legacy_id]
