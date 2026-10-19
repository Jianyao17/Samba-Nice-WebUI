from nicegui import ui

from src.core.backup import BackupManager
from src.samba.backend import SambaBackend
from src.ui.backup.backup_components import (
    render_drift_banner,
    render_empty_history,
    render_history_entry,
)
from src.ui.backup.backup_dialogs import open_undo_dialog
from src.ui.layout import page_layout


def create_backup_page(backend: SambaBackend, backup_manager: BackupManager):
    with page_layout("Configuration History", backend) as authenticated:
        if not authenticated:
            return

        ui.label(
            "Review configuration changes and undo them. Click any entry to inspect change details."
        ).classes("text-sm text-gray-500 mb-2")

        history_container = ui.column().classes("w-full gap-2.5")

        def confirm_undo(snapshot, previous, index):
            open_undo_dialog(
                snapshot, previous, index, backup_manager, backend, refresh_history
            )

        def refresh_history():
            history_container.clear()
            snapshots = backup_manager.list_snapshots()
            drift = backup_manager.has_unrecorded_changes()

            with history_container:
                if drift:
                    render_drift_banner()

                if not snapshots:
                    render_empty_history()
                    return

                for index, snap in enumerate(snapshots):
                    previous = snapshots[index + 1] if index + 1 < len(snapshots) else None
                    diff = backup_manager.get_previous_diff(snap.snapshot_id) if previous else None
                    render_history_entry(snap, previous, index, diff, confirm_undo)

        refresh_history()
