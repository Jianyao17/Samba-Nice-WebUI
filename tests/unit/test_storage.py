import pytest

from src.core.models import ShareConfig
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


class _FakeShareBackend:
    """
    Minimal backend exposing the shares used by storage safety checks.
    """

    def __init__(self, shares):
        self._shares = shares

    def list_shares(self):
        return self._shares


def test_storage_rejects_touching_shared_folders(storage_mgr, temp_workspace):
    # 1. Prepare a folder tree with a share on the inner folder
    root = temp_workspace["storage_root"]
    container = storage_mgr.create_directory(str(root / "container"))
    shared_dir = storage_mgr.create_directory(str(container / "shared"))
    backend = _FakeShareBackend(
        [ShareConfig(name="shared", path=str(shared_dir))]
    )

    # 2. The shared folder itself cannot be renamed or deleted
    with pytest.raises(PermissionError, match="actively shared"):
        storage_mgr.rename_directory(str(shared_dir), "renamed", backend=backend)
    with pytest.raises(PermissionError, match="actively shared"):
        storage_mgr.delete_directory(str(shared_dir), backend=backend)

    # 3. A parent folder that contains a share is protected as well
    with pytest.raises(PermissionError, match="actively shared"):
        storage_mgr.delete_directory(str(container), backend=backend)

    # 4. The guarded folders are left untouched
    assert shared_dir.exists()
    assert container.exists()


def test_storage_rejects_deleting_folder_with_files(storage_mgr, temp_workspace):
    # 1. A folder holding files at any depth cannot be deleted
    root = temp_workspace["storage_root"]
    folder = storage_mgr.create_directory(str(root / "with_files"))
    nested = storage_mgr.create_directory(str(folder / "nested"))
    (nested / "notes.txt").write_text("data", encoding="utf-8")

    with pytest.raises(PermissionError, match="still contains files"):
        storage_mgr.delete_directory(str(folder))

    assert folder.exists()

    # 2. Empty folders (even with empty subfolders) can still be deleted
    empty = storage_mgr.create_directory(str(root / "empty"))
    storage_mgr.create_directory(str(empty / "empty_child"))
    storage_mgr.delete_directory(str(empty))

    assert not empty.exists()
