"""Shared share-creation, update, and rename planning utilities.

Both the Linux and mock backends use this module so that duplicate-name
protection and rename semantics are enforced identically.
"""

from dataclasses import dataclass
from typing import Optional

from src.core.models import ShareConfig
from src.samba.parser import sanitize_share_name


class ShareMutationError(ValueError):
    """Raised when a share create/update/rename cannot be applied."""


@dataclass(frozen=True)
class ShareSavePlan:
    """Validated result of planning a share save operation."""

    shares: list[ShareConfig]
    share: ShareConfig
    original_name: Optional[str]
    is_rename: bool


def prepare_share_save(
    current_shares: list[ShareConfig],
    share: ShareConfig,
    original_name: Optional[str] = None,
) -> ShareSavePlan:
    """
    Validate and prepare the new share list for a create/update/rename.

    - ``original_name is None`` creates a new share and rejects duplicate names.
    - ``original_name`` identifies the existing section to replace. The section
      may be renamed, but the new name must not collide with another share.
    """
    # 1. Validate the target path and sanitize the requested section name
    if not share.path.strip():
        raise ShareMutationError("Target path is required.")

    try:
        clean_name = sanitize_share_name(share.name)
    except ValueError as exc:
        raise ShareMutationError(str(exc)) from exc

    if len(clean_name) > 64:
        raise ShareMutationError("Share name cannot be longer than 64 characters.")

    normalized = share.model_copy(update={"name": clean_name})
    current_by_name = {item.name.strip().casefold(): item for item in current_shares}

    # 2. Replace an existing section when the original name is known; otherwise append
    if original_name is not None:
        original_key = original_name.strip().casefold()
        if original_key not in current_by_name:
            raise ShareMutationError(
                f"Share '{original_name}' no longer exists. Refresh and try again."
            )

        new_key = clean_name.casefold()
        collision = current_by_name.get(new_key)
        if collision is not None and collision.name.strip().casefold() != original_key:
            raise ShareMutationError(
                f"A share named '{clean_name}' already exists. Choose a different name."
            )

        updated_shares = [
            normalized if item.name.strip().casefold() == original_key else item
            for item in current_shares
        ]
        is_rename = original_key != new_key
        
    else:
        if clean_name.casefold() in current_by_name:
            raise ShareMutationError(
                f"A share named '{clean_name}' already exists. "
                "Edit the existing share or choose a different name."
            )

        updated_shares = [*current_shares, normalized]
        is_rename = False

    return ShareSavePlan(
        shares=updated_shares,
        share=normalized,
        original_name=original_name,
        is_rename=is_rename,
    )
