"""Share-level configuration diffing utilities.

This module compares two Samba include-file contents and produces a compact
description of what changed: added shares, removed shares, and field-level
modifications for shares that exist in both versions.
"""

from dataclasses import dataclass, field

from src.core.models import ShareConfig
from src.samba.parser import parse_conf_content


@dataclass
class ShareDiff:
    """Compact, presentation-friendly difference between two configurations."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    file_changed: bool = False

    @property
    def is_empty(self) -> bool:
        # 1. True when no share was added, removed, or modified
        return not self.added and not self.removed and not self.modified

    @property
    def has_changes(self) -> bool:
        # 2. A raw file change alone (e.g. comments/whitespace) still counts
        return self.file_changed or not self.is_empty


def _share_map(content: str | None) -> dict[str, ShareConfig]:
    # 1. Parse content and key shares by case-insensitive section name
    if not content:
        return {}

    shares = parse_conf_content(content)
    return {share.name.casefold(): share for share in shares}


def _format_value(value: object) -> str:
    # 1. Use Samba-style yes/no for booleans, trimmed text for everything else
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value).strip()


def _share_fields(share: ShareConfig) -> dict[str, str]:
    # 1. Collect the standard fields shown in the UI
    fields: dict[str, object] = {
        "name": share.name,
        "path": share.path,
        "comment": share.comment,
        "read only": share.read_only,
        "browsable": share.browsable,
        "guest ok": share.guest_ok,
        "valid users": share.valid_users,
        "write list": share.write_list,
    }

    # 2. Flatten custom options so each key is diffed independently
    for key, value in share.extra_options.items():
        fields[f"extra:{key.casefold()}"] = value

    return {key: _format_value(value) for key, value in fields.items()}


def diff_contents(old_content: str | None, new_content: str | None) -> ShareDiff:
    """Compare two raw configuration contents.

    The direction is always old -> new. A missing old content means the new
    configuration is treated as an initial snapshot.
    """
    # 1. Parse both sides into case-insensitive share maps
    old_shares = _share_map(old_content)
    new_shares = _share_map(new_content)

    diff = ShareDiff(file_changed=old_content != new_content)

    # 2. Detect added and removed shares
    for key in sorted(new_shares.keys() - old_shares.keys()):
        diff.added.append(new_shares[key].name)

    for key in sorted(old_shares.keys() - new_shares.keys()):
        diff.removed.append(old_shares[key].name)

    # 3. Detect field-level changes for shares present on both sides
    for key in sorted(old_shares.keys() & new_shares.keys()):
        old_fields = _share_fields(old_shares[key])
        new_fields = _share_fields(new_shares[key])

        changed: dict[str, tuple[str, str]] = {}
        for field_name in sorted(old_fields.keys() | new_fields.keys()):
            before = old_fields.get(field_name, "")
            after = new_fields.get(field_name, "")
            if before != after:
                changed[field_name] = (before, after)

        if changed:
            diff.modified[new_shares[key].name] = changed

    return diff
