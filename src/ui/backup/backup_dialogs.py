"""Dialogs for the configuration history page."""

from typing import Callable
from nicegui import ui

from src.core.backup import BackupManager
from src.samba.backend import SambaBackend
from src.ui.backup.backup_components import render_diff


def open_undo_dialog(snapshot, previous, index, backup_manager: BackupManager, backend: SambaBackend, on_done: Callable) -> None:
    diff = backup_manager.get_undo_diff(snapshot.snapshot_id)
    discard_count = index + 1
    entries_word = "entry" if discard_count == 1 else "entries"
    dialog = ui.dialog()

    with dialog, ui.card().props("flat bordered").classes("w-full max-w-md p-6 rounded-xl"):
        ui.label(f'Undo "{snapshot.description}"?').classes("text-lg font-bold mb-2")
        ui.label(
            f"Restore configuration to the state before this change "
            f"({previous.created_at.strftime('%Y-%m-%d %H:%M:%S')}). "
            f"This permanently removes {discard_count} history {entries_word}."
        ).classes("text-sm text-gray-600 dark:text-gray-300 mb-4")

        if backup_manager.has_unrecorded_changes():
            ui.label("Warning: Unrecorded changes in the active configuration will be overwritten.").classes(
                "text-xs text-amber-600 font-medium mb-3"
            )

        if diff is not None:
            with ui.column().classes(
                "w-full max-h-48 overflow-auto border border-gray-200 dark:border-gray-700 "
                "rounded-lg p-3 mb-4 bg-gray-50 dark:bg-gray-900/60"
            ):
                render_diff(diff)

        def execute_undo():
            if backup_manager.undo_change(snapshot.snapshot_id):
                backend.reload_service()
                ui.notify(
                    f'Reverted "{snapshot.description}". {discard_count} history {entries_word} removed.',
                    type="positive",
                )
                dialog.close()
                on_done()
            else:
                ui.notify("Failed to undo. The previous state is missing or corrupt.", type="negative")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps color=grey-7")
            ui.button("Undo", on_click=execute_undo, icon="undo").props("unelevated no-caps color=primary")

    dialog.open()
