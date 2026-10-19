import pytest

from src.storage.dir_manager import StorageDirectoryManager


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


def test_storage_manager_handles_multiple_roots(temp_workspace):
    # 1. Create a second root and a manager that owns both roots
    root_a = temp_workspace["storage_root"]
    root_b = temp_workspace["root"] / "storage_second"
    root_b.mkdir()
    storage_mgr = StorageDirectoryManager([str(root_a), str(root_b)])

    assert storage_mgr.allowed_roots == [str(root_a.resolve()), str(root_b.resolve())]

    # 2. Each root can be browsed and written independently
    storage_mgr.create_directory(str(root_a / "alpha"))
    storage_mgr.create_directory(str(root_b / "beta"))

    assert [item["name"] for item in storage_mgr.list_directory(str(root_a))] == ["alpha"]
    assert [item["name"] for item in storage_mgr.list_directory(str(root_b))] == ["beta"]

    # 3. Listing without a path falls back to the first root
    assert [item["name"] for item in storage_mgr.list_directory()] == ["alpha"]

    # 4. Paths outside every configured root are still rejected
    with pytest.raises(PermissionError):
        storage_mgr.create_directory(str(root_b / ".." / "escaped"))

    # 5. A configured root itself cannot be renamed or deleted
    with pytest.raises(PermissionError):
        storage_mgr.rename_directory(str(root_b), "renamed-root")
    with pytest.raises(PermissionError):
        storage_mgr.delete_directory(str(root_b))


def test_storage_manager_normalizes_and_dedupes_roots(temp_workspace):
    # 1. Blank entries are ignored and repeated roots collapse into one
    root = temp_workspace["storage_root"]
    storage_mgr = StorageDirectoryManager(["", str(root), f" {root} ", str(root)])

    assert storage_mgr.allowed_roots == [str(root.resolve())]


def test_storage_manager_requires_at_least_one_root():
    # 1. An empty root list is a configuration error, not a silent no-op
    with pytest.raises(ValueError, match="At least one allowed storage root"):
        StorageDirectoryManager([])
