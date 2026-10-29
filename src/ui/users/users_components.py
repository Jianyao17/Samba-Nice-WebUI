"""Reusable Material-style components for the users and groups page."""

from __future__ import annotations

from typing import Callable

from nicegui import ui

from src.core.models import SambaGroup, SambaUser


_ITEM_CLASSES = (
    "w-full rounded-xl border border-slate-200 dark:border-slate-700 "
    "bg-white dark:bg-slate-900 px-3 py-2.5 sm:px-4 gap-2 "
    "transition-colors duration-200 hover:border-slate-300 dark:hover:border-slate-600"
)
_AVATAR_CLASSES = (
    "w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
)
_CHIP_CLASSES = "text-[10px] font-mono leading-none px-1.5 py-0.5"
_ACTION_CLASSES = "rounded-lg px-4 h-9 min-h-9"
_MENU_ITEM_CLASSES = "px-3 py-2 gap-2 text-xs min-h-9 rounded-md"
_DESKTOP_ACTIONS_CLASSES = (
    "gt-xs flex items-center gap-1 shrink-0"
)
_MOBILE_MENU_CLASSES = "lt-sm shrink-0"


def _render_badge(label: str, color: str, icon: str) -> None:
    """Render a compact rounded status badge."""
    with ui.badge(color=color).props("rounded").classes(
        "flex items-center justify-center gap-1 "
        "text-[10px] sm:text-[11px] font-medium whitespace-nowrap px-2 py-0.5"
    ):
        ui.icon(icon).classes("shrink-0 text-[11px] sm:text-[12px]")
        ui.label(label).classes("leading-none")


def _render_chips(values: list[str], empty_text: str, empty_icon: str) -> None:
    """Render group or member chips, or a compact empty hint."""
    if values:
        with ui.row().classes("items-center gap-1 flex-wrap"):
            for value in values:
                with ui.badge(color="blue-grey").props("rounded").classes(
                    _CHIP_CLASSES
                ):
                    ui.label(value).classes("leading-none")
        return

    with ui.row().classes("items-center gap-1 text-slate-400"):
        ui.icon(empty_icon, size="0.9rem")
        ui.label(empty_text).classes("text-[11px] italic leading-none")


def _render_mobile_action(
    label: str,
    icon: str,
    color_classes: str,
    on_click: Callable[[], None],
) -> None:
    """Render one compact action inside the mobile overflow menu."""
    with ui.menu_item(on_click=on_click).classes(_MENU_ITEM_CLASSES):
        with ui.row().classes("items-center gap-2"):
            ui.icon(icon, size="1rem").classes(color_classes)
            ui.label(label).classes("text-xs leading-none " + color_classes)


def _render_mobile_menu(
    actions: list[tuple[str, str, str, Callable[[], None]]],
) -> None:
    """Render a three-dot menu holding the item actions on small screens."""
    with ui.button(icon="more_vert").props(
        "flat round dense color=grey-7"
    ).classes(
        _MOBILE_MENU_CLASSES + " w-8 h-8 min-h-8"
    ).tooltip("Actions"):
        with ui.menu().props("auto-close").classes("min-w-[11rem] py-1"):
            for label, icon, color_classes, on_click in actions:
                _render_mobile_action(label, icon, color_classes, on_click)


def render_user_card(
    user: SambaUser,
    on_password: Callable[[SambaUser], None],
    on_toggle: Callable[[SambaUser], None],
    on_delete: Callable[[SambaUser], None],
) -> None:
    """Render one Samba user as a compact two-row item."""
    with ui.element("div").classes(_ITEM_CLASSES):
        with ui.row().classes("w-full items-center gap-2 sm:gap-3"):
            with ui.row().classes("items-center gap-2.5 min-w-0 flex-1"):
                with ui.element("div").classes(
                    _AVATAR_CLASSES
                    + (
                        " bg-blue-50 dark:bg-blue-950/40 "
                        "text-blue-600 dark:text-blue-400"
                        if user.enabled
                        else " bg-slate-100 dark:bg-slate-800 text-slate-400"
                    )
                ):
                    ui.icon("person", size="1.2rem")

                with ui.column().classes("gap-1 min-w-0 flex-1"):
                    with ui.row().classes("items-center gap-2 min-w-0"):
                        ui.label(user.username).classes(
                            "text-sm font-bold text-slate-800 dark:text-slate-100 "
                            "truncate"
                        ).tooltip(user.username)
                        if user.enabled:
                            _render_badge("Enabled", "positive", "check_circle")
                        else:
                            _render_badge("Disabled", "grey", "block")

                    _render_chips(user.groups, "No group memberships", "group_off")

            with ui.row().classes(_DESKTOP_ACTIONS_CLASSES):
                ui.button(
                    "Password",
                    icon="key",
                    on_click=lambda: on_password(user),
                ).props("flat no-caps color=primary").classes(
                    _ACTION_CLASSES
                ).tooltip("Change password")

                ui.button(
                    "Disable" if user.enabled else "Enable",
                    icon="block" if user.enabled else "check_circle",
                    on_click=lambda: on_toggle(user),
                ).props(
                    "flat no-caps color=warning"
                    if user.enabled
                    else "flat no-caps color=positive"
                ).classes(_ACTION_CLASSES)

                ui.button(
                    icon="delete",
                    on_click=lambda: on_delete(user),
                ).props("flat round color=negative").classes(
                    "w-9 h-9 min-h-9 shrink-0"
                ).tooltip("Delete user")

            _render_mobile_menu(
                [
                    (
                        "Change Password",
                        "key",
                        "text-primary",
                        lambda: on_password(user),
                    ),
                    (
                        "Disable" if user.enabled else "Enable",
                        "block" if user.enabled else "check_circle",
                        "text-amber-600" if user.enabled else "text-positive",
                        lambda: on_toggle(user),
                    ),
                    (
                        "Delete User",
                        "delete",
                        "text-negative",
                        lambda: on_delete(user),
                    ),
                ]
            )


