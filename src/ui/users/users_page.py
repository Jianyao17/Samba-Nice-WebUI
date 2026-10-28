"""Samba user and group management page."""

from __future__ import annotations

from nicegui import ui

from src.core.models import SambaUser
from src.samba.backend import SambaBackend
from src.samba.user_backend import SambaUserBackend
from src.ui.layout import page_layout, render_page_header
from src.ui.users.users_components import (
    render_group_card,
    render_groups_empty_state,
    render_user_card,
    render_users_empty_state,
)
from src.ui.users.users_dialogs import (
    open_add_group_dialog,
    open_add_user_dialog,
    open_change_password_dialog,
    open_delete_group_dialog,
    open_delete_user_dialog,
    open_manage_members_dialog,
)


_COUNT_CIRCLE_CLASSES = (
    "grid place-items-center w-5 h-5 rounded-full "
    "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-200 "
    "text-[11px] font-semibold"
)


def _render_section_heading(
    title: str,
    description: str,
    action_label: str,
    action_icon: str,
    on_action,
) -> None:
    """Render a responsive section header with an action."""
    with ui.element("div").classes(
        "w-full flex flex-col sm:flex-row sm:items-center "
        "sm:justify-between gap-2 mb-3"
    ):
        with ui.column().classes("gap-0.5 min-w-0 sm:flex-1"):
            ui.label(title).classes(
                "text-base font-bold text-slate-800 dark:text-slate-100"
            )
            ui.label(description).classes("text-sm text-slate-500")

        ui.button(
            action_label,
            icon=action_icon,
            on_click=on_action,
        ).props("unelevated no-caps color=primary").classes(
            "rounded-lg w-full sm:w-auto shrink-0"
        )


def create_users_page(
    user_backend: SambaUserBackend,
    backend: SambaBackend,
) -> None:
    """Render the users and groups management page."""
    with page_layout("User Management", backend, show_title=False) as authenticated:
        if not authenticated:
            return

        with ui.column().classes("w-full gap-4"):
            render_page_header(
                "User Management",
                "Create Samba accounts, manage passwords, and organize "
                "Unix groups used by share access lists.",
            )

            with ui.element("div").classes(
                "w-full rounded-2xl border border-slate-200 dark:border-slate-700 "
                "bg-white dark:bg-slate-900 overflow-hidden"
            ):
                with ui.tabs().props("no-caps align=left narrow-indicator").classes(
                    "w-full bg-slate-100 dark:bg-slate-800/60 "
                    "border-b border-slate-200 dark:border-slate-700"
                ) as tabs:
                    with ui.tab("Users", label="").classes("h-12 px-4") as users_tab:
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("people", size="1.15rem")
                            ui.label("Users").classes(
                                "text-sm font-medium leading-none"
                            )
                            with ui.element("div").classes(_COUNT_CIRCLE_CLASSES):
                                users_count = ui.label("0").classes("leading-none")

                    with ui.tab("Groups", label="").classes("h-12 px-4") as groups_tab:
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("groups", size="1.15rem")
                            ui.label("Groups").classes(
                                "text-sm font-medium leading-none"
                            )
                            with ui.element("div").classes(_COUNT_CIRCLE_CLASSES):
                                groups_count = ui.label("0").classes("leading-none")

                with ui.tab_panels(tabs, value=users_tab).props("animated").classes(
                    "w-full bg-transparent p-0"
                ):
                    with ui.tab_panel(users_tab).classes("p-4 sm:p-5"):
                        _render_section_heading(
                            "Samba Users",
                            "Accounts that can authenticate to your SMB shares.",
                            "Add User",
                            "person_add",
                            lambda: open_add_user_dialog(user_backend, refresh_all),
                        )
                        users_container = ui.column().classes("w-full gap-2.5")

                    with ui.tab_panel(groups_tab).classes("p-4 sm:p-5"):
                        _render_section_heading(
                            "Groups",
                            "Use @groupname in valid users or write list.",
                            "Add Group",
                            "group_add",
                            lambda: open_add_group_dialog(user_backend, refresh_all),
                        )
                        groups_container = ui.column().classes("w-full gap-2.5")

        def refresh_users() -> None:
            users_container.clear()
            try:
                users = user_backend.list_users()
            except Exception as exc:  # pragma: no cover - defensive UI boundary
                ui.notify(f"Could not load users: {exc}", type="negative")
                users = []

            users_count.set_text(str(len(users)))
            with users_container:
                if not users:
                    render_users_empty_state()
                    return

                for user in users:
                    render_user_card(
                        user,
                        on_password=lambda selected: open_change_password_dialog(
                            selected, user_backend, refresh_all
                        ),
                        on_toggle=lambda selected: _toggle_user(selected, user_backend),
                        on_delete=lambda selected: open_delete_user_dialog(
                            selected, user_backend, refresh_all
                        ),
                    )

        def refresh_groups() -> None:
            groups_container.clear()
            try:
                groups = user_backend.list_groups()
            except Exception as exc:  # pragma: no cover - defensive UI boundary
                ui.notify(f"Could not load groups: {exc}", type="negative")
                groups = []

            groups_count.set_text(str(len(groups)))
            with groups_container:
                if not groups:
                    render_groups_empty_state()
                    return

                for group in groups:
                    render_group_card(
                        group,
                        on_members=lambda selected: open_manage_members_dialog(
                            selected, user_backend, refresh_all
                        ),
                        on_delete=lambda selected: open_delete_group_dialog(
                            selected, user_backend, refresh_all
                        ),
                    )

        def refresh_all() -> None:
            refresh_users()
            refresh_groups()

        def _toggle_user(user: SambaUser, manager: SambaUserBackend) -> None:
            result = (
                manager.disable_user(user.username)
                if user.enabled
                else manager.enable_user(user.username)
            )
            ui.notify(
                result.message,
                type="positive" if result.success else "negative",
            )
            refresh_all()

        refresh_all()
