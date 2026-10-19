from pathlib import Path
from nicegui import ui

from src.config import settings
from src.samba.backend import SambaBackend
from src.storage.dir_manager import StorageDirectoryManager
from src.ui.layout import page_layout


def create_storage_page(backend: SambaBackend, dir_manager: StorageDirectoryManager):
    with page_layout("Storage Explorer", backend) as authenticated:
        if not authenticated:
            return

        # 1. State for currently inspected directory
        current_path_state = {"path": str(Path(settings.parsed_storage_roots[0]).resolve())}

        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Explore files and folders within allowed storage roots").classes("text-sm text-slate-500")

            def open_new_folder_dialog():
                dialog = ui.dialog()
                with dialog, ui.card().classes("p-6 max-w-md w-full"):
                    ui.label("Create New Directory").classes("text-lg font-bold mb-3")
                    folder_name_input = ui.input("Directory Name").props("outlined dense").classes("w-full mb-4")

                    def execute_create():
                        name = folder_name_input.value.strip() if folder_name_input.value else ""
                        if not name:
                            ui.notify("Folder name is required.", type="warning")
                            return

                        target = Path(current_path_state["path"]) / name
                        try:
                            dir_manager.create_directory(str(target))
                            ui.notify(f"Created folder '{name}' successfully.", type="positive")
                            dialog.close()
                            render_directory_contents()
                        except PermissionError as err:
                            ui.notify(str(err), type="negative")

                    with ui.row().classes("justify-end gap-3 w-full"):
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                        ui.button("Create", on_click=execute_create).props("unelevated").classes("bg-blue-600 text-white")

                dialog.open()

            ui.button("New Folder", icon="create_new_folder", on_click=open_new_folder_dialog).props("unelevated").classes("bg-blue-600 text-white rounded-lg")

        # 2. Path navigation bar
        path_label = ui.label(current_path_state["path"]).classes("text-xs font-mono bg-slate-100 dark:bg-slate-800 p-3 rounded-lg w-full border border-slate-200 dark:border-slate-700")

        # 3. Directory listing container
        table_container = ui.column().classes("w-full mt-2")

        def navigate_to(new_path: str):
            current_path_state["path"] = new_path
            path_label.set_text(new_path)
            render_directory_contents()

        def render_directory_contents():
            table_container.clear()
            try:
                items = dir_manager.list_directory(current_path_state["path"])
            except Exception as err:
                ui.notify(f"Cannot read directory: {err}", type="negative")
                items = []

            with table_container:
                # Parent directory button if not at absolute storage root
                curr = Path(current_path_state["path"])
                parent = curr.parent

                from src.core.security import is_path_safe
                allowed = [Path(r) for r in settings.parsed_storage_roots]
                if is_path_safe(parent, allowed) and curr != parent:
                    with ui.row().classes("items-center gap-2 p-2 hover:bg-slate-50 dark:hover:bg-slate-800 cursor-pointer w-full rounded").on("click", lambda p=parent: navigate_to(str(p))):
                        ui.icon("arrow_upward", size="1.2rem").classes("text-blue-500")
                        ui.label(".. (Up to parent directory)").classes("text-sm font-medium text-blue-600")

                if not items:
                    ui.label("This directory is empty.").classes("text-sm text-slate-400 italic py-4")
                    return

                for item in items:
                    with ui.row().classes("items-center justify-between p-3 border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 w-full"):
                        with ui.row().classes("items-center gap-3"):
                            if item["is_dir"]:
                                with ui.row().classes("items-center gap-3 cursor-pointer").on("click", lambda i=item: navigate_to(i["path"])):
                                    ui.icon("folder", size="1.5rem").classes("text-amber-500")
                                    ui.label(item["name"]).classes("text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline")
                            else:
                                ui.icon("description", size="1.5rem").classes("text-slate-400")
                                ui.label(item["name"]).classes("text-sm text-slate-700 dark:text-slate-200")

                        with ui.row().classes("items-center gap-4 text-xs text-slate-400"):
                            if not item["is_dir"]:
                                size_kb = item["size_bytes"] / 1024
                                ui.label(f"{size_kb:.1f} KB")
                            else:
                                ui.label("Directory")

        render_directory_contents()
