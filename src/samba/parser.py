import re
from pathlib import Path
from typing import Optional

from src.core.models import ShareConfig


RESERVED_SECTION_NAMES = {"global", "homes", "printers"}

# Documented Samba synonyms mapped to their canonical parameter name
OPTION_ALIASES = {
    "browsable": "browseable",
    "public": "guest ok",
}

# Synonyms that express the inverse of a canonical boolean parameter
INVERTED_OPTION_ALIASES = {
    "writeable": "read only",
    "writable": "read only",
    "write ok": "read only",
}


def sanitize_share_name(name: str) -> str:
    # 1. Strip surrounding whitespace and remove invalid characters
    clean_name = re.sub(r"[^\w\-_.]", "", name.strip())

    # 2. Reject empty or reserved Samba section names
    if not clean_name:
        raise ValueError("Share name cannot be empty or contain only invalid characters.")

    if clean_name.lower() in RESERVED_SECTION_NAMES:
        raise ValueError(f"Share name '{clean_name}' is a reserved Samba section name.")

    return clean_name


def parse_boolean_value(val: str) -> bool:
    # 1. Normalize Samba boolean strings (yes/no, true/false, 1/0)
    normalized = val.strip().lower()
    return normalized in {"yes", "true", "1"}


def format_boolean_value(val: bool) -> str:
    # 1. Format boolean using standard Samba convention
    return "yes" if val else "no"


def normalize_option(key: str, value: str) -> tuple[str, str]:
    """
    Canonicalize a Samba parameter name and invert documented synonyms.
    """
    # 1. Samba parameter names ignore case and repeated whitespace
    clean_key = " ".join(key.split()).casefold()

    # 2. Inverted synonyms such as 'writeable' map to 'read only = no'
    canonical = INVERTED_OPTION_ALIASES.get(clean_key)
    if canonical is not None:
        return canonical, format_boolean_value(not parse_boolean_value(value))

    return OPTION_ALIASES.get(clean_key, clean_key), value


def parse_conf_content(content: str, filename: str = "") -> list[ShareConfig]:
    """
    Parse Samba configuration content into share models.

    Samba treats section and parameter names case-insensitively, so duplicate
    sections are merged into one entry with later values winning.
    """
    # 1. Collect sections by case-insensitive name so manual duplicates merge
    sections: dict[str, tuple[str, dict[str, str]]] = {}
    current_section: Optional[str] = None
    section_params: dict[str, str] = {}

    def commit_section():
        if not current_section:
            return

        if current_section.casefold() in RESERVED_SECTION_NAMES:
            return

        key = current_section.casefold()
        existing = sections.get(key)
        if existing is None:
            sections[key] = (current_section, dict(section_params))
            return

        # Merge repeated sections: keep the first spelling, later values win
        name, params = existing
        params.update(section_params)
        sections[key] = (name, params)

    # 2. Parse lines sequentially
    for line in content.splitlines():
        line = line.strip()

        # Skip empty lines or pure comment lines
        if not line or line.startswith("#") or line.startswith(";"):
            continue

        # Detect section header [section_name]
        section_match = re.match(r"^\[([^\]]+)\]$", line)
        if section_match:
            commit_section()
            current_section = section_match.group(1).strip()
            section_params = {}
            continue

        # Parse key = value pair within section
        if "=" in line and current_section:
            key, val = line.split("=", 1)
            clean_key, clean_val = normalize_option(key, val.strip())
            section_params[clean_key] = clean_val

    # 3. Commit the last section in file
    commit_section()

    # 4. Build share models, skipping sections without a target path
    shares: list[ShareConfig] = []
    for name, params in sections.values():
        path_val = params.get("path", "")
        if not path_val:
            continue

        shares.append(
            ShareConfig(
                name=name,
                path=path_val,
                comment=params.get("comment", ""),
                read_only=parse_boolean_value(params.get("read only", "no")),
                browsable=parse_boolean_value(params.get("browseable", "yes")),
                guest_ok=parse_boolean_value(params.get("guest ok", "no")),
                valid_users=params.get("valid users", ""),
                write_list=params.get("write list", ""),
                conf_file=filename,
                extra_options={
                    k: v
                    for k, v in params.items()
                    if k not in {"path", "comment", "read only", "browseable", "guest ok", "valid users", "write list"}
                }
            )
        )

    return shares


def parse_conf_file(file_path: Path) -> list[ShareConfig]:
    # 1. Safely read and parse target file if it exists
    if not file_path.exists():
        return []

    content = file_path.read_text(encoding="utf-8", errors="replace")
    return parse_conf_content(content, filename=file_path.name)


def serialize_share(share: ShareConfig) -> str:
    # 1. Validate sanitized section header name
    clean_name = sanitize_share_name(share.name)

    # 2. Build structured INI lines with standard Samba formatting
    lines = [
        f"[{clean_name}]",
        f"    path = {share.path}",
        f"    comment = {share.comment}",
        f"    read only = {format_boolean_value(share.read_only)}",
        f"    browseable = {format_boolean_value(share.browsable)}",
        f"    guest ok = {format_boolean_value(share.guest_ok)}",
    ]

    # 3. Append optional access control list directives
    if share.valid_users.strip():
        lines.append(f"    valid users = {share.valid_users.strip()}")

    if share.write_list.strip():
        lines.append(f"    write list = {share.write_list.strip()}")

    # 4. Append custom extra options
    for key, value in sorted(share.extra_options.items()):
        if value:
            lines.append(f"    {key} = {value}")

    lines.append("")
    return "\n".join(lines)


def serialize_all_shares(shares: list[ShareConfig]) -> str:
    # 1. Generate clean header for the dedicated include configuration file
    blocks = [
        "# ==================================================================",
        "# Samba-Nice-WebUI Managed Shares Configuration",
        "# This file is included into the primary smb.conf",
        "# ==================================================================\n"
    ]

    # 2. Append serialized blocks for each configured share
    for share in shares:
        blocks.append(serialize_share(share))

    return "\n".join(blocks)

