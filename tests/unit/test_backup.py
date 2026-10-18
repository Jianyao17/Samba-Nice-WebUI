from src.core.models import ShareConfig
from src.samba.parser import parse_conf_file, serialize_all_shares


def test_create_and_restore_backup(backup_mgr, temp_workspace):
    include_conf = temp_workspace["include_conf_path"]

    # 1. Create initial share in dedicated include file
    share1 = ShareConfig(name="share1", path="/storage/share1")
    include_conf.write_text(serialize_all_shares([share1]), encoding="utf-8")

    # 2. Capture initial snapshot
    snapshot1 = backup_mgr.create_snapshot("Initial state with share1")
    assert snapshot1.snapshot_id.startswith("snapshot_")
    assert len(snapshot1.files) >= 1

    # 3. Modify configuration to share2
    share2 = ShareConfig(name="share2", path="/storage/share2")
    include_conf.write_text(serialize_all_shares([share2]), encoding="utf-8")

    shares_modified = parse_conf_file(include_conf)
    assert len(shares_modified) == 1
    assert shares_modified[0].name == "share2"

    # 4. Restore initial snapshot
    restore_success = backup_mgr.restore_snapshot(snapshot1.snapshot_id)
    assert restore_success is True

    # 5. Verify share1 is restored and share2 is reverted
    shares_restored = parse_conf_file(include_conf)
    assert len(shares_restored) == 1
    assert shares_restored[0].name == "share1"


def test_list_and_delete_snapshots(backup_mgr):
    # 1. Create multiple snapshots
    snap1 = backup_mgr.create_snapshot("Snapshot 1")
    snap2 = backup_mgr.create_snapshot("Snapshot 2")

    # 2. List snapshots
    snapshots = backup_mgr.list_snapshots()
    assert len(snapshots) >= 2
    snapshot_ids = [s.snapshot_id for s in snapshots]
    assert snap1.snapshot_id in snapshot_ids
    assert snap2.snapshot_id in snapshot_ids

    # 3. Delete snapshot
    deleted = backup_mgr.delete_snapshot(snap1.snapshot_id)
    assert deleted is True

    updated_snapshots = backup_mgr.list_snapshots()
    assert snap1.snapshot_id not in [s.snapshot_id for s in updated_snapshots]
