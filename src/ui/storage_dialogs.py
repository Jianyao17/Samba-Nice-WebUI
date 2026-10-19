from pathlib import Path
from typing import Callable

from nicegui import ui

from src.samba.backend import SambaBackend
from src.storage.dir_manager import StorageDirectoryManager


def open_rename_dialog(
    item: dict,
    is_shared: bool,
    dir_manager: StorageDirectoryManager,
    backend: SambaBackend,
    on_done: Callable,
) -> None:
    if is_shared:
        ui.notify(
            f"Cannot rename '{item['name']}' — it is actively shared in Samba. "
            "Remove or edit the share first.",
            type="warning",
        )
        return

    dialog = ui.dialog()
    with dialog, ui.card().props("flat bordered").classes("p-6 max-w-md w-full rounded-2xl shadow-xl"):
        ui.label(f"Rename {'Folder' if item['is_dir'] else 'File'}").classes("text-lg font-bold mb-3")
        name_input = (
            ui.input("New Name", value=item["name"])
            .props("outlined dense autofocus")
            .classes("w-full mb-4")
        )

        def execute_rename():
            new_name = (name_input.value or "").strip()
            if not new_name:
                ui.notify("Name cannot be empty.", type="warning")
                return
            if new_name == item["name"]:
                dialog.close()
                return
            try:
                dir_manager.rename_directory(item["path"], new_name, backend=backend)
                ui.notify(f"Renamed '{item['name']}' → '{new_name}'.", type="positive")
                dialog.close()
                on_done()
            except (PermissionError, FileExistsError, ValueError) as err:
                ui.notify(str(err), type="negative")
            except Exception as err:
                ui.notify(f"Rename failed: {err}", type="negative")

        with ui.row().classes("justify-end gap-3 w-full pt-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps color=grey-7")
            ui.button("Rename", on_click=execute_rename).props("unelevated no-caps color=primary").classes("rounded-lg")

    dialog.open()


def open_delete_dialog(
    item: dict,
    is_shared: bool,
    dir_manager: StorageDirectoryManager,
    backend: SambaBackend,
    on_done: Callable,
) -> None:
    if is_shared:
        ui.notify(
            f"Cannot delete '{item['name']}' — it is actively shared in Samba. "
            "Remove or edit the share first.",
            type="warning",
        )
        return

    dialog = ui.dialog()
    with dialog, ui.card().props("flat bordered").classes("p-6 max-w-md w-full rounded-2xl shadow-xl"):
        with ui.row().classes("items-center gap-3 mb-2"):
            ui.icon("warning", size="2rem").classes("text-red-500 shrink-0")
            ui.label(f"Delete {'Folder' if item['is_dir'] else 'File'}").classes(
                "text-lg font-bold text-red-600 dark:text-red-400"
            )

        ui.label(f"Are you sure you want to permanently delete '{item['name']}'?").classes(
            "text-base text-slate-700 dark:text-slate-200 mb-2 font-medium"
        )
        desc = (
            "This will permanently delete this folder and all its contents. This action cannot be undone."
            if item["is_dir"]
            else "This file will be permanently deleted. This action cannot be undone."
        )
        ui.label(desc).classes("text-sm text-slate-500 mb-4")

        def execute_delete():
            try:
                dir_manager.delete_directory(item["path"], backend=backend)
                ui.notify(f"Deleted '{item['name']}' successfully.", type="positive")
                dialog.close()
                on_done()
            except PermissionError as err:
                ui.notify(str(err), type="negative")
            except Exception as err:
                ui.notify(f"Delete failed: {err}", type="negative")

        with ui.row().classes("justify-end gap-3 w-full pt-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps color=grey-7")
            ui.button("Delete", on_click=execute_delete).props("unelevated no-caps color=negative").classes("rounded-lg")

    dialog.open()


def open_new_folder_dialog(
    current_path: str,
    dir_manager: StorageDirectoryManager,
    on_done: Callable,
) -> None:
    dialog = ui.dialog()
    with dialog, ui.card().props("flat bordered").classes("p-6 max-w-md w-full rounded-2xl shadow-xl"):
        ui.label("Create New Directory").classes("text-lg font-bold mb-3")
        folder_input = (
            ui.input("Directory Name")
            .props("outlined dense autofocus")
            .classes("w-full mb-4")
        )

        def execute_create():
            name = (folder_input.value or "").strip()
            if not name:
                ui.notify("Folder name is required.", type="warning")
                return
            try:
                dir_manager.create_directory(str(Path(current_path) / name))
                ui.notify(f"Created folder '{name}' successfully.", type="positive")
                dialog.close()
                on_done()
            except PermissionError as err:
                ui.notify(str(err), type="negative")

        with ui.row().classes("justify-end gap-3 w-full pt-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps color=grey-7")
            ui.button("Create", on_click=execute_create).props("unelevated no-caps color=primary").classes("rounded-lg")

    dialog.open()
