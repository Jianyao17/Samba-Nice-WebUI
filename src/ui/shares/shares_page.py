"""Samba share management page."""

from __future__ import annotations

import socket
from nicegui import ui

from src.config import settings
from src.core.smb_address import (
    build_smb_uri,
    build_unc_path,
    normalize_smb_port,
)
from src.samba.backend import SambaBackend
from src.samba.user_backend import SambaUserBackend
from src.storage.dir_manager import StorageDirectoryManager
from src.ui.layout import page_layout, render_page_header
from src.ui.shares.shares_components import (
    render_empty_state,
    render_share_card,
)
from src.ui.shares.shares_dialogs import open_delete_dialog, open_share_dialog


def _resolve_smb_host() -> str:
    """Resolve the hostname shown in client-facing SMB addresses."""
    # 1. Prefer an explicitly configured public SMB host
    configured = settings.samba_smb_host.strip()
    if configured:
        return configured

    # 2. Fall back to the hostname the browser used to reach the WebUI
    try:
        request_host = ui.context.client.request.url.hostname
        if request_host:
            return request_host
    except (RuntimeError, AttributeError):
        pass

    # 3. Last-resort fallback for local development
    try:
        return socket.gethostname() or "localhost"
    except OSError:
        return "localhost"


def create_shares_page(
    backend: SambaBackend,
    dir_manager: StorageDirectoryManager,
    user_backend: SambaUserBackend | None = None,
):
    with page_layout("Share Configurations", backend, show_title=False) as authenticated:
        if not authenticated:
            return

        # 1. Resolve the public SMB endpoint once per page render
        smb_host = _resolve_smb_host()
        smb_port = normalize_smb_port(settings.samba_smb_port)

        with ui.column().classes("w-full gap-4"):
            # 2. Page header with live share count and the primary action
            count_label = render_page_header(
                "Share Configurations",
                f"Configure and manage Samba shares stored in "
                f"{settings.samba_include_conf_path.name}. Changes are validated "
                f"and applied immediately.",
                count=True,
                action_label="Add Share",
                action_icon="add",
                on_action=lambda: open_share_dialog(
                    None, backend, dir_manager, refresh_shares, user_backend
                ),
            )

            # 4. Share cards live inside this container and are rebuilt on refresh
            shares_container = ui.column().classes("w-full gap-3")

        def refresh_shares() -> None:
            shares_container.clear()
            shares = backend.list_shares()
            count_label.set_text(str(len(shares)))

            with shares_container:
                if not shares:
                    render_empty_state(
                        lambda: open_share_dialog(
                            None, backend, dir_manager, refresh_shares, user_backend
                        )
                    )
                    return

                for share in shares:
                    smb_uri = build_smb_uri(smb_host, share.name, smb_port)
                    unc_path = (
                        build_unc_path(smb_host, share.name)
                        if smb_port == 445
                        else ""
                    )
                    render_share_card(
                        share,
                        smb_uri,
                        unc_path,
                        on_edit=lambda selected: open_share_dialog(
                            selected, backend, dir_manager, refresh_shares, user_backend
                        ),
                        on_delete=lambda selected: open_delete_dialog(
                            selected, backend, refresh_shares
                        ),
                    )

        refresh_shares()
