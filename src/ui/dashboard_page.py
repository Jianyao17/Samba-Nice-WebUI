from nicegui import ui

from src.config import settings
from src.samba.backend import SambaBackend
from src.ui.layout import page_layout


def create_dashboard_page(backend: SambaBackend):
    with page_layout("Dashboard", backend) as authenticated:
        if not authenticated:
            return

        status = backend.get_status()
        shares = backend.list_shares()

        # 1. Metric summary cards
        with ui.row().classes("w-full grid grid-cols-1 md:grid-cols-4 gap-4"):
            # Daemon status card
            with ui.card().classes("p-5 shadow-sm border border-slate-200 dark:border-slate-800"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Daemon Status").classes("text-sm text-slate-500 font-medium")
                    ui.icon("dns", size="1.5rem").classes("text-blue-500")
                ui.label("Running" if status.is_running else "Stopped").classes(
                    f"text-2xl font-bold {'text-emerald-600' if status.is_running else 'text-red-500'}"
                )
                ui.label(f"PID: {status.pid or 'N/A'}").classes("text-xs text-slate-400 mt-1")

            # Active shares card
            with ui.card().classes("p-5 shadow-sm border border-slate-200 dark:border-slate-800"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Total Shares").classes("text-sm text-slate-500 font-medium")
                    ui.icon("share", size="1.5rem").classes("text-indigo-500")
                ui.label(str(len(shares))).classes("text-2xl font-bold text-slate-800 dark:text-slate-100")
                ui.label(f"Stored in {settings.samba_include_conf_path.name}").classes("text-xs text-slate-400 mt-1")

            # Storage roots card
            with ui.card().classes("p-5 shadow-sm border border-slate-200 dark:border-slate-800"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Storage Roots").classes("text-sm text-slate-500 font-medium")
                    ui.icon("folder", size="1.5rem").classes("text-amber-500")
                ui.label(str(len(settings.parsed_storage_roots))).classes("text-2xl font-bold text-slate-800 dark:text-slate-100")
                ui.label(", ".join(settings.parsed_storage_roots)).classes("text-xs text-slate-400 mt-1 truncate")

            # Last reload card
            with ui.card().classes("p-5 shadow-sm border border-slate-200 dark:border-slate-800"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Last Reload").classes("text-sm text-slate-500 font-medium")
                    ui.icon("update", size="1.5rem").classes("text-emerald-500")
                reload_str = status.last_reloaded_at.strftime("%H:%M:%S") if status.last_reloaded_at else "Never"
                ui.label(reload_str).classes("text-2xl font-bold text-slate-800 dark:text-slate-100")
                ui.label("Via SIGHUP signal").classes("text-xs text-slate-400 mt-1")

        # 2. Shares quick overview table
        with ui.card().classes("w-full p-6 shadow-sm border border-slate-200 dark:border-slate-800 mt-2"):
            with ui.row().classes("items-center justify-between w-full mb-4"):
                ui.label("Active Samba Shares").classes("text-lg font-bold text-slate-800 dark:text-slate-100")
                ui.button("Manage All Shares", on_click=lambda: ui.navigate.to("/shares"), icon="arrow_forward").props("flat dense")

            if not shares:
                ui.label("No Samba shares configured yet.").classes("text-slate-400 italic py-4")
            else:
                columns = [
                    {"name": "name", "label": "Share Name", "field": "name", "align": "left", "sortable": True},
                    {"name": "path", "label": "Target Path", "field": "path", "align": "left"},
                    {"name": "access", "label": "Access", "field": "access", "align": "center"},
                    {"name": "guest", "label": "Guest", "field": "guest", "align": "center"},
                    {"name": "conf_file", "label": "Source File", "field": "conf_file", "align": "left"},
                ]
                rows = [
                    {
                        "name": s.name,
                        "path": s.path,
                        "access": "Read-Only" if s.read_only else "Read/Write",
                        "guest": "Yes" if s.guest_ok else "No",
                        "conf_file": s.conf_file or "modular",
                    }
                    for s in shares
                ]
                ui.table(columns=columns, rows=rows, row_key="name").classes("w-full")
