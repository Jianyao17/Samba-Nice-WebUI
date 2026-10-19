"""
Reusable UI components for the Storage Explorer page.

Exports:
  - render_action_menu   : 3-dots dropdown with Rename / Delete actions
  - render_list_view     : Material-style list view of directory items
  - render_icons_view    : Grid/icon view of directory items
"""

from pathlib import Path
from typing import Callable
from nicegui import ui


# ─────────────────────────── shared helpers ────────────────────────────────

def render_smb_badge(share_name: str, compact: bool = False) -> None:
    """Inline SMB share badge used in both list and icon views."""
    size = "13px" if compact else "12px"
    with ui.badge(color="primary").props("rounded").classes(
        f"text-xs px-2 py-0.5 font-semibold flex items-center gap-1 shadow-sm text-white flex-nowrap {'max-w-full' if compact else 'max-w-[150px] sm:max-w-none'}"
    ):
        ui.icon("folder_shared" if not compact else "share", size=size).classes("shrink-0")
        ui.label(share_name).classes("truncate text-xs")


def render_action_menu(item: dict, is_shared: bool, on_rename: Callable, on_delete: Callable) -> None:
    """3-dots dropdown menu with Rename and Delete items."""
    with ui.menu().props("auto-close").classes(
        "rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 "
        "bg-white dark:bg-slate-900 p-1.5 min-w-[160px]"
    ):
        with ui.item().props("clickable v-close-popup").classes(
            "px-3.5 py-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 "
            "flex items-center gap-3 transition-colors cursor-pointer"
        ).on("click", lambda: on_rename(item, is_shared)):
            ui.icon("edit", size="1.25rem").classes("text-blue-600 dark:text-blue-400 shrink-0")
            ui.label("Rename").classes("text-sm font-semibold text-slate-700 dark:text-slate-200")

        with ui.item().props("clickable v-close-popup").classes(
            "px-3.5 py-2.5 rounded-xl hover:bg-red-50 dark:hover:bg-red-950/40 "
            "flex items-center gap-3 transition-colors cursor-pointer"
        ).on("click", lambda: on_delete(item, is_shared)):
            ui.icon("delete", size="1.25rem").classes("text-red-500 shrink-0")
            ui.label("Delete").classes("text-sm font-semibold text-red-600 dark:text-red-400")


# ─────────────────────────── list view ─────────────────────────────────────

_ROW_CLS = (
    "w-full px-4 py-2.5 items-center justify-between border-b border-slate-100 "
    "dark:border-slate-800/80 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50 "
    "transition-colors flex-nowrap min-h-[60px]"
)


def _list_row_up(parent: Path, navigate_to: Callable) -> None:
    with ui.item().props("clickable v-ripple").classes(_ROW_CLS).on(
        "click", lambda p=parent: navigate_to(str(p))
    ):
        with ui.row().classes("items-center gap-3.5 flex-1 min-w-0 flex-nowrap"):
            ui.icon("arrow_upward", size="2.2rem").classes("text-blue-500 shrink-0")
            with ui.element("div").classes("flex flex-col min-w-0 flex-1 justify-center"):
                ui.label(".. (Up to parent directory)").classes(
                    "text-sm font-semibold text-blue-600 dark:text-blue-400 truncate w-full block"
                )
                ui.label("Navigate up one level").classes("text-xs text-slate-400 mt-0.5")


def _list_row_item(item: dict, is_shared: bool, share_name: str | None,
                   navigate_to: Callable, on_rename: Callable, on_delete: Callable) -> None:
    is_dir = item["is_dir"]
    row = ui.item().props("clickable v-ripple").classes(_ROW_CLS)
    if is_dir:
        row.on("click", lambda i=item: navigate_to(i["path"]))

    with row:
        with ui.row().classes("items-center gap-3.5 flex-1 min-w-0 flex-nowrap"):
            # Icon
            if is_dir:
                icon_name = "folder_shared" if is_shared else "folder"
                icon_color = "text-blue-600 dark:text-blue-400" if is_shared else "text-amber-500"
                ui.icon(icon_name, size="2.4rem").classes(f"{icon_color} shrink-0")
            else:
                ui.icon("description", size="2.1rem").classes("text-slate-400 shrink-0")

            # Two-line text block
            with ui.element("div").classes("flex flex-col min-w-0 flex-1 justify-center"):
                ui.label(item["name"]).classes(
                    "text-sm font-semibold text-slate-800 dark:text-slate-100 truncate w-full block"
                )
                with ui.row().classes("items-center gap-2 flex-nowrap text-xs text-slate-400 mt-0.5"):
                    if is_dir:
                        ui.label("Folder").classes("shrink-0")
                    else:
                        ui.label("File").classes("shrink-0")
                        ui.label("•").classes(
                            "text-slate-300 dark:text-slate-600 text-xs shrink-0"
                        )
                        ui.label(f"{item['size_bytes'] / 1024:.1f} KB").classes("font-mono shrink-0")

                    if is_shared and share_name:
                        ui.label("•").classes("text-slate-300 dark:text-slate-600 text-xs shrink-0")
                        render_smb_badge(share_name)

        # 3-dots action button
        with ui.button(icon="more_vert").props("flat round color=grey-7").classes(
            "w-10 h-10 shrink-0 ml-1 text-slate-500 hover:text-slate-800 "
            "dark:text-slate-400 dark:hover:text-slate-100 "
            "hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
        ).on("click.stop", lambda: None):
            render_action_menu(item, is_shared, on_rename, on_delete)


