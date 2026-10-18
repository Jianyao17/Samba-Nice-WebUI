from pathlib import Path
import pytest

from src.core.security import (
    ensure_safe_storage_path,
    generate_session_token,
    is_path_safe,
    verify_credentials,
)


def test_is_path_safe(temp_workspace):
    storage_root = temp_workspace["storage_root"]
    allowed_roots = [storage_root]

    # 1. Valid child path
    valid_child = storage_root / "documents" / "photos"
    valid_child.mkdir(parents=True, exist_ok=True)
    assert is_path_safe(valid_child, allowed_roots) is True

    # 2. Path equal to storage root
    assert is_path_safe(storage_root, allowed_roots) is True

    # 3. Path outside storage root (e.g. workspace root or /etc)
    outside_path = temp_workspace["root"]
    assert is_path_safe(outside_path, allowed_roots) is False

    # 4. Traversal attempt using ../
    traversal_path = storage_root / ".." / "etc_samba"
    assert is_path_safe(traversal_path, allowed_roots) is False


def test_ensure_safe_storage_path(temp_workspace):
    storage_root = str(temp_workspace["storage_root"])
    allowed = [storage_root]

    # 1. Valid path succeeds
    safe = ensure_safe_storage_path(f"{storage_root}/folder1", allowed)
    assert safe.is_relative_to(Path(storage_root).resolve())

    # 2. Invalid path raises PermissionError
    with pytest.raises(PermissionError):
        ensure_safe_storage_path(f"{storage_root}/../../sensitive_data", allowed)


def test_verify_credentials():
    from src.config import settings

    # 1. Match configured credentials from settings
    assert verify_credentials(settings.webui_admin_user, settings.webui_admin_password) is True

    # 2. Reject incorrect username or password
    assert verify_credentials(settings.webui_admin_user, "definitely_wrong_password") is False
    assert verify_credentials("wrong_user", settings.webui_admin_password) is False


def test_generate_session_token():
    token1 = generate_session_token()
    token2 = generate_session_token()

    assert len(token1) > 20
    assert token1 != token2
