"""Reusable UI components for the configuration history page."""

from typing import Callable
from nicegui import ui

from src.core.config_diff import ShareDiff


def render_diff(diff: ShareDiff) -> None:
    with ui.column().classes("w-full gap-1.5"):
        if diff.added:
            ui.label(f"Added shares: {', '.join(diff.added)}") \
                .classes("text-sm font-medium text-green-600 dark:text-green-400")

        if diff.removed:
            ui.label(f"Removed shares: {', '.join(diff.removed)}") \
                .classes("text-sm font-medium text-red-600 dark:text-red-400")

        for share_name, changes in diff.modified.items():
            with ui.column().classes("w-full gap-0.5"):
                ui.label(f"Share [{share_name}]:").classes("text-sm font-bold text-slate-800 dark:text-slate-100")

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


def render_drift_banner() -> None:
    with ui.card()\
    .props("flat bordered")\
    .classes("w-full p-3.5 border-amber-300 bg-amber-50 dark:bg-amber-950/20"):
        ui.label(
            "Warning: Active configuration differs from latest snapshot. "
            "It may have been edited manually; the next save/delete action will record a checkpoint."
        ).classes("text-xs sm:text-sm text-amber-800 dark:text-amber-200")


def render_empty_history() -> None:
    with ui.card().props("flat bordered").classes("w-full p-8 text-center text-gray-400 border border-dashed"):
        ui.icon("history_toggle_off", size="3rem").classes("mx-auto mb-2 text-gray-300")
        ui.label("No history records yet.").classes("font-semibold text-gray-600 dark:text-gray-300")
        ui.label("Changes will appear here when Samba shares are added, updated, or removed.").classes("text-xs text-gray-400 mt-1")


def _render_header(snapshot, index, has_previous, total, diff) -> None:
    with ui.column().classes("flex-1 min-w-0 gap-1"):
        with ui.row().classes("items-center gap-2 flex-wrap min-w-0"):
            ui.label(snapshot.description).classes("text-xs sm:text-sm font-semibold text-slate-800 dark:text-slate-100 truncate")

            if index == 0:
                ui.badge("Latest", color="positive").props("rounded").classes("text-[10px] px-1.5 py-0.5 shrink-0")

            if not has_previous:
                ui.badge("Starting point", color="grey").props("rounded").classes("text-[10px] px-1.5 py-0.5 shrink-0")

        with ui.row().classes("w-full items-center gap-2 text-xs text-gray-500 dark:text-gray-400 flex-wrap min-w-0"):
            ui.label(snapshot.created_at.strftime("%Y-%m-%d %H:%M:%S")).classes("shrink-0")

            with ui.row().classes("items-center gap-1.5 shrink-0"):
                if not has_previous or total == 0:
                    ui.badge("0 changes", color="grey-6").props("rounded").classes("text-[10px] px-2 py-0.5 text-white")

                elif diff is None:
                    ui.badge("No details", color="grey-6").props("rounded").classes("text-[10px] px-2 py-0.5 text-white")
                else:
                    ui.badge(f"{total} change{'s' if total != 1 else ''}", color="warning").props("rounded").classes(
                        "text-[10px] px-2 py-0.5 font-medium text-white"
                    )
                if snapshot.file_hash:
                    ui.badge(f"#{snapshot.file_hash[:8]}", color="blue-grey-6").props("rounded").classes(
                        "font-mono text-[10px] px-2 py-0.5 text-white"
                    )


def _render_footer(snapshot) -> None:
    ui.separator()
    with ui.column().classes("w-full gap-0.5 text-xs text-gray-500 dark:text-gray-400 font-mono"):
        ui.label(f"Snapshot ID: {snapshot.snapshot_id}").classes("break-all")

        if snapshot.file_hash:
            ui.label(f"Full SHA256: {snapshot.file_hash}").classes("break-all")
            
        ui.label(f"Files: {', '.join(snapshot.files)}").classes("break-all")


def render_history_entry(snapshot, previous, index, diff, on_undo: Callable) -> None:
    has_previous = previous is not None
    total = len(diff.added) + len(diff.removed) + sum(len(c) for c in diff.modified.values()) if diff else 0
    exp = ui.expansion().classes(
        "w-full border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden "
        "bg-white dark:bg-slate-900 shadow-sm hover:shadow transition-all duration-200 "
        "hover:bg-gray-100 dark:hover:bg-gray-800/60"
    )

    with exp:
        with exp.add_slot("header"):
            with ui.row().classes("w-full items-center justify-between py-2 sm:py-2.5 gap-3 select-none"):
                with ui.row().classes("items-center gap-3 flex-1 min-w-0"):
                    icon_name = "history" if has_previous else "bookmark"
                    icon_color = "text-blue-600 dark:text-blue-400" if has_previous else "text-gray-400"
                    ui.icon(icon_name, size="1.4rem").classes(f"{icon_color} shrink-0")
                    _render_header(snapshot, index, has_previous, total, diff)

                if has_previous:
                    undo_btn = ui.button("Undo", icon="undo").props("flat no-caps color=primary").classes("gt-xs rounded-lg")
                    undo_btn.on("click.stop", lambda s=snapshot, p=previous, i=index: on_undo(s, p, i))
                    undo_btn.tooltip("Revert configuration to before this change")

        with ui.column().classes("w-full px-4 pb-4 pt-2 gap-3 bg-gray-50/50 dark:bg-gray-900/50"):
            if has_previous:
                with ui.row().classes("w-full justify-end lt-sm pb-2 border-b border-gray-200 dark:border-gray-800"):
                    ui.button(
                        "Undo This Change",
                        icon="undo",
                        on_click=lambda s=snapshot, p=previous, i=index: on_undo(s, p, i),
                    ).props("flat no-caps color=primary").classes("rounded-lg")

            if previous is None:
                ui.label("Starting point of the recorded history. There is no earlier state to undo to.").classes("text-xs text-gray-500 italic")
                
            elif diff is None:
                ui.label("Change details are unavailable for this entry.").classes("text-xs text-amber-600")
                
            else:
                render_diff(diff)
                
            _render_footer(snapshot)
