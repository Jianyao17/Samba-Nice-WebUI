from nicegui import ui

from src.core.backup import BackupManager
from src.core.config_diff import ShareDiff
from src.samba.backend import SambaBackend
from src.ui.layout import page_layout


def create_backup_page(backend: SambaBackend, backup_manager: BackupManager):
    with page_layout("Configuration History", backend) as authenticated:
        if not authenticated:
            return

        ui.label(
            "Review configuration changes and undo them. Click any entry to inspect change details."
        ).classes("text-sm text-gray-500 mb-2")

        history_container = ui.column().classes("w-full gap-2.5")

        def change_total(diff: ShareDiff | None) -> int:
            if diff is None:
                return 0
            return (
                len(diff.added)
                + len(diff.removed)
                + sum(len(changes) for changes in diff.modified.values())
            )

        def render_diff(diff: ShareDiff):
            with ui.column().classes("w-full gap-1.5"):
                if diff.added:
                    ui.label(f"Added shares: {', '.join(diff.added)}").classes(
                        "text-sm font-medium text-green-600 dark:text-green-400"
                    )

                if diff.removed:
                    ui.label(f"Removed shares: {', '.join(diff.removed)}").classes(
                        "text-sm font-medium text-red-600 dark:text-red-400"
                    )

                if diff.modified:
                    for share_name, changes in diff.modified.items():
                        with ui.column().classes("w-full gap-0.5"):
                            ui.label(f"Share [{share_name}]:").classes(
                                "text-sm font-bold text-slate-800 dark:text-slate-100"
                            )
                            for field_name, (before, after) in changes.items():
                                with ui.row().classes("items-center gap-2 pl-4 text-sm font-mono leading-normal"):
                                    ui.label(f"{field_name}:").classes("text-gray-600 dark:text-gray-300 shrink-0")
                                    ui.label(before or "(empty)").classes("text-red-500 line-through")
                                    ui.label("→").classes("text-gray-400 shrink-0")
                                    ui.label(after or "(empty)").classes("text-green-600 font-semibold")

                if diff.is_empty:
                    ui.label("No share definitions were changed.").classes("text-sm italic text-gray-400")

                if diff.file_changed:
                    ui.label("File formatting or whitespace was modified.").classes("text-sm text-gray-400")

        def refresh_history():
            history_container.clear()
            snapshots = backup_manager.list_snapshots()
            drift = backup_manager.has_unrecorded_changes()

            with history_container:
                # 1. Configuration drift alert banner
                if drift:
                    with ui.card().props("flat bordered").classes(
                        "w-full p-3.5 border-amber-300 bg-amber-50 dark:bg-amber-950/20"
                    ):
                        ui.label(
                            "Warning: Active configuration differs from latest snapshot. "
                            "It may have been edited manually; the next save/delete action will record a checkpoint."
                        ).classes("text-xs sm:text-sm text-amber-800 dark:text-amber-200")

                # 2. Empty state
                if not snapshots:
                    with ui.card().props("flat bordered").classes("w-full p-8 text-center text-gray-400 border border-dashed"):
                        ui.icon("history_toggle_off", size="3rem").classes("mx-auto mb-2 text-gray-300")
                        ui.label("No history records yet.").classes("font-semibold text-gray-600 dark:text-gray-300")
                        ui.label("Changes will appear here when Samba shares are added, updated, or removed.").classes(
                            "text-xs text-gray-400 mt-1"
                        )
                    return

                # 3. Material UI Expansion Cards
                for index, snap in enumerate(snapshots):
                    previous = snapshots[index + 1] if index + 1 < len(snapshots) else None
                    diff = backup_manager.get_previous_diff(snap.snapshot_id) if previous else None
                    total = change_total(diff)
                    has_previous = previous is not None

                    # Native Quasar Expansion item: handles slide transition and single native chevron
                    exp = ui.expansion().classes(
                        "w-full border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden "
                        "bg-white dark:bg-slate-900 shadow-sm hover:shadow transition-all duration-200 "
                        "hover:bg-gray-100 dark:hover:bg-gray-800/60"
                    )

                    with exp:
                        # Custom Header Slot: Quasar will automatically append its single native chevron on the far right
                        with exp.add_slot("header"):
                            with ui.row().classes(
                                "w-full items-center justify-between py-2 sm:py-2.5 gap-3 select-none"
                            ):
                                # Left section: Icon + Title & Badges
                                with ui.row().classes("items-center gap-3 flex-1 min-w-0"):
                                    icon_name = "history" if has_previous else "bookmark"
                                    icon_color = "text-blue-600 dark:text-blue-400" if has_previous else "text-gray-400"
                                    ui.icon(icon_name, size="1.4rem").classes(f"{icon_color} shrink-0")

                                    with ui.column().classes("flex-1 min-w-0 gap-1"):
                                        # Line 1: Title + Status Badge
                                        with ui.row().classes("items-center gap-2 flex-wrap min-w-0"):
                                            ui.label(snap.description).classes(
                                                "text-xs sm:text-sm font-semibold text-slate-800 dark:text-slate-100 truncate"
                                            )
                                            if index == 0:
                                                ui.badge("Latest", color="positive").props("rounded").classes(
                                                    "text-[10px] px-1.5 py-0.5 shrink-0"
                                                )
                                            if previous is None:
                                                ui.badge("Starting point", color="grey").props("rounded").classes(
                                                    "text-[10px] px-1.5 py-0.5 shrink-0"
                                                )

                                        # Line 2: Timestamp + Badges group (stays together on mobile)
                                        with ui.row().classes(
                                            "w-full items-center gap-2 text-xs text-gray-500 dark:text-gray-400 flex-wrap min-w-0"
                                        ):
                                            ui.label(snap.created_at.strftime("%Y-%m-%d %H:%M:%S")).classes("shrink-0")

                                            # Group element for change and hash badges (filled design)
                                            with ui.row().classes("items-center gap-1.5 shrink-0"):
                                                if not has_previous or total == 0:
                                                    ui.badge("0 changes", color="grey-6").props("rounded").classes(
                                                        "text-[10px] px-2 py-0.5 text-white"
                                                    )
                                                elif diff is None:
                                                    ui.badge("No details", color="grey-6").props("rounded").classes(
                                                        "text-[10px] px-2 py-0.5 text-white"
                                                    )
                                                else:
                                                    label = f"{total} change{'s' if total != 1 else ''}"
                                                    ui.badge(label, color="warning").props("rounded").classes(
                                                        "text-[10px] px-2 py-0.5 font-medium text-white"
                                                    )

                                                if snap.file_hash:
                                                    ui.badge(f"#{snap.file_hash[:8]}", color="blue-grey-6").props("rounded").classes(
                                                        "font-mono text-[10px] px-2 py-0.5 text-white"
                                                    )

                                # Right section in header: Desktop-only Undo button (gt-xs = visible on desktop/tablet, hidden on mobile)
                                if has_previous:
                                    undo_btn = ui.button(
                                        "Undo",
                                        icon="undo",
                                    ).props("flat no-caps color=primary").classes("gt-xs rounded-lg")
                                    undo_btn.on(
                                        "click.stop",
                                        lambda s=snap, p=previous, i=index: confirm_undo(s, p, i),
                                    )
                                    undo_btn.tooltip("Revert configuration to before this change")

                        # Expandable Body with native Material UI slide transition
                        with ui.column().classes("w-full px-4 pb-4 pt-2 gap-3 bg-gray-50/50 dark:bg-gray-900/50"):
                            # Mobile-only Undo button (lt-sm = visible on mobile only, hidden on desktop)
                            if has_previous:
                                with ui.row().classes("w-full justify-end lt-sm pb-2 border-b border-gray-200 dark:border-gray-800"):
                                    ui.button(
                                        "Undo This Change",
                                        icon="undo",
                                        on_click=lambda s=snap, p=previous, i=index: confirm_undo(s, p, i),
                                    ).props("flat no-caps color=primary").classes("rounded-lg")

                            if previous is None:
                                ui.label(
                                    "Starting point of the recorded history. There is no earlier state to undo to."
                                ).classes("text-xs text-gray-500 italic")
                            elif diff is None:
                                ui.label("Change details are unavailable for this entry.").classes("text-xs text-amber-600")
                            else:
                                render_diff(diff)

                            # Bottom Technical Footer: Snapshot ID, Full SHA256, and Files
                            ui.separator()
                            with ui.column().classes("w-full gap-0.5 text-xs text-gray-500 dark:text-gray-400 font-mono"):
                                ui.label(f"Snapshot ID: {snap.snapshot_id}").classes("break-all")
                                if snap.file_hash:
                                    ui.label(f"Full SHA256: {snap.file_hash}").classes("break-all")
                                ui.label(f"Files: {', '.join(snap.files)}").classes("break-all")

        # 4. Confirmation dialog for undo operation
        def confirm_undo(snapshot, previous, index):
            diff = backup_manager.get_undo_diff(snapshot.snapshot_id)
            drift = backup_manager.has_unrecorded_changes()
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

                if drift:
                    ui.label("Warning: Unrecorded changes in the active configuration will be overwritten.").classes(
                        "text-xs text-amber-600 font-medium mb-3"
                    )

                if diff is not None:
                    with ui.column().classes("w-full max-h-48 overflow-auto border border-gray-200 dark:border-gray-700 rounded-lg p-3 mb-4 bg-gray-50 dark:bg-gray-900/60"):
                        render_diff(diff)

                def execute_undo():
                    if backup_manager.undo_change(snapshot.snapshot_id):
                        backend.reload_service()
                        ui.notify(
                            f'Reverted "{snapshot.description}". {discard_count} history {entries_word} removed.',
                            type="positive",
                        )
                        dialog.close()
                        refresh_history()
                    else:
                        ui.notify(
                            "Failed to undo. The previous state is missing or corrupt.",
                            type="negative",
                        )

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps color=grey-7")
                    ui.button("Undo", on_click=execute_undo, icon="undo").props("unelevated no-caps color=primary")

            dialog.open()

        refresh_history()
