from contextlib import contextmanager
from nicegui import app, ui

from src.core.models import ServerStatus
from src.samba.backend import SambaBackend


def is_authenticated() -> bool:
    # 1. Inspect session dictionary for authenticated flag
    return app.storage.user.get("authenticated", False) is True


def require_auth():
    # 1. Enforce authentication guard, redirecting to login page if unauthenticated
    if not is_authenticated():
        ui.navigate.to("/login")


@contextmanager
def page_layout(title: str, backend: SambaBackend):
    # 1. Enforce user authentication
    if not is_authenticated():
        ui.navigate.to("/login")
        ui.label("Redirecting to login...").classes("text-slate-400 p-6")
        yield False
        return

    # 2. Configure page title and styling tokens
    ui.page_title(f"{title} - Samba-Nice-WebUI")
    ui.colors(primary="#2563eb", secondary="#64748b", accent="#0ea5e9", positive="#10b981", negative="#ef4444")

    # 3. Render header with logo, navigation links, and service status
    with ui.header().classes("items-center justify-between px-6 py-3 bg-slate-900 text-white shadow-md"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("folder_shared", size="2rem").classes("text-blue-400")
            ui.label("Samba-Nice-WebUI").classes("text-xl font-bold tracking-tight")

        with ui.row().classes("items-center gap-6"):
            ui.link("Dashboard", "/").classes("text-slate-200 hover:text-white font-medium")
            ui.link("Shares", "/shares").classes("text-slate-200 hover:text-white font-medium")
            ui.link("Storage", "/storage").classes("text-slate-200 hover:text-white font-medium")
            ui.link("History", "/backups").classes("text-slate-200 hover:text-white font-medium")

        with ui.row().classes("items-center gap-3"):
            # Status indicator badge
            status: ServerStatus = backend.get_status()
            badge_color = "positive" if status.is_running else "negative"
            status_text = f"smbd: PID {status.pid}" if status.is_running else "smbd: stopped"
            ui.badge(status_text, color=badge_color).props("rounded")

            # Quick reload button
            def trigger_reload():
                success = backend.reload_service()
                if success:
                    ui.notify("Samba configuration reloaded successfully (SIGHUP)", type="positive")
                else:
                    ui.notify("Failed to signal reload to Samba daemon", type="negative")

            ui.button(icon="sync", on_click=trigger_reload).props("flat round dense text-color=white").tooltip("Reload Samba Daemon")

            # Logout button
            def handle_logout():
                app.storage.user["authenticated"] = False
                ui.navigate.to("/login")

            ui.button(icon="logout", on_click=handle_logout).props("flat round dense text-color=white").tooltip("Log Out")

    with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6"):
        ui.label(title).classes("text-2xl font-bold text-slate-800 dark:text-slate-100")
        yield True
