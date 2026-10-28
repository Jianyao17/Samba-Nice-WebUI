"""Dialogs for managing Samba users and Unix groups."""

from __future__ import annotations

from typing import Callable

from nicegui import ui

from src.core.models import SambaGroup, SambaUser
from src.samba.user_backend import SambaUserBackend
from src.ui.dialog_utils import submit_on_enter


_CARD_CLASSES = (
    "w-full max-w-lg p-0 rounded-2xl overflow-hidden shadow-xl"
)
_HEADER_CLASSES = (
    "w-full items-center justify-between gap-2 px-4 sm:px-6 py-3 "
    "bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-700"
)
_BODY_CLASSES = (
    "w-full px-4 sm:px-6 py-4 gap-3 max-h-[70vh] overflow-y-auto"
)
_FOOTER_CLASSES = (
    "w-full justify-end gap-2 px-4 sm:px-6 py-3 "
    "bg-slate-50 dark:bg-slate-800/40 border-t border-slate-200 dark:border-slate-700"
)
_ERROR_CLASSES = "text-xs text-red-600 dark:text-red-400 break-words"


def _render_header(
    dialog: ui.dialog,
    icon: str,
    title: str,
    subtitle: str = "",
) -> None:
    """Render a shared Material dialog header."""
    with ui.row().classes(_HEADER_CLASSES):
        with ui.row().classes("items-center gap-2 min-w-0 flex-1"):
            ui.icon(icon, size="1.4rem").classes(
                "text-blue-600 dark:text-blue-400 shrink-0"
            )
            with ui.column().classes("gap-0 min-w-0"):
                ui.label(title).classes(
                    "text-base font-bold text-slate-800 dark:text-slate-100 truncate"
                )
                if subtitle:
                    ui.label(subtitle).classes(
                        "text-xs text-slate-500 hidden sm:block"
                    )

        ui.button(icon="close", on_click=dialog.close).props(
            "flat round dense color=grey-7"
        ).classes("shrink-0").tooltip("Close")


def _password_input(label: str) -> ui.input:
    """Create a masked password field with a visibility toggle."""
    return (
        ui.input(label, password=True, password_toggle_button=True)
        .props("outlined dense")
        .classes("w-full")
    )


def open_add_user_dialog(
    user_backend: SambaUserBackend,
    on_done: Callable,
) -> None:
    """Collect a username and password and create a Samba user."""
    dialog = ui.dialog().props("persistent")

    with dialog, ui.card().props("flat bordered").classes(_CARD_CLASSES):
        _render_header(
            dialog,
            "person_add",
            "New Samba User",
            "A no-login Unix account is created and registered with Samba.",
        )

        with ui.column().classes(_BODY_CLASSES):
            username_input = ui.input("Username").props("outlined dense").classes(
                "w-full"
            )
            ui.label(
                "Usernames are stored in lowercase and cannot collide with an "
                "existing Unix or Samba account."
            ).classes("text-xs text-slate-400 -mt-2")

            def force_lower(event) -> None:
                lowered = (event.value or "").lower()
                if lowered != event.value:
                    username_input.set_value(lowered)

            username_input.on_value_change(force_lower)

            password_input = _password_input("Password")
            confirm_input = _password_input("Confirm Password")

            error_label = ui.label("").classes(_ERROR_CLASSES)
            error_label.set_visibility(False)

        def submit() -> None:
            username = (username_input.value or "").strip().lower()
            password = password_input.value or ""
            confirmation = confirm_input.value or ""

            if not username:
                ui.notify("Username is required.", type="warning")
                return
            if not password:
                ui.notify("Password is required.", type="warning")
                return
            if password != confirmation:
                ui.notify("Passwords do not match.", type="warning")
                return

            result = user_backend.create_user(username, password)
            if result.success:
                ui.notify(result.message, type="positive")
                dialog.close()
                on_done()
                return

            error_label.set_text(result.message)
            error_label.set_visibility(True)
            ui.notify(result.message, type="negative")

        with ui.row().classes(_FOOTER_CLASSES):
            ui.button("Cancel", on_click=dialog.close).props(
                "flat no-caps color=grey-7"
            )
            ui.button("Create User", icon="person_add", on_click=submit).props(
                "unelevated no-caps color=primary"
            ).classes("rounded-lg")

    for field in (username_input, password_input, confirm_input):
        submit_on_enter(field, submit)

    dialog.open()


