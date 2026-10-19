from pathlib import Path

from nicegui import ui

from src.config import settings
from src.core.security import is_path_safe
from src.samba.backend import SambaBackend
from src.storage.dir_manager import StorageDirectoryManager
from src.ui.layout import page_layout
from src.ui.storage_components import render_icons_view, render_list_view
from src.ui.storage_dialogs import (
    open_delete_dialog,
    open_new_folder_dialog,
    open_rename_dialog,
)


def create_storage_page(backend: SambaBackend, dir_manager: StorageDirectoryManager):
    with page_layout("Storage Explorer", backend) as authenticated:
        if not authenticated:
            return

        # ── State ────────────────────────────────────────────────────────────
        state = {
            "path": str(Path(settings.parsed_storage_roots[0]).resolve()),
            "mode": "list",
        }

        # ── Page header (description only) ───────────────────────────────────
        ui.label("Explore files and folders within allowed storage roots").classes(
            "text-sm text-slate-500 mb-3"
        )

        # ── Main card (path bar + content, unified border) ────────────────────
        with ui.card().props("flat bordered").classes(
            "w-full p-0 rounded-xl overflow-hidden border border-slate-200 "
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
                            .classes("rounded-md px-2.5 py-1")
                            .tooltip("List view")
                        )
                        icons_btn = (
                            ui.button(icon="grid_view", on_click=lambda: _switch_mode("icons"))
                            .props("dense flat no-caps")
                            .classes("rounded-md px-2.5 py-1")
                            .tooltip("Icons view")
                        )

                    # New folder button
                    ui.button("New Folder", icon="create_new_folder", on_click=lambda: _open_new_folder())\
                        .props("unelevated dense no-caps color=primary")\
                        .classes("rounded-lg px-3 h-9 shadow-sm")\
                        .tooltip("New folder")

            # ── Directory content ─────────────────────────────────────────────
            content = ui.column().classes("w-full p-0 gap-0")

        # ── Helpers / callbacks ───────────────────────────────────────────────
        def _refresh():
            _update_toggle_styles()
            render_directory_contents()

        def _switch_mode(mode: str):
            state["mode"] = mode
            _refresh()

        def _open_new_folder():
            open_new_folder_dialog(state["path"], dir_manager, on_done=render_directory_contents)

        def _on_rename(item: dict, is_shared: bool):
            open_rename_dialog(item, is_shared, dir_manager, backend, on_done=render_directory_contents)

        def _on_delete(item: dict, is_shared: bool):
            open_delete_dialog(item, is_shared, dir_manager, backend, on_done=render_directory_contents)

        def _update_toggle_styles():
            is_list = state["mode"] == "list"
            active   = "unelevated color=primary text-color=white"
            inactive = "flat color=grey-7"
            remove_active   = "flat color=grey-7"
            remove_inactive = "unelevated color=primary text-color=white"

            list_btn.props(active if is_list else inactive,
                           remove=remove_active if is_list else remove_inactive)
            icons_btn.props(inactive if is_list else active,
                            remove=remove_inactive if is_list else remove_active)

        def navigate_to(new_path: str):
            state["path"] = new_path
            path_label.set_text(new_path)
            render_directory_contents()

        def render_directory_contents():
            content.clear()
            try:
                items = dir_manager.list_directory(state["path"])
            except Exception as err:
                ui.notify(f"Cannot read directory: {err}", type="negative")
                items = []

            shares = backend.list_shares()
            share_map: dict[Path, str] = {}
            for s in shares:
                try:
                    share_map[Path(s.path).resolve()] = s.name
                except Exception:
                    continue

            curr = Path(state["path"])
            parent = curr.parent
            allowed = [Path(r) for r in settings.parsed_storage_roots]
            can_go_up = is_path_safe(parent, allowed) and curr != parent

            with content:
                if state["mode"] == "list":
                    render_list_view(items, share_map, can_go_up, parent,
                                     navigate_to, _on_rename, _on_delete)
                else:
                    render_icons_view(items, share_map, can_go_up, parent,
                                      navigate_to, _on_rename, _on_delete)

        # ── Initial render ────────────────────────────────────────────────────
        _update_toggle_styles()
        render_directory_contents()
