from nicegui import ui

from src.core.backup import BackupManager
from src.samba.backend import SambaBackend
from src.ui.layout import page_layout


def create_backup_page(backend: SambaBackend, backup_manager: BackupManager):
    with page_layout("Backups & Rollback", backend) as authenticated:
        if not authenticated:
            return

        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Review configuration snapshots and restore previous working states").classes("text-sm text-slate-500")

            def handle_create_manual_backup():
                snapshot = backup_manager.create_snapshot("Manual user snapshot")
                ui.notify(f"Created snapshot '{snapshot.snapshot_id}' successfully.", type="positive")
                refresh_backup_list()

            ui.button("Create Backup Now", icon="backup", on_click=handle_create_manual_backup).props("unelevated").classes("bg-blue-600 text-white rounded-lg")

        backup_container = ui.column().classes("w-full gap-4 mt-2")

        def refresh_backup_list():
            backup_container.clear()
            snapshots = backup_manager.list_snapshots()

            with backup_container:
                if not snapshots:
                    with ui.card().classes("w-full p-8 text-center text-slate-400 border border-dashed border-slate-300 dark:border-slate-700"):
                        ui.icon("history_toggle_off", size="3rem").classes("mx-auto text-slate-300 dark:text-slate-600 mb-2")
                        ui.label("No configuration backups found.").classes("font-medium")
                        ui.label("Snapshots are automatically recorded whenever shares are saved or deleted.").classes("text-xs mt-1")
                    return

                for snap in snapshots:
                    with ui.card().classes("w-full p-5 shadow-sm border border-slate-200 dark:border-slate-800"):
                        with ui.row().classes("items-center justify-between w-full"):
                            with ui.row().classes("items-center gap-3"):
                                ui.icon("inventory_2", size="1.8rem").classes("text-emerald-500")
                                with ui.column().classes("gap-0"):
                                    ui.label(snap.snapshot_id).classes("text-base font-bold text-slate-800 dark:text-slate-100")
                                    ui.label(snap.created_at.strftime("%Y-%m-%d %H:%M:%S")).classes("text-xs text-slate-400")

                            with ui.row().classes("items-center gap-2"):
                                ui.button("Rollback", icon="restore", on_click=lambda s=snap: confirm_restore(s)).props("flat dense text-color=blue").tooltip("Restore this snapshot")
                                ui.button(icon="delete", on_click=lambda s=snap: confirm_delete(s)).props("flat round dense text-color=red").tooltip("Delete snapshot")

                        with ui.row().classes("w-full mt-3 pt-3 border-t border-slate-100 dark:border-slate-800 items-center justify-between text-xs text-slate-500"):
                            ui.label(snap.description).classes("italic")
                            ui.label(f"{len(snap.files)} file(s): " + ", ".join(snap.files[:3]) + ("..." if len(snap.files) > 3 else ""))

        def confirm_restore(snapshot):
            dialog = ui.dialog()
            with dialog, ui.card().classes("p-6 max-w-md"):
                ui.label(f"Restore Snapshot '{snapshot.snapshot_id}'?").classes("text-lg font-bold text-blue-600 mb-2")
                ui.label("All current share configurations will be rolled back to this snapshot, and the Samba service will be reloaded.").classes("text-sm text-slate-500 mb-4")

                def execute_restore():
                    success = backup_manager.restore_snapshot(snapshot.snapshot_id)
                    if success:
                        backend.reload_service()
                        ui.notify(f"Restored snapshot '{snapshot.snapshot_id}' and reloaded Samba.", type="positive")
                        dialog.close()
                        refresh_backup_list()
                    else:
                        ui.notify("Failed to restore snapshot.", type="negative")

                with ui.row().classes("justify-end gap-3 w-full"):
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                    ui.button("Confirm Rollback", on_click=execute_restore).props("unelevated").classes("bg-blue-600 text-white")

            dialog.open()

        def confirm_delete(snapshot):
            dialog = ui.dialog()
            with dialog, ui.card().classes("p-6 max-w-md"):
                ui.label("Delete Backup Snapshot?").classes("text-lg font-bold text-red-600 mb-2")
                ui.label(f"Are you sure you want to delete snapshot '{snapshot.snapshot_id}'?").classes("text-sm text-slate-500 mb-4")

                def execute_delete():
                    backup_manager.delete_snapshot(snapshot.snapshot_id)
                    ui.notify("Snapshot deleted.", type="positive")
                    dialog.close()
                    refresh_backup_list()

                with ui.row().classes("justify-end gap-3 w-full"):
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                    ui.button("Delete", on_click=execute_delete).props("unelevated").classes("bg-red-600 text-white")

            dialog.open()

        refresh_backup_list()
