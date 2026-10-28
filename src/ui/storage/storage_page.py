from pathlib import Path
from nicegui import ui

from src.core.security import is_path_safe
from src.samba.backend import SambaBackend
from src.storage.dir_manager import StorageDirectoryManager

from src.ui.layout import page_layout, render_page_header
from src.ui.storage.storage_components import render_icons_view, render_list_view
from src.ui.storage.storage_dialogs import (
    open_delete_dialog,
    open_new_folder_dialog,
    open_rename_dialog,
)


def create_storage_page(backend: SambaBackend, dir_manager: StorageDirectoryManager):
    with page_layout("Storage Explorer", backend, show_title=False) as authenticated:
        if not authenticated:
            return

        render_page_header(
            "Storage Explorer",
            "Explore files and folders within allowed storage roots.",
        )

        # ── One independent folder browser per allowed storage root ──────────
        for root in dir_manager.allowed_roots:
            _render_storage_browser(root, backend, dir_manager)


def _render_storage_browser(
    root: str,
    backend: SambaBackend,
    dir_manager: StorageDirectoryManager,
) -> None:
    """Render a self-contained folder browser card for one allowed storage root."""
    root_path = Path(root).resolve()

    # 1. Browser state is scoped to this root, so each card navigates independently
    state = {
        "path": str(root_path),
        "mode": "list",
    }

    # 2. Reuse the existing storage card design (toolbar + content area)
    with ui.card().props("flat bordered").classes(
        "w-full p-0 gap-y-0 rounded-xl overflow-hidden border border-slate-200"
        "dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm"
    ):
        # ── Integrated toolbar: path display + mode switch + new folder ──
        with ui.row().classes(
            "w-full items-center justify-between px-4 py-2.5 "
            "bg-slate-50 dark:bg-slate-800/60 "
            "border-b border-slate-200 dark:border-slate-700 gap-3 flex-wrap"
        ):
            # Left: current path
            with ui.row().classes("items-center gap-2 flex-1 min-w-0 font-mono text-xs"):
                ui.icon("folder_open", size="1.35rem").classes(
                    "text-blue-600 dark:text-blue-400 shrink-0"
                )
                path_label = ui.label(state["path"]).classes(
                    "text-slate-700 dark:text-slate-200 truncate select-all"
                )

            # Right: mode toggle + new folder button
            with ui.row().classes(
                "items-center gap-2 w-full sm:w-auto shrink-0 "
                "justify-between sm:justify-end"
            ):
                # Segmented toggle
                with ui.row().classes(
                    "items-center p-0.5 bg-slate-200/70 dark:bg-slate-700/60 "
                    "rounded-lg border border-slate-300/50 dark:border-slate-600/50 gap-0.5"
                ):
                    list_btn = (
                        ui.button(icon="view_list", on_click=lambda: _switch_mode("list"))
                        .props("dense flat no-caps")
                        .classes("rounded-md px-1.5 py-0.5 sm:px-2.5 sm:py-1")
                        .tooltip("List view")
                    )
                    icons_btn = (
                        ui.button(icon="grid_view", on_click=lambda: _switch_mode("icons"))
                        .props("dense flat no-caps")
                        .classes("rounded-md px-1.5 py-0.5 sm:px-2.5 sm:py-1")
                        .tooltip("Icons view")
                    )

                # New folder button
                ui.button("New Folder", icon="create_new_folder", on_click=lambda: _open_new_folder())\
                    .props("unelevated dense no-caps color=primary")\
                    .classes("rounded-lg px-2 h-8 text-xs sm:px-3 sm:h-9 sm:text-sm shadow-sm")\
                    .tooltip("New folder")

        # ── Directory content ─────────────────────────────────────────────
        # Bounded, independently scrollable area so many folders / multiple
        # roots never push other browsers off-screen.
        content = ui.column().classes(
            "w-full p-0 gap-0 min-h-0 overflow-y-auto overscroll-contain "
            "max-h-[55vh] sm:max-h-[60vh] lg:max-h-[70vh]"
        )

    # ── Helpers / callbacks (all scoped to this browser) ──────────────────
    def _refresh():
        _update_toggle_styles()
        render_directory_contents()

    def _switch_mode(mode: str):
        state["mode"] = mode
        _refresh()

    def _open_new_folder():
        open_new_folder_dialog(
            state["path"], dir_manager, on_done=render_directory_contents
        )

    def _on_rename(item: dict, is_shared: bool):
        open_rename_dialog(
            item, is_shared, dir_manager, backend, on_done=render_directory_contents
        )

    def _on_delete(item: dict, is_shared: bool):
        open_delete_dialog(
            item, is_shared, dir_manager, backend, on_done=render_directory_contents
        )

    def _update_toggle_styles():
        is_list = state["mode"] == "list"
        active = "unelevated color=primary text-color=white"
        inactive = "flat color=grey-7"
        remove_active = "flat color=grey-7"
        remove_inactive = "unelevated color=primary text-color=white"

        list_btn.props(active if is_list else inactive,
                       remove=remove_active if is_list else remove_inactive)
        icons_btn.props(inactive if is_list else active,
                        remove=remove_inactive if is_list else remove_active)

    def navigate_to(new_path: str):
        try:
            target = Path(new_path).resolve()
        except (OSError, RuntimeError, ValueError):
            ui.notify("Invalid directory path.", type="negative")
            return

        # Keep each browser inside its own root, even when following symlinks
        if not is_path_safe(target, [root_path]):
            ui.notify("Cannot navigate outside this storage root.", type="negative")
            return

        state["path"] = str(target)
        path_label.set_text(str(target))
        render_directory_contents()

    def render_directory_contents():
        content.clear()
        try:
            items = dir_manager.list_directory(state["path"])
        except Exception as err:
            ui.notify(f"Cannot read directory: {err}", type="negative")
            items = []

        curr = Path(state["path"]).resolve()
        can_go_up = _can_navigate_up(curr, root_path)
        share_map = _build_share_map(backend)

        with content:
            if state["mode"] == "list":
                render_list_view(items, share_map, can_go_up, curr.parent,
                                 navigate_to, _on_rename, _on_delete)
            else:
                render_icons_view(items, share_map, can_go_up, curr.parent,
                                  navigate_to, _on_rename, _on_delete)

    # ── Initial render ────────────────────────────────────────────────────
    _update_toggle_styles()
    render_directory_contents()


def _build_share_map(backend: SambaBackend) -> dict[Path, str]:
    """Map each shared directory path to its Samba share name."""
    share_map: dict[Path, str] = {}
    for share in backend.list_shares():
        try:
            share_map[Path(share.path).resolve()] = share.name
        except (OSError, RuntimeError, ValueError):
            continue
    return share_map


def _can_navigate_up(current: Path, root: Path) -> bool:
    """Allow going up only while the parent is still inside this browser's root."""
    return current != root and is_path_safe(current.parent, [root])
