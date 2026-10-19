from pathlib import Path
from typing import Any

from src.core.security import ensure_safe_storage_path


class StorageDirectoryManager:
    """
    Handles filesystem directory browsing and creation restricted to allowed storage roots.

    Enforces path canonicalization and strict boundary validation to prevent
    directory traversal attacks, ensuring users cannot browse or create folders
    outside designated storage paths.
    """

    def __init__(self, allowed_roots: list[str], backend: Any | None = None):
        # 1. Canonicalize paths, ignore blanks, and remove duplicates while keeping order
        normalized_roots: list[str] = []
        for root in allowed_roots:
            text = str(root).strip()
            if not text:
                continue
            try:
                resolved = str(Path(text).expanduser().resolve())
            except (OSError, ValueError, RuntimeError) as err:
                raise ValueError(f"Invalid storage root '{text}': {err}") from err
            if resolved not in normalized_roots:
                normalized_roots.append(resolved)

        if not normalized_roots:
            raise ValueError("At least one allowed storage root must be configured.")

        # 2. Initialize allowed root paths and guarantee existence
        self.allowed_roots = normalized_roots
        self.backend = backend
        for root_str in self.allowed_roots:
            Path(root_str).mkdir(parents=True, exist_ok=True)

    def is_path_shared(self, target_path: Path, backend: Any | None = None) -> tuple[bool, str | None]:
        """
        Check if a directory or any of its children is actively shared in Samba.
        Returns (True, share_name) if shared, or (False, None).
        """
        b = backend or self.backend
        if not b:
            return False, None
        try:
            shares = b.list_shares()
            target_resolved = target_path.resolve()
            for s in shares:
                try:
                    s_path = Path(s.path).resolve()
                    if s_path == target_resolved:
                        return True, s.name
                    if target_resolved in s_path.parents:
                        return True, f"{s.name} (contains share {s_path.name})"
                except Exception:
                    continue
        except Exception:
            pass
        return False, None

    def list_directory(self, rel_or_abs_path: str = "") -> list[dict[str, Any]]:
        # 1. Fallback to first allowed root if path is not specified
        if not rel_or_abs_path.strip():
            target_path = Path(self.allowed_roots[0]).resolve()
        else:
            target_path = ensure_safe_storage_path(rel_or_abs_path, self.allowed_roots)

        if not target_path.exists() or not target_path.is_dir():
            return []

        # 2. Iterate through items safely and gather metadata
        items = []
        for entry in sorted(target_path.iterdir()):
            try:
                stat = entry.stat()
                items.append({
                    "name": entry.name,
                    "path": str(entry.resolve()),
                    "is_dir": entry.is_dir(),
                    "size_bytes": stat.st_size if not entry.is_dir() else 0,
                    "modified_time": stat.st_mtime,
                })
            except (PermissionError, OSError):
                continue

        return items

    def create_directory(self, target_path_str: str) -> Path:
        # 1. Enforce strict safety verification before filesystem creation
        safe_path = ensure_safe_storage_path(target_path_str, self.allowed_roots)

        # 2. Create directory including parents safely
        safe_path.mkdir(parents=True, exist_ok=True)
        return safe_path

    def rename_directory(self, target_path_str: str, new_name: str, backend: Any | None = None) -> Path:
        """
        Rename a directory or file safely within allowed storage roots.
        Prevents renaming root directories or actively shared folders.
        """
        clean_name = new_name.strip()
        if not clean_name:
            raise ValueError("Directory name cannot be empty.")
        if any(sep in clean_name for sep in ["/", "\\", ".."]):
            raise ValueError("Invalid directory name format.")

        safe_path = ensure_safe_storage_path(target_path_str, self.allowed_roots)
        if not safe_path.exists():
            raise FileNotFoundError(f"Item '{target_path_str}' does not exist.")

        # Disallow renaming allowed roots
        if safe_path in [Path(r).resolve() for r in self.allowed_roots]:
            raise PermissionError("Cannot rename a root storage directory.")

        # Disallow renaming shared folders
        shared, share_name = self.is_path_shared(safe_path, backend)
        if shared:
            raise PermissionError(
                f"Folder '{safe_path.name}' is actively shared in Samba as '{share_name}'. "
                "Remove or edit the share before renaming."
            )

        dest_path = safe_path.parent / clean_name
        dest_safe = ensure_safe_storage_path(str(dest_path), self.allowed_roots)
        if dest_safe.exists():
            raise FileExistsError(f"An item named '{clean_name}' already exists in this directory.")

        safe_path.rename(dest_safe)
        return dest_safe

    @staticmethod
    def _is_recursively_empty(path: Path) -> bool:
        """
        Returns True only if 'path' (a directory) contains no files at any
        depth — only subdirectories are allowed.  A single regular file anywhere
        inside the tree makes this return False.
        """
        for entry in path.rglob("*"):
            if entry.is_file():
                return False
        return True

    def delete_directory(self, target_path_str: str, backend: Any | None = None) -> None:
        """
        Delete a directory or file safely within allowed storage roots.
        Prevents deleting root directories, actively shared folders,
        or folders that still contain files (recursively).
        """
        import shutil

        safe_path = ensure_safe_storage_path(target_path_str, self.allowed_roots)
        if not safe_path.exists():
            raise FileNotFoundError(f"Item does not exist: {target_path_str}")

        # Disallow deleting allowed roots
        if safe_path in [Path(r).resolve() for r in self.allowed_roots]:
            raise PermissionError("Cannot delete a root storage directory.")

        # Disallow deleting shared folders
        shared, share_name = self.is_path_shared(safe_path, backend)
        if shared:
            raise PermissionError(
                f"Folder '{safe_path.name}' is actively shared in Samba as '{share_name}'. "
                "Remove or edit the share before deleting."
            )

        # Disallow deleting directories that still contain files (recursively)
        if safe_path.is_dir() and not self._is_recursively_empty(safe_path):
            raise PermissionError(
                f"Folder '{safe_path.name}' cannot be deleted because it still contains files. "
                "Remove all files inside the folder (including subfolders) before deleting."
            )

        if safe_path.is_dir():
            shutil.rmtree(safe_path)
        else:
            safe_path.unlink()

    def check_path_exists(self, target_path_str: str) -> bool:
        # 1. Verify path exists and falls within allowed roots
        try:
            safe_path = ensure_safe_storage_path(target_path_str, self.allowed_roots)
            return safe_path.exists()
        except PermissionError:
            return False
