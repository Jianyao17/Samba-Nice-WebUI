import hmac
import secrets
from pathlib import Path

from src.config import settings


def is_path_safe(target_path: Path, allowed_roots: list[Path]) -> bool:
    try:
        # 1. Resolve target path to canonical absolute form, eliminating symlinks and traversal components
        resolved_target = target_path.resolve()

        # 2. Check if the target is equal to or a child of any configured allowed storage root
        for root in allowed_roots:
            resolved_root = root.resolve()
            if resolved_target == resolved_root or resolved_target.is_relative_to(resolved_root):
                return True

        # 3. Path falls outside all configured allowed roots
        return False

    except (ValueError, RuntimeError):
        # 4. In case of any path resolution error, deny access by default
        return False


def ensure_safe_storage_path(target_path_str: str, allowed_roots: list[str]) -> Path:
    # 1. Convert string paths to Path instances
    target_path = Path(target_path_str)
    root_paths = [Path(root) for root in allowed_roots]

    # 2. Validate safety against configured allowed roots
    if not is_path_safe(target_path, root_paths):
        raise PermissionError(f"Access denied: path '{target_path_str}' is outside allowed storage roots.")

    # 3. Return validated canonical Path
    return target_path.resolve()


def verify_credentials(username: str, password: str) -> bool:
    # 1. Constant-time comparison to prevent timing attacks
    is_user_match = hmac.compare_digest(username.strip(), settings.webui_admin_user.strip())
    is_pass_match = hmac.compare_digest(password.strip(), settings.webui_admin_password.strip())

    # 2. Return authentication verdict
    return is_user_match and is_pass_match


def generate_session_token() -> str:
    # 1. Generate high-entropy cryptographically secure random token
    return secrets.token_urlsafe(32)