def render_group_card(
    group: SambaGroup,
    on_members: Callable[[SambaGroup], None],
    on_delete: Callable[[SambaGroup], None],
) -> None:
    """Render one Unix group as a compact two-row item."""
    with ui.element("div").classes(_ITEM_CLASSES):
        with ui.row().classes("w-full items-center gap-2 sm:gap-3"):
            with ui.row().classes("items-center gap-2.5 min-w-0 flex-1"):
                with ui.element("div").classes(
                    _AVATAR_CLASSES
                    + " bg-violet-50 dark:bg-violet-950/40 "
                    "text-violet-600 dark:text-violet-400"
                ):
                    ui.icon("groups", size="1.2rem")

                with ui.column().classes("gap-1 min-w-0 flex-1"):
                    with ui.row().classes("items-center gap-2 min-w-0"):
                        ui.label(group.name).classes(
                            "text-sm font-bold text-slate-800 dark:text-slate-100 "
                            "truncate"
                        ).tooltip(group.name)
                        _render_badge(
                            f"{len(group.members)} member"
                            + ("" if len(group.members) == 1 else "s"),
                            "primary" if group.members else "grey",
                            "people",
                        )
                        ui.label(f"GID {group.gid}").classes(
                            "text-[11px] font-mono text-slate-400 truncate"
                        )

                    _render_chips(group.members, "No members yet", "person_off")

            with ui.row().classes(_DESKTOP_ACTIONS_CLASSES):
                ui.button(
                    "Manage Members",
                    icon="group_add",
                    on_click=lambda: on_members(group),
                ).props("flat no-caps color=primary").classes(_ACTION_CLASSES)

                ui.button(
                    icon="delete",
                    on_click=lambda: on_delete(group),
                ).props("flat round color=negative").classes(
                    "w-9 h-9 min-h-9 shrink-0"
                ).tooltip("Delete group")

            _render_mobile_menu(
                [
                    (
                        "Manage Members",
                        "group_add",
                        "text-primary",
                        lambda: on_members(group),
                    ),
                    (
                        "Delete Group",
                        "delete",
                        "text-negative",
                        lambda: on_delete(group),
                    ),
                ]
            )


def _render_empty_state(
    icon: str,
    icon_classes: str,
    title: str,
    description: str,
    hint: str,
) -> None:
    """Render a centered empty state with a soft icon tile and hint."""
    with ui.column().classes(
        "w-full items-center justify-center gap-3 text-center "
        "rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 "
        "bg-slate-50/60 dark:bg-slate-900/40 px-6 py-10"
    ):
        with ui.element("div").classes(
            "grid place-items-center w-14 h-14 rounded-2xl " + icon_classes
        ):
            ui.icon(icon, size="1.7rem")

        with ui.column().classes("items-center gap-1 max-w-sm"):
            ui.label(title).classes(
                "text-sm font-semibold text-slate-700 dark:text-slate-200"
            )
            ui.label(description).classes(
                "text-xs text-slate-500 dark:text-slate-400 leading-relaxed"
            )

        with ui.row().classes(
            "items-center gap-1 mt-1 text-[11px] font-medium "
            "text-slate-400 dark:text-slate-500"
        ):
            ui.icon("north", size="0.85rem")
            ui.label(hint).classes("leading-none")


def render_users_empty_state() -> None:
    """Compact, centered empty state for the users tab."""
    _render_empty_state(
        "person_off",
        "bg-blue-50 text-blue-500 dark:bg-blue-950/40 dark:text-blue-400",
        "No Samba users yet",
        "Only accounts with a Samba password can sign in. Existing Linux users "
        "are not listed until they are registered with Samba.",
        "Use Add User in the header above to get started",
    )


def render_groups_empty_state() -> None:
    """Compact, centered empty state for the groups tab."""
    _render_empty_state(
        "group_off",
        "bg-violet-50 text-violet-500 dark:bg-violet-950/40 dark:text-violet-400",
        "No groups yet",
        "Groups bundle access rules so you can reference them as @groupname in a share.",
        "Use Add Group in the header above to get started",
    )
