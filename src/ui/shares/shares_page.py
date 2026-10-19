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
from src.storage.dir_manager import StorageDirectoryManager
from src.ui.layout import page_layout
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


def create_shares_page(backend: SambaBackend, dir_manager: StorageDirectoryManager):
    with page_layout("Share Configurations", backend, show_title=False) as authenticated:
        if not authenticated:
            return

        # 1. Resolve the public SMB endpoint once per page render
        smb_host = _resolve_smb_host()
        smb_port = normalize_smb_port(settings.samba_smb_port)

        with ui.column().classes("w-full gap-6"):
            # 2. Page title and share count
            with ui.row().classes("w-full items-center gap-2"):
                ui.label("Share Configurations").classes(
                    "text-2xl font-bold text-slate-800 dark:text-slate-100"
                )
                with ui.element("div").classes(
                    "flex items-center justify-center min-w-8 h-8 px-2 "
                    "rounded-full bg-blue-600 text-white text-sm font-bold shadow-sm"
                ):
                    count_label = ui.label("0").classes("leading-none")

            # 3. Description and Add Share action share one row on desktop
            with ui.element("div").classes(
                "w-full flex flex-col sm:flex-row sm:items-center "
                "sm:justify-between gap-2 mb-3"
            ):
                ui.label(
                    f"Configure and manage Samba shares stored in "
                    f"{settings.samba_include_conf_path.name}. Changes are validated "
                    f"and applied immediately."
                ).classes("text-sm text-slate-500 min-w-0 sm:flex-1")

                ui.button(
                    "Add Share",
                    icon="add",
                    on_click=lambda: open_share_dialog(
                        None, backend, dir_manager, refresh_shares
                    ),
                ).props("unelevated no-caps color=primary").classes(
                    "rounded-lg w-full sm:w-auto"
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
                        lambda: open_share_dialog(None, backend, dir_manager, refresh_shares)
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
                            selected, backend, dir_manager, refresh_shares
                        ),
                        on_delete=lambda selected: open_delete_dialog(
                            selected, backend, refresh_shares
                        ),
                    )

        refresh_shares()
