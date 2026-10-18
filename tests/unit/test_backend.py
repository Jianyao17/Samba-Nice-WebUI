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
