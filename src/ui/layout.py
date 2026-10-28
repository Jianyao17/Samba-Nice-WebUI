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


_NAV_ITEMS = [
    ("Dashboard", "/", "space_dashboard", lambda t: t == "Dashboard"),
    ("Shares", "/shares", "folder_shared", lambda t: "Share" in t),
    ("Storage", "/storage", "inventory_2", lambda t: "Storage" in t),
    ("Users", "/users", "manage_accounts", lambda t: "User" in t or "Group" in t),
    ("History", "/backups", "history", lambda t: "History" in t or "Backup" in t),
]

_TITLE_CLASSES = "text-2xl font-bold text-slate-800 dark:text-slate-100"
_DESCRIPTION_CLASSES = "text-sm text-slate-500 min-w-0 sm:flex-1"
_COUNT_CLASSES = (
    "grid place-items-center w-7 h-7 rounded-full bg-blue-600 text-white "
    "text-xs font-bold shadow-sm"
)


def render_page_header(
    title: str,
    description: str,
    *,
    count: bool = False,
    action_label: str = "",
    action_icon: str | None = None,
    on_action=None,
) -> ui.label | None:
    """Render a consistent title, description, count, and optional action."""
    count_label: ui.label | None = None

    with ui.column().classes("w-full gap-3"):
        with ui.row().classes("w-full items-center gap-2 min-w-0 flex-wrap"):
            ui.label(title).classes(_TITLE_CLASSES)
            if count:
                with ui.element("div").classes(_COUNT_CLASSES):
                    count_label = ui.label("0").classes("leading-none")

        with ui.element("div").classes(
            "w-full flex flex-col sm:flex-row sm:items-center "
            "sm:justify-between gap-2"
        ):
            ui.label(description).classes(_DESCRIPTION_CLASSES)
            if action_label and on_action is not None:
                ui.button(
                    action_label,
                    icon=action_icon,
                    on_click=on_action,
                ).props("unelevated no-caps color=primary").classes(
                    "rounded-lg w-full sm:w-auto shrink-0"
                )

    return count_label


@contextmanager
def page_layout(title: str, backend: SambaBackend, *, show_title: bool = True):
    # 1. Enforce user authentication
    if not is_authenticated():
        ui.navigate.to("/login")
        ui.label("Redirecting to login...").classes("text-slate-400 p-6")
        yield False
        return

    # 2. Configure page title and styling tokens
    ui.page_title(f"{title} - Samba Nice WebUI")
    ui.colors(primary="#2563eb", secondary="#64748b", accent="#0ea5e9", positive="#10b981", negative="#ef4444")

    # 3. Render clean, simple Material UI top app bar
    with ui.header().classes(
        "w-full p-0 bg-slate-900 text-white shadow-sm flex flex-wrap md:flex-nowrap items-center justify-between"
    ):
        # Baris 1 kiri (Mobile & Desktop): Logo & brand
        with ui.link(target="/").classes(
            "order-1 md:order-1 flex items-center gap-2 sm:gap-2.5 px-3 sm:px-4 h-12 sm:h-14 no-underline text-white shrink-0"
        ):
            ui.icon("folder_shared", size="1.35rem").classes("text-blue-400 shrink-0")
            ui.label("Samba Nice WebUI").classes(
                "text-sm sm:text-base font-bold tracking-tight text-white leading-none whitespace-nowrap"
            )

        # Baris 1 kanan (Mobile & Desktop): Status badge + reload + logout
        with ui.row().classes(
            "order-2 md:order-3 flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 h-12 sm:h-14 shrink-0 flex-nowrap"
        ):
            status: ServerStatus = backend.get_status()
            badge_color = "positive" if status.is_running else "negative"
            mobile_text = "Running" if status.is_running else "Stopped"
            desktop_text = f"smbd: PID {status.pid}" if status.is_running else "smbd: stopped"
            with ui.badge(color=badge_color).props("rounded").classes(
                "text-[11px] sm:text-xs font-mono px-2 sm:px-2.5 py-1 whitespace-nowrap"
            ):
                ui.label(mobile_text).classes("lt-sm leading-none")
                ui.label(desktop_text).classes("gt-xs leading-none")

            def trigger_reload():
                success = backend.reload_service()
                if success:
                    ui.notify("Samba configuration reloaded successfully (SIGHUP)", type="positive")
                else:
                    ui.notify("Failed to signal reload to Samba daemon", type="negative")

            ui.button(icon="sync", on_click=trigger_reload).props(
                "flat round text-color=white size=sm"
            ).classes("w-8 h-8 sm:w-9 sm:h-9 hover:bg-slate-800 transition-colors").tooltip("Reload Samba Daemon")

            def handle_logout():
                app.storage.user["authenticated"] = False
                ui.navigate.to("/login")

            ui.button(icon="logout", on_click=handle_logout).props(
                "flat round text-color=white size=sm"
            ).classes("hover:bg-slate-800 transition-colors w-8 h-8 sm:w-9 sm:h-9").tooltip("Log Out")

        # Baris 2 (Mobile) / Tengah (Desktop): Tombol halaman sebaris dengan tinggi penuh & hover luas
        with ui.element("nav").classes(
            "order-3 md:order-2 w-full md:w-auto h-11 sm:h-12 md:h-14 grid grid-cols-5 md:flex md:items-stretch border-t border-slate-800 md:border-t-0 p-0 m-0"
        ):
            for label, path, icon, is_active_fn in _NAV_ITEMS:
                active = is_active_fn(title)
                btn_classes = (
                    "flex items-center justify-center gap-1 sm:gap-2 "
                    "h-full px-1 sm:px-4 text-[11px] sm:text-sm font-medium no-underline transition-colors "
                    "border-b-2 whitespace-nowrap overflow-hidden "
                    + (
                        "bg-slate-800 text-blue-400 border-blue-500"
                        if active
                        else "text-slate-300 hover:text-white hover:bg-slate-800/60 border-transparent"
                    )
                )
                with ui.link(target=path).classes(btn_classes):
                    ui.icon(icon, size="1.05rem").classes(
                        "shrink-0 transition-transform duration-200 "
                        "hover:scale-110 "
                        + ("text-blue-400" if active else "text-slate-400")
                    )
                    ui.label(label).classes("leading-none truncate max-md:hidden")

    # Compact spacing between bar and title/content
    with ui.column().classes("w-full max-w-7xl mx-auto px-4 sm:px-6 pt-3 pb-8 gap-3"):
        if show_title:
            ui.label(title).classes("text-2xl font-bold text-slate-800 dark:text-slate-100")
        yield True
