"""Reusable UI components for the Samba shares page."""

from __future__ import annotations

from typing import Callable, Optional
from nicegui import ui

from src.core.models import ShareConfig


_CARD_CLASSES = (
    "w-full p-0 rounded-xl overflow-hidden border border-slate-200 "
    "dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm"
)
_HEADER_CLASSES = (
    "w-full items-center justify-between gap-3 px-4 py-2.5 "
    "bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-700"
)
_FOOTER_CLASSES = (
    "w-full px-4 py-2 gap-0.5 bg-slate-50 dark:bg-slate-800/40 "
    "border-t border-slate-100 dark:border-slate-800"
)


def _render_badge(label: str, color: str, icon: Optional[str] = None) -> None:
    with ui.badge(color=color).props("rounded").classes(
        "flex items-center justify-center gap-1 sm:gap-1.5"
        "text-[10px] sm:text-xs font-medium whitespace-nowrap"
        "px-2 py-1 sm:px-2.5 sm:py-1.5"
    ):
        if icon:
            ui.icon(icon).classes("shrink-0 text-[12px] sm:text-[14px]")
        ui.label(label).classes("text-[11px] sm:text-xs leading-none")


def render_share_badges(share: ShareConfig) -> None:
    """Render every share detail badge in a single wrapping row."""
    with ui.row().classes("items-center gap-1 sm:gap-1.5 flex-wrap"):
        if share.read_only:
            _render_badge("Read-Only", "warning", "lock")
        else:
            _render_badge("Read/Write", "positive", "edit")

        if share.browsable:
            _render_badge("Browsable", "primary", "visibility")
        else:
            _render_badge("Hidden", "grey", "visibility_off")

        if share.guest_ok:
            _render_badge("Guest Allowed", "warning", "person")
        else:
            _render_badge("Guest Denied", "grey", "person_off")

        if share.valid_users.strip():
            _render_badge(f"Users: {share.valid_users}", "grey", "group")
        if share.write_list.strip():
            _render_badge(f"Write: {share.write_list}", "grey", "edit_note")


def render_smb_access(smb_uri: str, unc_path: str = "") -> None:
    """Show the client-facing SMB address with a copy action."""
    with ui.row().classes("w-full items-center gap-2 flex-nowrap"):
        ui.icon("link", size="1.1rem").classes("text-slate-400 shrink-0")
        ui.label("SMB").classes(
            "text-[10px] uppercase tracking-wide text-slate-400 shrink-0"
        )
        ui.label(smb_uri).classes(
            "text-xs font-mono text-slate-700 dark:text-slate-200 "
            "truncate min-w-0 flex-1 select-all"
        ).tooltip(smb_uri)

        def copy_address() -> None:
            ui.clipboard.write(smb_uri)
            ui.notify("SMB address copied.", type="positive")

        ui.button(icon="content_copy", on_click=copy_address).props(
            "flat round dense color=grey-7"
        ).classes("shrink-0").tooltip("Copy SMB address")

    if unc_path:
        ui.label(f"Windows: {unc_path}").classes(
            "w-full text-[11px] font-mono text-slate-400 truncate select-all"
        ).tooltip(unc_path)


def render_share_action_menu(
    share: ShareConfig,
    on_edit: Callable[[ShareConfig], None],
    on_delete: Callable[[ShareConfig], None],
) -> None:
    """3-dots menu with edit/rename and delete actions."""
    with ui.menu().props("auto-close").classes(
        "rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 "
        "bg-white dark:bg-slate-900 p-1.5 min-w-[180px]"
    ):
        with ui.item().props("clickable v-close-popup").classes(
            "px-3.5 py-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 "
            "flex items-center gap-3 transition-colors cursor-pointer"
        ).on("click", lambda: on_edit(share)):
            ui.icon("edit", size="1.25rem").classes(
                "text-blue-600 dark:text-blue-400 shrink-0"
            )
            ui.label("Edit / Rename").classes(
                "text-sm font-semibold text-slate-700 dark:text-slate-200"
            )

        with ui.item().props("clickable v-close-popup").classes(
            "px-3.5 py-2.5 rounded-xl hover:bg-red-50 dark:hover:bg-red-950/40 "
            "flex items-center gap-3 transition-colors cursor-pointer"
        ).on("click", lambda: on_delete(share)):
            ui.icon("delete", size="1.25rem").classes("text-red-500 shrink-0")
            ui.label("Delete").classes("text-sm font-semibold text-red-600 dark:text-red-400")


def render_share_card(
    share: ShareConfig,
    smb_uri: str,
    unc_path: str,
    on_edit: Callable[[ShareConfig], None],
    on_delete: Callable[[ShareConfig], None],
) -> None:
    """Render one share as a Material-style card."""
    with ui.card().props("flat bordered").classes(_CARD_CLASSES):
        # 1. Header: identity, path, and direct desktop actions
        with ui.row().classes(_HEADER_CLASSES):
            with ui.row().classes("items-center gap-3 flex-1 min-w-0"):
                ui.icon("folder_shared", size="2rem").classes(
                    "text-blue-600 dark:text-blue-400 shrink-0"
                )
                with ui.column().classes("gap-0 min-w-0"):
                    ui.label(share.name).classes(
                        "text-base font-bold text-slate-800 dark:text-slate-100 truncate"
                    ).tooltip(share.name)
                    ui.label(share.path).classes(
                        "text-xs font-mono text-slate-400 truncate select-all"
                    ).tooltip(share.path)

            with ui.row().classes("items-center gap-0.5 shrink-0"):
                ui.button(icon="edit", on_click=lambda: on_edit(share)).props(
                    "flat round dense color=primary"
                ).classes("gt-xs").tooltip("Edit / Rename")
                ui.button(icon="delete", on_click=lambda: on_delete(share)).props(
                    "flat round dense color=negative"
                ).classes("gt-xs").tooltip("Delete Share")
                with ui.button(icon="more_vert").props("flat round dense color=grey-7").classes(
                    "lt-sm text-slate-500 hover:text-slate-800 "
                    "dark:text-slate-400 dark:hover:text-slate-100"
                ).on("click.stop", lambda: None):
                    render_share_action_menu(share, on_edit, on_delete)

        # 2. Body: description and one wrapping row of detail badges
        with ui.column().classes("w-full px-4 py-2 gap-1.5"):
            if share.comment.strip():
                ui.label(share.comment).classes(
                    "text-sm text-slate-600 dark:text-slate-300 italic"
                )

            render_share_badges(share)

        # 3. Footer: SMB access address
        with ui.column().classes(_FOOTER_CLASSES):
            render_smb_access(smb_uri, unc_path)


def render_empty_state(on_add: Optional[Callable] = None) -> None:
    """Dashed empty state shown when no shares exist yet."""
    with ui.card().props("flat bordered").classes(
        "w-full p-8 text-center border-dashed border-slate-300 dark:border-slate-700"
    ):
        ui.icon("folder_off", size="3rem").classes(
            "mx-auto text-slate-300 dark:text-slate-600 mb-2"
        )
        ui.label("No Samba shares configured yet.").classes(
            "font-medium text-slate-600 dark:text-slate-300"
        )
        ui.label("Add a share to expose a storage folder over SMB.").classes(
            "text-xs text-slate-400 mt-1"
        )
        if on_add is not None:
            ui.button("Add Share", icon="add", on_click=on_add).props(
                "unelevated dense no-caps color=primary"
            ).classes("mt-4 rounded-lg")
