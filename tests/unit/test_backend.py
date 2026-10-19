from src.core.models import ShareConfig


def test_backend_crud_lifecycle(mock_backend):
    # 1. Verify initial status
    status = mock_backend.get_status()
    assert status.is_running is True

    # 2. Add new share
    new_share = ShareConfig(
        name="finance",
        path="/storage/finance",
        comment="Finance records",
        read_only=True,
        browsable=True,
        guest_ok=False
    )
    result = mock_backend.save_share(new_share)
    assert result.is_valid is True

    # 3. Retrieve share
    saved = mock_backend.get_share("finance")
    assert saved is not None
    assert saved.name == "finance"
    assert saved.path == "/storage/finance"
    assert saved.read_only is True

    # 4. List all shares
    shares = mock_backend.list_shares()
    names = [s.name for s in shares]
    assert "finance" in names

    # 5. Delete share
    deleted = mock_backend.delete_share("finance")
    assert deleted is True

    assert mock_backend.get_share("finance") is None


def test_delete_records_history_entry(mock_backend, backup_mgr):
    # 1. Delete the seeded share and verify a new history entry is recorded
    previous_ids = {snapshot.snapshot_id for snapshot in backup_mgr.list_snapshots()}
    assert mock_backend.delete_share("public") is True

    snapshots = backup_mgr.list_snapshots()
    new_snapshots = [s for s in snapshots if s.snapshot_id not in previous_ids]

    assert new_snapshots
    assert snapshots[0].description == "Deleted share 'public'"


def test_undo_deleted_share_restores_it(mock_backend, backup_mgr):
    # 1. Delete the seeded share
    assert mock_backend.delete_share("public") is True
    deletion_entry = backup_mgr.list_snapshots()[0]
    assert deletion_entry.description == "Deleted share 'public'"

    # 2. Undo the deletion: share returns and the deletion entry disappears
    snapshot_count = len(backup_mgr.list_snapshots())
    assert backup_mgr.undo_change(deletion_entry.snapshot_id) is True
    assert mock_backend.get_share("public") is not None
    assert len(backup_mgr.list_snapshots()) == snapshot_count - 1
    assert deletion_entry.snapshot_id not in {
        snapshot.snapshot_id for snapshot in backup_mgr.list_snapshots()
    }