def open_change_password_dialog(
    user: SambaUser,
    user_backend: SambaUserBackend,
    on_done: Callable,
) -> None:
    """Collect a new password and apply it to an existing Samba user."""
    dialog = ui.dialog().props("persistent")

    with dialog, ui.card().props("flat bordered").classes(_CARD_CLASSES):
        _render_header(
            dialog,
            "key",
            f"Change Password: {user.username}",
            "Only the Samba password changes; the Unix account is untouched.",
        )

        with ui.column().classes(_BODY_CLASSES):
            password_input = _password_input("New Password")
            confirm_input = _password_input("Confirm New Password")

            error_label = ui.label("").classes(_ERROR_CLASSES)
            error_label.set_visibility(False)

        def submit() -> None:
            password = password_input.value or ""
            confirmation = confirm_input.value or ""

            if not password:
                ui.notify("Password is required.", type="warning")
                return
            if password != confirmation:
                ui.notify("Passwords do not match.", type="warning")
                return

            result = user_backend.set_password(user.username, password)
            if result.success:
                ui.notify(result.message, type="positive")
                dialog.close()
                on_done()
                return

            error_label.set_text(result.message)
            error_label.set_visibility(True)
            ui.notify(result.message, type="negative")

        with ui.row().classes(_FOOTER_CLASSES):
            ui.button("Cancel", on_click=dialog.close).props(
                "flat no-caps color=grey-7"
            )
            ui.button("Update Password", icon="save", on_click=submit).props(
                "unelevated no-caps color=primary"
            ).classes("rounded-lg")

    for field in (password_input, confirm_input):
        submit_on_enter(field, submit)

    dialog.open()


