import pytest

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


def test_create_rejects_duplicate_name(mock_backend, backup_mgr):
    # 1. The seeded 'public' share must not be overwritten by a new create
    before = {share.name: share for share in mock_backend.list_shares()}
    snapshot_count = len(backup_mgr.list_snapshots())

    result = mock_backend.save_share(
        ShareConfig(name="public", path="/storage/other", comment="Duplicate")
    )

    assert result.is_valid is False
    assert "already exists" in result.message
    after = {share.name: share for share in mock_backend.list_shares()}
    assert after["public"].path == before["public"].path
    assert len(backup_mgr.list_snapshots()) == snapshot_count


def test_create_rejects_duplicate_name_case_insensitive(mock_backend):
    # 1. Samba section names are treated case-insensitively
    result = mock_backend.save_share(
        ShareConfig(name="Public", path="/storage/other")
    )

    assert result.is_valid is False
    assert mock_backend.get_share("public") is not None
    assert [share.name for share in mock_backend.list_shares()].count("Public") == 0


def test_update_with_original_name_keeps_single_entry(mock_backend):
    # 1. Create a share, then update its fields through original_name
    assert mock_backend.save_share(
        ShareConfig(name="finance", path="/storage/finance", comment="Old")
    ).is_valid

    result = mock_backend.save_share(
        ShareConfig(name="finance", path="/storage/finance", comment="Updated"),
        original_name="finance",
    )

    assert result.is_valid is True
    shares = [share for share in mock_backend.list_shares() if share.name == "finance"]
    assert len(shares) == 1
    assert shares[0].comment == "Updated"


def test_rename_share_preserves_configuration(mock_backend):
    # 1. Create a share with non-default fields and custom options
    original = ShareConfig(
        name="finance",
        path="/storage/finance",
        comment="Finance records",
        read_only=True,
        valid_users="alice",
    )
    assert mock_backend.save_share(original).is_valid

    # 2. Rename it while preserving the path and advanced options
    renamed = ShareConfig(
        name="finance_2026",
        path="/storage/finance",
        comment="Finance records 2026",
        read_only=True,
        valid_users="alice",
        extra_options={"veto files": "/tmp/*"},
    )
    result = mock_backend.save_share(renamed, original_name="finance")

    assert result.is_valid is True
    assert mock_backend.get_share("finance") is None
    saved = mock_backend.get_share("finance_2026")
    assert saved is not None
    assert saved.path == "/storage/finance"
    assert saved.comment == "Finance records 2026"
    assert saved.read_only is True
    assert saved.valid_users == "alice"
    assert saved.extra_options == {"veto files": "/tmp/*"}
    assert mock_backend.get_share("public") is not None


def test_rename_records_rename_history_entry(mock_backend, backup_mgr):
    # 1. Create and rename a share, then inspect the newest history entry
    assert mock_backend.save_share(
        ShareConfig(name="finance", path="/storage/finance")
    ).is_valid
    assert mock_backend.save_share(
        ShareConfig(name="finance_2026", path="/storage/finance"),
        original_name="finance",
    ).is_valid

    assert backup_mgr.list_snapshots()[0].description == (
        "Renamed share 'finance' to 'finance_2026'"
    )


def test_rename_rejects_collision_with_another_share(mock_backend):
    # 1. Prepare two shares, then try to rename one onto the other's name
    assert mock_backend.save_share(
        ShareConfig(name="alpha", path="/storage/alpha")
    ).is_valid
    assert mock_backend.save_share(
        ShareConfig(name="beta", path="/storage/beta")
    ).is_valid

    result = mock_backend.save_share(
        ShareConfig(name="beta", path="/storage/alpha"),
        original_name="alpha",
    )

    assert result.is_valid is False
    assert "already exists" in result.message
    assert mock_backend.get_share("alpha") is not None
    assert mock_backend.get_share("beta") is not None


def test_update_unknown_original_name_fails(mock_backend):
    # 1. A stale edit dialog must not silently create a new share
    result = mock_backend.save_share(
        ShareConfig(name="ghost", path="/storage/ghost"),
        original_name="missing",
    )

    assert result.is_valid is False
    assert "no longer exists" in result.message
    assert mock_backend.get_share("ghost") is None


@pytest.mark.parametrize("invalid_name", ["global", "homes", "printers", "   "])
def test_rejects_invalid_or_reserved_share_names(mock_backend, backup_mgr, invalid_name):
    # 1. Invalid names return a validation result instead of raising
    snapshot_count = len(backup_mgr.list_snapshots())
    result = mock_backend.save_share(
        ShareConfig(name=invalid_name, path="/storage/invalid")
    )

    assert result.is_valid is False
    assert len(backup_mgr.list_snapshots()) == snapshot_count
