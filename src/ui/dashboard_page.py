from nicegui import ui

from src.config import settings
from src.samba.backend import SambaBackend
from src.ui.layout import page_layout, render_page_header


def create_dashboard_page(backend: SambaBackend):
    with page_layout("Dashboard", backend, show_title=False) as authenticated:
        if not authenticated:
            return

        status = backend.get_status()
        shares = backend.list_shares()

        render_page_header(
            "Dashboard",
            "Overview of Samba daemon status, active network shares, and storage roots.",
        )

        # 1. Metric summary cards
        with ui.row().classes("w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"):
            # Daemon status card
            with ui.card().props("flat bordered").classes(
                "w-full p-4 sm:p-5 rounded-xl border border-slate-200 dark:border-slate-700 "
                "bg-white dark:bg-slate-900 shadow-sm flex flex-col justify-between hover:shadow transition-shadow"
            ):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Daemon Status").classes(
                        "text-[11px] font-bold tracking-wider uppercase text-slate-400 dark:text-slate-500"
                    )
                    with ui.element("div").classes(
                        "w-8 h-8 rounded-lg flex items-center justify-center "
                        + (
                            "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400"
                            if status.is_running
                            else "bg-red-50 dark:bg-red-950/40 text-red-500"
                        )
                    ):
                        ui.icon("dns", size="1.2rem")

                with ui.row().classes("items-center gap-2 mt-2 mb-1"):
                    if status.is_running:
                        ui.element("div").classes("w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse")
                        ui.label("Running").classes("text-2xl font-bold text-emerald-600 dark:text-emerald-400 leading-none")
                    else:
                        ui.element("div").classes("w-2.5 h-2.5 rounded-full bg-red-500")
                        ui.label("Stopped").classes("text-2xl font-bold text-red-500 leading-none")

                with ui.row().classes("items-center gap-1.5 text-xs text-slate-400 pt-2.5 border-t border-slate-100 dark:border-slate-800 w-full mt-2"):
                    ui.icon("tag", size="0.95rem").classes("text-slate-400 shrink-0")
                    ui.label(f"PID: {status.pid or 'N/A'}").classes("font-mono text-slate-500 dark:text-slate-400")

            # Active shares card
            with ui.card().props("flat bordered").classes(
                "w-full p-4 sm:p-5 rounded-xl border border-slate-200 dark:border-slate-700 "
                "bg-white dark:bg-slate-900 shadow-sm flex flex-col justify-between hover:shadow transition-shadow"
            ):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Total Shares").classes(
                        "text-[11px] font-bold tracking-wider uppercase text-slate-400 dark:text-slate-500"
                    )
                    with ui.element("div").classes(
                        "w-8 h-8 rounded-lg flex items-center justify-center bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400"
                    ):
                        ui.icon("folder_shared", size="1.2rem")

                ui.label(str(len(shares))).classes("text-2xl font-bold text-slate-800 dark:text-slate-100 mt-2 mb-1 leading-none")

                with ui.row().classes("items-center gap-1.5 text-xs text-slate-400 pt-2.5 border-t border-slate-100 dark:border-slate-800 w-full mt-2 truncate"):
                    ui.icon("description", size="0.95rem").classes("text-slate-400 shrink-0")
                    ui.label(settings.samba_include_conf_path.name).classes("font-mono text-slate-500 dark:text-slate-400 truncate")

            # Storage roots card
            roots_summary = ", ".join(settings.parsed_storage_roots) if settings.parsed_storage_roots else "None"
            with ui.card().props("flat bordered").classes(
                "w-full p-4 sm:p-5 rounded-xl border border-slate-200 dark:border-slate-700 "
                "bg-white dark:bg-slate-900 shadow-sm flex flex-col justify-between hover:shadow transition-shadow"
            ):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Storage Roots").classes(
                        "text-[11px] font-bold tracking-wider uppercase text-slate-400 dark:text-slate-500"
                    )
                    with ui.element("div").classes(
                        "w-8 h-8 rounded-lg flex items-center justify-center bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400"
                    ):
                        ui.icon("inventory_2", size="1.2rem")

                ui.label(str(len(settings.parsed_storage_roots))).classes("text-2xl font-bold text-slate-800 dark:text-slate-100 mt-2 mb-1 leading-none")

                with ui.row().classes("items-center gap-1.5 text-xs text-slate-400 pt-2.5 border-t border-slate-100 dark:border-slate-800 w-full mt-2 truncate"):
                    ui.icon("folder_open", size="0.95rem").classes("text-slate-400 shrink-0")
                    ui.label(roots_summary).classes("font-mono text-slate-500 dark:text-slate-400 truncate").tooltip(roots_summary)

            # Last reload card
            with ui.card().props("flat bordered").classes(
                "w-full p-4 sm:p-5 rounded-xl border border-slate-200 dark:border-slate-700 "
                "bg-white dark:bg-slate-900 shadow-sm flex flex-col justify-between hover:shadow transition-shadow"
            ):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("Last Reload").classes(
                        "text-[11px] font-bold tracking-wider uppercase text-slate-400 dark:text-slate-500"
                    )
                    with ui.element("div").classes(
                        "w-8 h-8 rounded-lg flex items-center justify-center bg-violet-50 dark:bg-violet-950/40 text-violet-600 dark:text-violet-400"
                    ):
                        ui.icon("sync", size="1.2rem")

                reload_str = status.last_reloaded_at.strftime("%H:%M:%S") if status.last_reloaded_at else "Never"
                ui.label(reload_str).classes("text-2xl font-bold text-slate-800 dark:text-slate-100 mt-2 mb-1 leading-none")

                with ui.row().classes("items-center gap-1.5 text-xs text-slate-400 pt-2.5 border-t border-slate-100 dark:border-slate-800 w-full mt-2"):
                    ui.icon("bolt", size="0.95rem").classes("text-emerald-500 shrink-0")
                    ui.label("Via SIGHUP reload").classes("text-slate-500 dark:text-slate-400")

        # 2. Shares quick overview table
        with ui.card().props("flat bordered").classes(
            "w-full p-0 rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 "
            "bg-white dark:bg-slate-900 shadow-sm mt-2 gap-y-0"
        ):
            with ui.row().classes(
                "w-full items-center justify-between px-5 py-3.5 "
                "bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-700 gap-3"
            ):
                with ui.row().classes("items-center gap-2.5"):
                    ui.icon("folder_shared", size="1.35rem").classes("text-blue-600 dark:text-blue-400 shrink-0")
                    ui.label("Active Samba Shares").classes("text-base font-bold text-slate-800 dark:text-slate-100")
                    ui.badge(str(len(shares)), color="primary").props("rounded").classes("text-xs font-semibold px-2 py-0.5")

                ui.button(
                    "Manage All Shares",
                    icon="arrow_forward",
                    on_click=lambda: ui.navigate.to("/shares"),
                ).props("unelevated dense no-caps color=primary").classes(
                    "rounded-lg px-3 py-1.5 text-xs font-semibold"
                )

            if not shares:
                with ui.column().classes("w-full items-center justify-center py-12 px-4 gap-2 text-slate-400"):
                    ui.icon("folder_off", size="2.5rem").classes("text-slate-300 dark:text-slate-600")
                    ui.label("No Samba shares configured yet.").classes("text-sm font-medium text-slate-500")
                    ui.button(
                        "Add Your First Share",
                        icon="add",
                        on_click=lambda: ui.navigate.to("/shares"),
                    ).props("flat no-caps color=primary").classes("text-xs mt-1")
            else:
                columns = [
                    {"name": "name", "label": "Share Name", "field": "name", "align": "left", "sortable": True, "classes": "whitespace-nowrap", "headerClasses": "whitespace-nowrap"},
                    {"name": "path", "label": "Target Path", "field": "path", "align": "left", "sortable": True, "classes": "whitespace-nowrap", "headerClasses": "whitespace-nowrap"},
                    {"name": "access", "label": "Access", "field": "access", "align": "center", "classes": "whitespace-nowrap", "headerClasses": "whitespace-nowrap"},
                    {"name": "guest", "label": "Guest", "field": "guest", "align": "center", "classes": "whitespace-nowrap", "headerClasses": "whitespace-nowrap"},
                    {"name": "users", "label": "Valid Users", "field": "users", "align": "left", "classes": "whitespace-nowrap", "headerClasses": "whitespace-nowrap"},
                    {"name": "writelist", "label": "Write List", "field": "writelist", "align": "left", "classes": "whitespace-nowrap", "headerClasses": "whitespace-nowrap"},
                ]
                rows = [
                    {
                        "name": s.name,
                        "path": s.path,
                        "access": "Read-Only" if s.read_only else "Read/Write",
                        "guest": "Yes" if s.guest_ok else "No",
                        "users": s.valid_users or "Everyone",
                        "users_everyone": not s.valid_users.strip(),
                        "writelist": s.write_list or "None",
                        "writelist_none": not s.write_list.strip(),
                    }
                    for s in shares
                ]
                with ui.element("div").classes("w-full overflow-x-auto select-none sm:select-text"):
                    table = (
                        ui.table(columns=columns, rows=rows, row_key="name")
                        .props("flat :rows-per-page-options='[0]' hide-pagination table-style='min-width:950px'")
                        .classes("w-full")
                    )
                    table.add_slot("body-cell-name", """
                        <q-td :props="props" class="whitespace-nowrap">
                            <div class="row items-center no-wrap q-gutter-x-sm">
                                <q-icon name="folder" size="1.25rem" class="text-blue-500" />
                                <span class="text-weight-bold text-slate-800 dark:text-slate-100 text-sm whitespace-nowrap">{{ props.value }}</span>
                            </div>
                        </q-td>
                    """)
                    table.add_slot("body-cell-path", """
                        <q-td :props="props" class="whitespace-nowrap">
                            <span class="font-mono text-xs text-slate-600 dark:text-slate-300 whitespace-nowrap">{{ props.value }}</span>
                        </q-td>
                    """)
                    table.add_slot("body-cell-access", """
                        <q-td :props="props" class="text-center whitespace-nowrap">
                            <q-badge :color="props.value === 'Read-Only' ? 'warning' : 'positive'" rounded class="q-px-sm q-py-xs text-caption text-weight-medium whitespace-nowrap">
                                <q-icon :name="props.value === 'Read-Only' ? 'lock' : 'edit'" size="0.85rem" class="q-mr-xs" />
                                {{ props.value }}
                            </q-badge>
                        </q-td>
                    """)
                    table.add_slot("body-cell-guest", """
                        <q-td :props="props" class="text-center whitespace-nowrap">
                            <q-badge :color="props.value === 'Yes' ? 'blue-6' : 'grey-6'" rounded class="q-px-sm q-py-xs text-caption text-weight-medium whitespace-nowrap">
                                <q-icon :name="props.value === 'Yes' ? 'person' : 'person_off'" size="0.85rem" class="q-mr-xs" />
                                {{ props.value }}
                            </q-badge>
                        </q-td>
                    """)
                    table.add_slot("body-cell-users", """
                        <q-td :props="props" class="whitespace-nowrap">
                            <div class="row items-center no-wrap q-gutter-x-xs">
                                <q-icon
                                    :name="props.row.users_everyone ? 'public' : 'group'"
                                    size="0.95rem"
                                    :class="props.row.users_everyone ? 'text-slate-400' : 'text-indigo-500'"
                                />
                                <span
                                    :class="props.row.users_everyone
                                        ? 'text-xs italic text-slate-400'
                                        : 'font-mono text-xs text-slate-600 dark:text-slate-300'"
                                >{{ props.value }}</span>
                            </div>
                        </q-td>
                    """)
                    table.add_slot("body-cell-writelist", """
                        <q-td :props="props" class="whitespace-nowrap">
                            <div class="row items-center no-wrap q-gutter-x-xs">
                                <q-icon
                                    :name="props.row.writelist_none ? 'edit_off' : 'edit_note'"
                                    size="0.95rem"
                                    :class="props.row.writelist_none ? 'text-slate-400' : 'text-emerald-600'"
                                />
                                <span
                                    :class="props.row.writelist_none
                                        ? 'text-xs italic text-slate-400'
                                        : 'font-mono text-xs text-slate-600 dark:text-slate-300'"
                                >{{ props.value }}</span>
                            </div>
                        </q-td>
                    """)
