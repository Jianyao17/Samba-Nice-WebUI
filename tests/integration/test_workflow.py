from src.core.models import ShareConfig
from src.core.security import verify_credentials


def test_full_application_workflow(mock_backend, storage_mgr, backup_mgr, temp_workspace):
    from src.config import settings
    storage_root = str(temp_workspace["storage_root"])

    # 1. Verify administrative authentication
    assert verify_credentials(settings.webui_admin_user, settings.webui_admin_password) is True

    # 2. Check initial server status
    status = mock_backend.get_status()
    assert status.is_running is True

    # 3. Create a target storage subfolder
    subfolder = storage_mgr.create_directory(f"{storage_root}/project_docs")
    assert subfolder.exists()

    # 4. Save and configure new Samba share
    new_share = ShareConfig(
        name="project_docs",
        path=str(subfolder),
        comment="Engineering Project Documentation",
        read_only=False,
        browsable=True,
        guest_ok=True,
        conf_file="project_docs.conf"
    )
    val_result = mock_backend.save_share(new_share)
    assert val_result.is_valid is True

    # 5. Verify share appears in active list
    shares = mock_backend.list_shares()
    share_names = [s.name for s in shares]
    assert "project_docs" in share_names

    # 6. Verify automatic snapshot was created during save
    snapshots = backup_mgr.list_snapshots()
    assert len(snapshots) >= 1

    # 7. Saving the exact same configuration again must not duplicate snapshots
    mock_backend.save_share(new_share)
    snapshot_count = len(backup_mgr.list_snapshots())
    mock_backend.save_share(new_share)
    assert len(backup_mgr.list_snapshots()) == snapshot_count

    # 8. Delete share and verify a new history entry is recorded
    snapshot_count = len(backup_mgr.list_snapshots())
    deleted = mock_backend.delete_share("project_docs")
    assert deleted is True
    assert mock_backend.get_share("project_docs") is None
    assert len(backup_mgr.list_snapshots()) == snapshot_count + 1

    deletion_entry = backup_mgr.list_snapshots()[0]
    assert deletion_entry.description == "Deleted share 'project_docs'"

    # 9. Undo the deletion: share returns and the deletion entry is removed
    count_before_undo = len(backup_mgr.list_snapshots())
    assert backup_mgr.undo_change(deletion_entry.snapshot_id) is True
    assert len(backup_mgr.list_snapshots()) == count_before_undo - 1
    mock_backend.reload_service()

    # 10. Verify share is restored after undo
    restored_share = mock_backend.get_share("project_docs")
    assert restored_share is not None
    assert restored_share.name == "project_docs"
