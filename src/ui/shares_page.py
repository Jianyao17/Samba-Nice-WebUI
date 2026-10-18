from nicegui import ui

from src.config import settings
from src.core.models import ShareConfig
from src.core.security import is_path_safe
from src.samba.backend import SambaBackend
from src.storage.dir_manager import StorageDirectoryManager
from src.ui.layout import page_layout


def create_shares_page(backend: SambaBackend, dir_manager: StorageDirectoryManager):
    with page_layout("Share Configurations", backend) as authenticated:
        if not authenticated:
            return

        # 1. Action bar with Add Share button
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(f"Configure and manage Samba shares in {settings.samba_include_conf_path.name}").classes("text-sm text-slate-500")
            ui.button("Add Share", icon="add", on_click=lambda: open_share_dialog()).props("unelevated").classes("bg-blue-600 text-white rounded-lg")

        # 2. Container for share cards/table
        shares_container = ui.column().classes("w-full gap-4 mt-2")

        def refresh_shares():
            shares_container.clear()
            shares = backend.list_shares()

            with shares_container:
                if not shares:
                    with ui.card().classes("w-full p-8 text-center text-slate-400 border border-dashed border-slate-300 dark:border-slate-700"):
                        ui.icon("folder_off", size="3rem").classes("mx-auto text-slate-300 dark:text-slate-600 mb-2")
                        ui.label("No Samba shares configured yet.").classes("font-medium")
                        ui.label("Click 'Add Share' above to configure your first share.").classes("text-xs mt-1")
                    return

                for share in shares:
                    with ui.card().classes("w-full p-5 shadow-sm border border-slate-200 dark:border-slate-800"):
                        with ui.row().classes("items-center justify-between w-full"):
                            # Share title and badges
                            with ui.row().classes("items-center gap-3"):
                                ui.icon("folder", size="1.8rem").classes("text-blue-500")
                                with ui.column().classes("gap-0"):
                                    ui.label(share.name).classes("text-lg font-bold text-slate-800 dark:text-slate-100")
                                    ui.label(share.path).classes("text-xs font-mono text-slate-400")

                            # Action buttons
                            with ui.row().classes("items-center gap-2"):
                                ui.button(icon="edit", on_click=lambda s=share: open_share_dialog(s)).props("flat round dense").tooltip("Edit Share")
                                ui.button(icon="delete", on_click=lambda s=share: confirm_delete(s)).props("flat round dense text-color=red").tooltip("Delete Share")

                        # Share configuration details
                        with ui.row().classes("w-full mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 items-center justify-between text-xs text-slate-500"):
                            with ui.row().classes("gap-4"):
                                ui.label(f"Comment: {share.comment or 'None'}").classes("italic")
                                ui.label(f"Access: {'Read-Only' if share.read_only else 'Read/Write'}")
                                ui.label(f"Browsable: {'Yes' if share.browsable else 'No'}")
                                ui.label(f"Guest Access: {'Allowed' if share.guest_ok else 'Denied'}")
                                if share.valid_users:
                                    ui.label(f"Users: {share.valid_users}")

                            ui.badge(share.conf_file or "modular", color="secondary").props("outline")

        # 3. Share editor modal dialog
        def open_share_dialog(share: ShareConfig | None = None):
            is_edit = share is not None
            dialog = ui.dialog()

            with dialog, ui.card().classes("w-full max-w-lg p-6 rounded-xl"):
                ui.label("Edit Share" if is_edit else "New Samba Share").classes("text-xl font-bold mb-4")

                # Form fields
                name_input = ui.input("Share Name", value=share.name if is_edit else "").props("outlined dense").classes("w-full mb-3")
                if is_edit:
                    name_input.disable()  # Prevent changing section name on edit

                path_input = ui.input("Target Path", value=share.path if is_edit else settings.parsed_storage_roots[0]).props("outlined dense").classes("w-full mb-3")
                comment_input = ui.input("Comment", value=share.comment if is_edit else "").props("outlined dense").classes("w-full mb-3")

                with ui.row().classes("gap-6 mb-3"):
                    read_only_check = ui.checkbox("Read Only", value=share.read_only if is_edit else False)
                    browsable_check = ui.checkbox("Browsable", value=share.browsable if is_edit else True)
                    guest_ok_check = ui.checkbox("Guest OK", value=share.guest_ok if is_edit else False)

                valid_users_input = ui.input("Valid Users (optional)", value=share.valid_users if is_edit else "").props("outlined dense").classes("w-full mb-3")
                write_list_input = ui.input("Write List (optional)", value=share.write_list if is_edit else "").props("outlined dense").classes("w-full mb-4")

                # Submission handler
                def save_share_data():
                    name_val = name_input.value.strip() if name_input.value else ""
                    path_val = path_input.value.strip() if path_input.value else ""

                    if not name_val or not path_val:
                        ui.notify("Share name and target path are required.", type="warning")
                        return

                    # Verify path security against allowed roots
                    from pathlib import Path
                    allowed = [Path(r) for r in settings.parsed_storage_roots]
                    if not is_path_safe(Path(path_val), allowed):
                        ui.notify(f"Target path '{path_val}' is outside allowed storage roots!", type="negative")
                        return

                    # Create directory if it does not exist yet
                    dir_manager.create_directory(path_val)

                    new_share = ShareConfig(
                        name=name_val,
                        path=path_val,
                        comment=comment_input.value or "",
                        read_only=read_only_check.value,
                        browsable=browsable_check.value,
                        guest_ok=guest_ok_check.value,
                        valid_users=valid_users_input.value or "",
                        write_list=write_list_input.value or "",
                        conf_file=settings.samba_include_conf_path.name
                    )

                    result = backend.save_share(new_share)
                    if result.is_valid:
                        ui.notify(result.message, type="positive")
                        dialog.close()
                        refresh_shares()
                    else:
                        ui.notify(f"Configuration rejected by testparm: {result.message}", type="negative")

                with ui.row().classes("justify-end gap-3 w-full mt-2"):
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                    ui.button("Save & Apply", on_click=save_share_data).props("unelevated").classes("bg-blue-600 text-white")

            dialog.open()

        # 4. Delete confirmation modal
        def confirm_delete(share: ShareConfig):
            dialog = ui.dialog()
            with dialog, ui.card().classes("p-6 max-w-md"):
                ui.label(f"Delete Share '{share.name}'?").classes("text-lg font-bold text-red-600 mb-2")
                ui.label("This will remove the share configuration and signal Samba to reload. Files in the storage directory will NOT be deleted.").classes("text-sm text-slate-500 mb-4")

                def execute_delete():
                    success = backend.delete_share(share.name)
                    if success:
                        ui.notify(f"Share '{share.name}' deleted successfully.", type="positive")
                        dialog.close()
                        refresh_shares()
                    else:
                        ui.notify(f"Failed to delete share '{share.name}'.", type="negative")

                with ui.row().classes("justify-end gap-3 w-full"):
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                    ui.button("Delete", on_click=execute_delete).props("unelevated text-color=white").classes("bg-red-600")

            dialog.open()

        # Initial render of shares list
        refresh_shares()