def render_list_view(
    items: list[dict],
    share_map: dict[Path, str],
    can_go_up: bool,
    parent: Path,
    navigate_to: Callable,
    on_rename: Callable,
    on_delete: Callable,
) -> None:
    if can_go_up:
        _list_row_up(parent, navigate_to)

    if not items:
        with ui.row().classes("w-full p-8 items-center justify-center text-slate-400"):
            ui.label("This directory is empty.").classes("text-sm italic")
        return

    for item in items:
        item_path = Path(item["path"]).resolve()
        is_dir = item["is_dir"]
        is_shared = is_dir and item_path in share_map
        share_name = share_map.get(item_path) if is_shared else None
        _list_row_item(item, is_shared, share_name, navigate_to, on_rename, on_delete)


# ─────────────────────────── icons / grid view ─────────────────────────────

_TILE_BASE = (
    "group relative overflow-hidden w-full min-h-[175px] p-3 rounded-2xl "
    "flex flex-col items-center justify-between text-center "
    "cursor-pointer select-none "
    "transition-all duration-200 ease-out hover:shadow-md hover:-translate-y-1 active:translate-y-0"
)
_TILE_UP   = "bg-blue-50/40 dark:bg-blue-950/20 border border-blue-200/80 dark:border-blue-900/50 hover:border-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/40"
_TILE_ITEM = "bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-primary/60 hover:bg-slate-50 dark:hover:bg-slate-800/60"


def _tile_bottom_labels(name: str, subtitle: str) -> None:
    with ui.element("div").classes("w-full min-w-0 flex flex-col items-center gap-0.5 mt-auto shrink-0"):
        ui.label(name).classes(
            "w-full text-center text-sm font-semibold text-slate-800 dark:text-slate-100 truncate block px-1"
        ).tooltip(name)
        ui.label(subtitle).classes("text-xs text-slate-400")


def _icon_tile_up(parent: Path, navigate_to: Callable) -> None:
    tile = ui.element("div").props("v-ripple").classes(f"{_TILE_BASE} {_TILE_UP}").on(
        "click", lambda p=parent: navigate_to(str(p))
    )
    with tile:
        ui.element("div").classes("w-full h-6 shrink-0")
        with ui.element("div").classes("flex-1 flex items-center justify-center my-auto py-1"):
            ui.icon("arrow_upward", size="3.2rem").classes(
                "text-blue-500 transition-transform duration-200 group-hover:scale-110"
            )
        _tile_bottom_labels(".. (Parent)", "Go up")


def _icon_tile_item(item: dict, is_shared: bool, share_name: str | None,
                    navigate_to: Callable, on_rename: Callable, on_delete: Callable) -> None:
    is_dir = item["is_dir"]
    tile = ui.element("div").props("v-ripple").classes(f"{_TILE_BASE} {_TILE_ITEM}")
    if is_dir:
        tile.on("click", lambda i=item: navigate_to(i["path"]))

    with tile:
        # Top-right 3-dots
        with ui.button(icon="more_vert").props("flat round color=grey-7").classes(
            "absolute top-1.5 right-1.5 z-10 w-9 h-9 "
            "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100 "
            "hover:bg-slate-100/90 dark:hover:bg-slate-800/90 transition-colors"
        ).on("click.stop", lambda: None):
            render_action_menu(item, is_shared, on_rename, on_delete)

        # Top badge slot (always h-6 for grid symmetry)
        if is_shared and share_name:
            with ui.row().classes("w-full h-6 items-center justify-center flex-nowrap shrink-0 px-8"):
                render_smb_badge(share_name, compact=True)
        else:
            ui.element("div").classes("w-full h-6 shrink-0")

        # Centre icon
        with ui.element("div").classes("flex-1 flex items-center justify-center my-auto py-1"):
            if is_dir:
                icon_name = "folder_shared" if is_shared else "folder"
                icon_color = "text-blue-600 dark:text-blue-400" if is_shared else "text-amber-500"
                ui.icon(icon_name, size="3.6rem").classes(
                    f"{icon_color} transition-transform duration-200 group-hover:scale-105"
                )
            else:
                ui.icon("description", size="3.2rem").classes(
                    "text-slate-400 transition-transform duration-200 group-hover:scale-105"
                )

        # Bottom labels
        subtitle = "Folder" if is_dir else f"File • {item['size_bytes'] / 1024:.1f} KB"
        _tile_bottom_labels(item["name"], subtitle)


def render_icons_view(
    items: list[dict],
    share_map: dict[Path, str],
    can_go_up: bool,
    parent: Path,
    navigate_to: Callable,
    on_rename: Callable,
    on_delete: Callable,
) -> None:
    with ui.element("div").classes(
        "w-full p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3.5"
    ):
        if can_go_up:
            _icon_tile_up(parent, navigate_to)

        for item in items:
            item_path = Path(item["path"]).resolve()
            is_dir = item["is_dir"]
            is_shared = is_dir and item_path in share_map
            share_name = share_map.get(item_path) if is_shared else None
            _icon_tile_item(item, is_shared, share_name, navigate_to, on_rename, on_delete)

    if not items and not can_go_up:
        with ui.row().classes("w-full p-8 items-center justify-center text-slate-400"):
            ui.label("This directory is empty.").classes("text-sm italic")
