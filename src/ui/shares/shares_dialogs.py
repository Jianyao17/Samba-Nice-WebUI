"""Dialogs for creating, editing, deleting, and browsing Samba shares."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional
from pydantic import ValidationError
from nicegui import ui

from src.config import settings
from src.core.models import ShareConfig
from src.core.security import is_path_safe
from src.samba.backend import SambaBackend
from src.samba.parser import sanitize_share_name
from src.storage.dir_manager import StorageDirectoryManager
from src.ui.shares.directory_tree import DirectoryTree


def open_directory_browser_dialog(
    current_path: str,
    dir_manager: StorageDirectoryManager,
    on_select: Callable[[str], None],
) -> None:
    """Open the lazy, expandable directory tree and return the chosen folder."""
    dialog = ui.dialog()
    tree = DirectoryTree(dir_manager, initial_path=current_path)
    path_label: Optional[ui.label] = None
    select_button: Optional[ui.button] = None

    def sync_selection(path: Optional[str]) -> None:
        if path_label is not None:
            path_label.set_text(path or "No folder selected")
        if select_button is not None:
            if path:
                select_button.enable()
            else:
                select_button.disable()

    tree.on_select = sync_selection

    with dialog, ui.card().props("flat bordered").classes(
        "w-full max-w-2xl p-0 rounded-2xl overflow-hidden shadow-xl"
    ):
        # 1. Header with title, refresh, and close actions
        with ui.row().classes(
            "w-full items-center justify-between gap-2 px-4 sm:px-5 py-3 "
            "bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-700"
        ):
            with ui.row().classes("items-center gap-2 min-w-0 flex-1"):
                ui.icon("account_tree", size="1.4rem").classes(
                    "text-blue-600 dark:text-blue-400 shrink-0"
                )
                ui.label("Browse Directory").classes(
                    "text-base font-bold text-slate-800 dark:text-slate-100 truncate"
                )

            with ui.row().classes("items-center gap-1 shrink-0"):
                ui.button(icon="refresh", on_click=lambda: tree.refresh()).props(
                    "flat round dense color=grey-7"
                ).tooltip("Refresh tree")
                ui.button(icon="close", on_click=dialog.close).props(
                    "flat round dense color=grey-7"
                ).tooltip("Close")

        # 2. Tree body
        with ui.column().classes("w-full px-4 sm:px-5 py-3 gap-2"):
            ui.label(
                "Expand folders to browse. Only directories inside the allowed storage roots are shown."
            ).classes("text-xs text-slate-500")
            tree.render()

        # 3. Footer — on mobile the selected path sits above the actions
        with ui.element("div").classes(
            "w-full flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 "
            "px-4 sm:px-5 py-3 bg-slate-50 dark:bg-slate-800/40 "
            "border-t border-slate-200 dark:border-slate-700"
        ):
            with ui.row().classes("items-center gap-2 mb-3 min-w-0 w-full sm:flex-1"):
                ui.icon("folder_open", size="1.1rem").classes("text-slate-400 shrink-0")
                path_label = ui.label("No folder selected").classes(
                    "text-xs font-mono text-slate-600 dark:text-slate-300 "
                    "break-all sm:truncate min-w-0"
                )

            with ui.row().classes("items-center gap-2 w-full sm:w-auto justify-end shrink-0"):
                ui.button("Cancel", on_click=dialog.close).props(
                    "flat no-caps color=grey-7"
                )
                select_button = ui.button(
                    "Select This Folder", icon="check", on_click=lambda: confirm_selection()
                ).props("unelevated no-caps color=primary").classes("rounded-lg")
                select_button.disable()

    def confirm_selection() -> None:
        selected = tree.selected_path
        if not selected:
            ui.notify("Select a folder first.", type="warning")
            return
        on_select(selected)
        dialog.close()

    # The tree may already have selected the initial path during render.
    sync_selection(tree.selected_path)
    dialog.open()


def open_share_dialog(
    share: Optional[ShareConfig],
    backend: SambaBackend,
    dir_manager: StorageDirectoryManager,
    on_saved: Callable,
) -> None:
    """Open the share editor for creation or editing/renaming."""
    is_edit = share is not None
    original_name = share.name if share is not None else None
    dialog = ui.dialog()

    with dialog, ui.card().props("flat bordered").classes(
        "w-full max-w-2xl p-0 rounded-2xl overflow-hidden shadow-xl"
    ):
        # 1. Dialog header — subtitle is hidden on mobile to keep one line
        with ui.row().classes(
            "w-full items-center justify-between gap-2 px-4 sm:px-6 py-3 "
            "bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-700"
        ):
            with ui.row().classes("items-center gap-2 min-w-0 flex-1"):
                ui.icon("edit" if is_edit else "create_new_folder", size="1.4rem").classes(
                    "text-blue-600 dark:text-blue-400 shrink-0"
                )
                with ui.column().classes("gap-0 min-w-0"):
                    ui.label("Edit Share" if is_edit else "New Samba Share").classes(
                        "text-base font-bold text-slate-800 dark:text-slate-100 truncate"
                    )
                    ui.label(
                        "Update the share name, target folder, and access rules."
                        if is_edit
                        else "Expose a folder inside the allowed storage roots."
                    ).classes("text-xs text-slate-500 hidden sm:block")

            ui.button(icon="close", on_click=dialog.close).props(
                "flat round dense color=grey-7"
            ).classes("shrink-0").tooltip("Close")

        # 2. Scrollable form body
        with ui.column().classes(
            "w-full px-4 sm:px-6 py-4 gap-3 max-h-[70vh] overflow-y-auto"
        ):
            name_input = ui.input(
                "Share Name", value=share.name if is_edit else ""
            ).props("outlined dense").classes("w-full")
            ui.label(
                "Allowed: letters, numbers, hyphen (-), underscore (_), and dot (.)."
            ).classes("text-xs text-slate-400 -mt-2")

            with ui.row().classes("w-full items-start gap-2 flex-wrap"):
                path_input = ui.input(
                    "Target Path",
                    value=share.path if is_edit else settings.parsed_storage_roots[0],
                ).props("outlined dense").classes("flex-1 min-w-[180px]")

                def browse_path() -> None:
                    open_directory_browser_dialog(
                        str(path_input.value or ""),
                        dir_manager,
                        on_select=lambda path: path_input.set_value(path),
                    )

                ui.button("Browse", icon="folder_open", on_click=browse_path).props(
                    "outline dense no-caps color=primary"
                ).classes("h-10 px-4").tooltip("Browse directories")

            ui.label(
                "The target folder must be inside an allowed storage root."
            ).classes("text-xs text-slate-400 -mt-2")

            comment_input = ui.input(
                "Comment", value=share.comment if is_edit else ""
            ).props("outlined dense").classes("w-full")

            with ui.row().classes("w-full items-center gap-6 flex-wrap"):
                read_only_check = ui.checkbox(
                    "Read Only", value=share.read_only if is_edit else False
                )
                browsable_check = ui.checkbox(
                    "Browseable", value=share.browsable if is_edit else True
                )
                guest_ok_check = ui.checkbox(
                    "Guest OK", value=share.guest_ok if is_edit else False
                )

            valid_users_input = ui.input(
                "Valid Users (optional)", value=share.valid_users if is_edit else ""
            ).props("outlined dense").classes("w-full")
            write_list_input = ui.input(
                "Write List (optional)", value=share.write_list if is_edit else ""
            ).props("outlined dense").classes("w-full")

            if is_edit:
                ui.label(
                    "Changing the name renames the SMB share only; the target folder is not renamed."
                ).classes("text-xs text-amber-600 dark:text-amber-400")

        # 3. Action footer
        with ui.row().classes(
            "w-full justify-end gap-2 px-4 sm:px-6 py-3 "
            "bg-slate-50 dark:bg-slate-800/40 border-t border-slate-200 dark:border-slate-700"
        ):
            ui.button("Cancel", on_click=dialog.close).props(
                "flat no-caps color=grey-7"
            )
            ui.button("Save & Apply", icon="save", on_click=lambda: save_share_data()).props(
                "unelevated no-caps color=primary"
            ).classes("rounded-lg")

    def save_share_data() -> None:
        name_val = (name_input.value or "").strip()
        path_val = (path_input.value or "").strip()

        if not name_val or not path_val:
            ui.notify("Share name and target path are required.", type="warning")
            return

        # 1. Validate the section name before constructing the model
        try:
            clean_name = sanitize_share_name(name_val)
        except ValueError as exc:
            ui.notify(str(exc), type="negative")
            return

        if clean_name != name_val:
            ui.notify(
                "Share name may only contain letters, numbers, '-', '_' and '.'.",
                type="warning",
            )
            return

        if len(clean_name) > 64:
            ui.notify("Share name cannot be longer than 64 characters.", type="warning")
            return

        # 2. Verify the target path is safe and usable
        target_path = Path(path_val)
        allowed_roots = [Path(root) for root in settings.parsed_storage_roots]
        if not is_path_safe(target_path, allowed_roots):
            ui.notify(
                f"Target path '{path_val}' is outside allowed storage roots.",
                type="negative",
            )
            return

        try:
            if target_path.exists():
                if not target_path.is_dir():
                    ui.notify(
                        f"Target path '{path_val}' is not a directory.",
                        type="negative",
                    )
                    return
            else:
                dir_manager.create_directory(str(target_path))
        except (PermissionError, OSError, ValueError) as exc:
            ui.notify(f"Could not prepare target directory: {exc}", type="negative")
            return

        # 3. Build the model and submit the create/update/rename request
        try:
            new_share = ShareConfig(
                name=clean_name,
                path=path_val,
                comment=comment_input.value or "",
                read_only=read_only_check.value,
                browsable=browsable_check.value,
                guest_ok=guest_ok_check.value,
                valid_users=valid_users_input.value or "",
                write_list=write_list_input.value or "",
                extra_options=dict(share.extra_options) if is_edit else {},
                conf_file=settings.samba_include_conf_path.name,
            )
        except (ValidationError, ValueError) as exc:
            ui.notify(f"Invalid share configuration: {exc}", type="negative")
            return

        try:
            result = backend.save_share(new_share, original_name=original_name)
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            ui.notify(f"Failed to save share: {exc}", type="negative")
            return

        if result.is_valid:
            ui.notify(result.message, type="positive")
            dialog.close()
            on_saved()
        else:
            ui.notify(result.message, type="negative")

    dialog.open()


def open_delete_dialog(
    share: ShareConfig,
    backend: SambaBackend,
    on_done: Callable,
) -> None:
    """Confirm and delete a share configuration."""
    dialog = ui.dialog()

    with dialog, ui.card().props("flat bordered").classes(
        "p-6 max-w-md w-full rounded-2xl shadow-xl"
    ):
        with ui.row().classes("items-center gap-3 mb-2"):
            ui.icon("warning", size="2rem").classes("text-red-500 shrink-0")
            ui.label(f"Delete Share '{share.name}'?").classes(
                "text-lg font-bold text-red-600 dark:text-red-400"
            )

        ui.label(
            "This removes the share configuration and reloads Samba. "
            "Files in the target folder are NOT deleted."
        ).classes("text-sm text-slate-500 mb-4")

        with ui.column().classes(
            "w-full gap-1 mb-4 p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 "
            "border border-slate-200 dark:border-slate-700"
        ):
            ui.label(f"Name: {share.name}").classes(
                "text-xs font-mono text-slate-700 dark:text-slate-200 break-all"
            )
            ui.label(f"Path: {share.path}").classes(
                "text-xs font-mono text-slate-500 dark:text-slate-400 break-all"
            )

        def execute_delete() -> None:
            try:
                success = backend.delete_share(share.name)
            except Exception as exc:  # pragma: no cover - defensive UI boundary
                ui.notify(f"Delete failed: {exc}", type="negative")
                return

            if success:
                ui.notify(f"Share '{share.name}' deleted successfully.", type="positive")
                dialog.close()
                on_done()
            else:
                ui.notify(
                    f"Failed to delete share '{share.name}'. It may no longer exist.",
                    type="negative",
                )

        with ui.row().classes("w-full justify-end gap-2 pt-2"):
            ui.button("Cancel", on_click=dialog.close).props(
                "flat no-caps color=grey-7"
            )
            ui.button("Delete", icon="delete", on_click=execute_delete).props(
                "unelevated no-caps color=negative"
            ).classes("rounded-lg")

    dialog.open()
