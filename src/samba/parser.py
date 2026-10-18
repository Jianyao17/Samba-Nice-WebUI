import re
from pathlib import Path
from typing import Optional

from src.core.models import ShareConfig


RESERVED_SECTION_NAMES = {"global", "homes", "printers"}


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


def parse_conf_content(content: str, filename: str = "") -> list[ShareConfig]:
    # 1. Split content by sections while preserving parameters
    shares: list[ShareConfig] = []
    current_section: Optional[str] = None
    section_params: dict[str, str] = {}

    def commit_section():
        if current_section and current_section.lower() not in RESERVED_SECTION_NAMES:
            path_val = section_params.get("path", "")
            if path_val:
                shares.append(
                    ShareConfig(
                        name=current_section,
                        path=path_val,
                        comment=section_params.get("comment", ""),
                        read_only=parse_boolean_value(section_params.get("read only", "no")),
                        browsable=parse_boolean_value(section_params.get("browsable", "yes")),
                        guest_ok=parse_boolean_value(section_params.get("guest ok", "no")),
                        valid_users=section_params.get("valid users", ""),
                        write_list=section_params.get("write list", ""),
                        conf_file=filename,
                        extra_options={
                            k: v
                            for k, v in section_params.items()
                            if k not in {"path", "comment", "read only", "browsable", "guest ok", "valid users", "write list"}
                        }
                    )
                )

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
            clean_key = key.strip().lower()
            clean_val = val.strip()
            section_params[clean_key] = clean_val

    # 3. Commit the last section in file
    commit_section()

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
        f"    browsable = {format_boolean_value(share.browsable)}",
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

