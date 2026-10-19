"""Formatting helpers for client-facing SMB share addresses."""

from urllib.parse import quote

DEFAULT_SMB_PORT = 445


def normalize_smb_host(host: str) -> str:
    """Normalize a configured hostname, IP address, or SMB URL."""
    # 1. Remove common URL decorations so the value can be used as a hostname
    value = (host or "").strip()
    if value.lower().startswith("smb://"):
        value = value[len("smb://"):]
    value = value.rstrip("/")

    # 2. Accept bracketed IPv6 literals but store them without brackets
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]

    return value or "localhost"


def normalize_smb_port(port: int | None) -> int:
    """Return a valid SMB port, falling back to 445 for invalid values."""
    try:
        value = int(port) if port is not None else DEFAULT_SMB_PORT
    except (TypeError, ValueError):
        return DEFAULT_SMB_PORT

    return value if 1 <= value <= 65535 else DEFAULT_SMB_PORT


def _format_uri_host(host: str) -> str:
    # 1. Wrap IPv6 literals in brackets for use inside an SMB URI
    value = normalize_smb_host(host)
    if ":" in value and not value.startswith("["):
        return f"[{value}]"
    return value


def build_smb_uri(host: str, share_name: str, port: int | None = DEFAULT_SMB_PORT) -> str:
    """Build an SMB URI such as ``smb://server/share`` or ``smb://server:1445/share``."""
    uri_host = _format_uri_host(host)
    clean_port = normalize_smb_port(port)
    clean_share = quote((share_name or "").strip(), safe="")

    if clean_port == DEFAULT_SMB_PORT:
        return f"smb://{uri_host}/{clean_share}"

    return f"smb://{uri_host}:{clean_port}/{clean_share}"


def build_unc_path(host: str, share_name: str) -> str:
    """Build a Windows UNC path when the host can be represented that way."""
    clean_host = normalize_smb_host(host)
    clean_share = (share_name or "").strip()

    # 1. UNC paths do not support IPv6 literals or custom ports cleanly
    if ":" in clean_host or not clean_share:
        return ""

    return f"\\\\{clean_host}\\{clean_share}"