def open_delete_user_dialog(
    user: SambaUser,
    user_backend: SambaUserBackend,
    on_done: Callable,
) -> None:
    """Confirm deletion and surface share-reference protection errors."""
    dialog = ui.dialog()

    with dialog, ui.card().props("flat bordered").classes(
        "w-full max-w-md p-0 rounded-2xl overflow-hidden shadow-xl"
    ):
        with ui.column().classes("w-full px-4 sm:px-6 py-4 gap-3"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("warning", size="2rem").classes("text-red-500 shrink-0")
                ui.label(f"Delete user '{user.username}'?").classes(
                    "text-lg font-bold text-red-600 dark:text-red-400 break-words"
                )

            ui.label(
                "This removes the Samba account and its no-login Unix account. "
                "Files in shared folders are NOT deleted."
            ).classes("text-sm text-slate-500")

            if user.groups:
                ui.label(
                    "Group memberships: " + ", ".join(user.groups)
                ).classes("text-xs text-slate-400 break-words")

            error_label = ui.label("").classes(_ERROR_CLASSES)
            error_label.set_visibility(False)

        def execute_delete() -> None:
            result = user_backend.delete_user(user.username)
            if result.success:
                ui.notify(result.message, type="positive")
                dialog.close()
                on_done()
                return

            error_label.set_text(result.message)
            error_label.set_visibility(True)
            ui.notify(result.message, type="negative")

        with ui.row().classes(_FOOTER_CLASSES):
            ui.button("Cancel", on_click=dialog.close).props(
                "flat no-caps color=grey-7"
            )
            ui.button("Delete User", icon="delete", on_click=execute_delete).props(
                "unelevated no-caps color=negative"
            ).classes("rounded-lg")

    dialog.open()


def open_add_group_dialog(
    user_backend: SambaUserBackend,
    on_done: Callable,
) -> None:
    """Collect a group name and create it."""
    dialog = ui.dialog().props("persistent")

    with dialog, ui.card().props("flat bordered").classes(_CARD_CLASSES):
        _render_header(
            dialog,
            "group_add",
            "New Group",
            "Use @groupname in a share's valid users or write list.",
        )

        with ui.column().classes(_BODY_CLASSES):
            name_input = ui.input("Group Name").props("outlined dense").classes(
                "w-full"
            )
            ui.label(
                "Group names are stored in lowercase and must be unique."
            ).classes("text-xs text-slate-400 -mt-2")

            def force_lower(event) -> None:
                lowered = (event.value or "").lower()
                if lowered != event.value:
                    name_input.set_value(lowered)

            name_input.on_value_change(force_lower)

            error_label = ui.label("").classes(_ERROR_CLASSES)
            error_label.set_visibility(False)

        def submit() -> None:
            name = (name_input.value or "").strip().lower()
            if not name:
                ui.notify("Group name is required.", type="warning")
                return

            result = user_backend.create_group(name)
            if result.success:
                ui.notify(result.message, type="positive")
                dialog.close()
                on_done()
                return

            error_label.set_text(result.message)
            error_label.set_visibility(True)
            ui.notify(result.message, type="negative")

        with ui.row().classes(_FOOTER_CLASSES):
            ui.button("Cancel", on_click=dialog.close).props(
                "flat no-caps color=grey-7"
            )
            ui.button("Create Group", icon="group_add", on_click=submit).props(
                "unelevated no-caps color=primary"
            ).classes("rounded-lg")

    submit_on_enter(name_input, submit)

    dialog.open()


def open_manage_members_dialog(
    group: SambaGroup,
    user_backend: SambaUserBackend,
    on_done: Callable,
) -> None:
    """Assign or remove Samba-managed users from a group."""
    dialog = ui.dialog().props("persistent")

    # Refresh the group so membership edits always start from the current state
    current_group = group
    try:
        current_group = next(
            (item for item in user_backend.list_groups() if item.name == group.name),
            group,
        )
    except Exception:
        current_group = group

    current_members = set(current_group.members)

    try:
        samba_users = [user.username for user in user_backend.list_users()]
    except Exception:
        samba_users = []

    options = sorted(set(samba_users) | current_members)

    with dialog, ui.card().props("flat bordered").classes(_CARD_CLASSES):
        _render_header(
            dialog,
            "group",
            f"Members: {current_group.name}",
            f"GID {current_group.gid} · select Samba users to include in this group.",
        )

        with ui.column().classes(_BODY_CLASSES):
            if samba_users:
                members_select = ui.select(
                    options=options,
                    label="Group Members",
                    value=sorted(current_members),
                    multiple=True,
                    with_input=True,
                ).props("outlined dense use-chips").classes("w-full")
                ui.label(
                    "Only users with a Samba account can be added to the group."
                ).classes("text-xs text-slate-400 -mt-2")
            else:
                members_select = None
                with ui.row().classes(
                    "items-center gap-2 p-3 rounded-xl bg-amber-50 "
                    "dark:bg-amber-950/30 text-amber-700 dark:text-amber-400"
                ):
                    ui.icon("info", size="1.1rem")
                    ui.label(
                        "Create a Samba user first before assigning group members."
                    ).classes("text-xs")

            error_label = ui.label("").classes(_ERROR_CLASSES)
            error_label.set_visibility(False)

        def submit() -> None:
            if members_select is None:
                ui.notify("Create a Samba user first.", type="warning")
                return

            selected = set(members_select.value or [])
            added = sorted(selected - current_members)
            removed = sorted(current_members - selected)
            errors: list[str] = []

            for username in added:
                result = user_backend.add_user_to_group(username, current_group.name)
                if not result.success:
                    errors.append(result.message)
            for username in removed:
                result = user_backend.remove_user_from_group(
                    username, current_group.name
                )
                if not result.success:
                    errors.append(result.message)

            if errors:
                message = " ".join(errors)
                error_label.set_text(message)
                error_label.set_visibility(True)
                ui.notify("Some membership changes failed.", type="negative")
                on_done()
                return

            ui.notify(f"Members of '{current_group.name}' updated.", type="positive")
            dialog.close()
            on_done()

        with ui.row().classes(_FOOTER_CLASSES):
            ui.button("Cancel", on_click=dialog.close).props(
                "flat no-caps color=grey-7"
            )
            ui.button("Save Members", icon="save", on_click=submit).props(
                "unelevated no-caps color=primary"
            ).classes("rounded-lg")

    if members_select is not None:
        submit_on_enter(members_select, submit)

    dialog.open()


def open_delete_group_dialog(
    group: SambaGroup,
    user_backend: SambaUserBackend,
    on_done: Callable,
) -> None:
    """Confirm deletion and surface protection errors."""
    dialog = ui.dialog()

    with dialog, ui.card().props("flat bordered").classes(
        "w-full max-w-md p-0 rounded-2xl overflow-hidden shadow-xl"
    ):
        with ui.column().classes("w-full px-4 sm:px-6 py-4 gap-3"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("warning", size="2rem").classes("text-red-500 shrink-0")
                ui.label(f"Delete group '{group.name}'?").classes(
                    "text-lg font-bold text-red-600 dark:text-red-400 break-words"
                )

            ui.label(
                "Only empty groups that are not referenced by any active share "
                "can be deleted."
            ).classes("text-sm text-slate-500")

            error_label = ui.label("").classes(_ERROR_CLASSES)
            error_label.set_visibility(False)

        def execute_delete() -> None:
            result = user_backend.delete_group(group.name)
            if result.success:
                ui.notify(result.message, type="positive")
                dialog.close()
                on_done()
                return

            error_label.set_text(result.message)
            error_label.set_visibility(True)
            ui.notify(result.message, type="negative")

        with ui.row().classes(_FOOTER_CLASSES):
            ui.button("Cancel", on_click=dialog.close).props(
                "flat no-caps color=grey-7"
            )
            ui.button("Delete Group", icon="delete", on_click=execute_delete).props(
                "unelevated no-caps color=negative"
            ).classes("rounded-lg")

    dialog.open()
