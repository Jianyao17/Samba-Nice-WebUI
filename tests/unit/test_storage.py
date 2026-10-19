from pathlib import Path
import pytest


def test_storage_create_and_list_directory(storage_mgr, temp_workspace):
    storage_root = str(temp_workspace["storage_root"])

    # 1. Create subdirectories safely
    sub1 = storage_mgr.create_directory(f"{storage_root}/subfolder1")
    assert sub1.exists()
    assert sub1.is_dir()

    # 2. Check path existence
    assert storage_mgr.check_path_exists(f"{storage_root}/subfolder1") is True
    assert storage_mgr.check_path_exists(f"{storage_root}/non_existent") is False

    # 3. List directory contents
    items = storage_mgr.list_directory(storage_root)
    item_names = [i["name"] for i in items]
    assert "subfolder1" in item_names

    # 4. Traversal creation is strictly blocked
    with pytest.raises(PermissionError):
        storage_mgr.create_directory(f"{storage_root}/../unauthorized_dir")

    # 5. Nested subfolder listing
    sub2 = storage_mgr.create_directory(f"{storage_root}/subfolder1/nested")
    nested_items = storage_mgr.list_directory(str(sub1))
    assert any(i["name"] == "nested" and i["is_dir"] is True for i in nested_items)
