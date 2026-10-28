"""Shared helpers for NiceGUI dialogs."""

from __future__ import annotations
from typing import Callable
from nicegui import ui


def submit_on_enter(element: ui.element, handler: Callable[[], None]) -> None:
    """Run the primary dialog action when Enter is pressed in a field."""
    element.on("keydown.enter", lambda _: handler())
