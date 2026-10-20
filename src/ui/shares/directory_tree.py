"""Lazy, expandable directory tree used by the share path browser."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional
from nicegui import ui

from src.core.security import is_path_safe
from src.storage.dir_manager import StorageDirectoryManager


_ROW_CLASSES = (
    "w-full flex items-center gap-1.5 pr-2 py-1.5 rounded-lg cursor-pointer "
    "select-none transition-colors hover:bg-slate-100 dark:hover:bg-slate-800"
)
_SELECTED_CLASSES = (
    "bg-blue-50 dark:bg-blue-950/40 ring-1 ring-blue-200 dark:ring-blue-900/60"
)
_PLACEHOLDER_CLASSES = (
    "w-full flex items-center gap-2 py-1.5 text-xs text-slate-400 dark:text-slate-500"
)


class DirectoryTree:
    """
    Render a Material-style directory tree with lazy child loading.

    Only the direct children of a folder are read when that folder is expanded
    for the first time. This keeps the browser responsive even when storage
    roots contain large directory trees.
    """

    def __init__(
        self,
        dir_manager: StorageDirectoryManager,
        initial_path: str = "",
        on_select: Optional[Callable[[Optional[str]], None]] = None,
    ) -> None:
        self.dir_manager = dir_manager
        self.initial_path = initial_path
        self.on_select = on_select
        self.roots = [Path(root).resolve() for root in dir_manager.allowed_roots]

        # 1. Internal UI state is scoped to this tree instance
        self._tree: Optional[ui.column] = None
        self._rows: dict[str, ui.element] = {}
        self._containers: dict[str, ui.column] = {}
        self._chevrons: dict[str, ui.button] = {}
        self._depths: dict[str, int] = {}
        self._loaded: set[str] = set()
        self._expanded: set[str] = set()
        self._selected_row: Optional[ui.element] = None
        self._selected_path: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def selected_path(self) -> Optional[str]:
        return self._selected_path

    def render(self) -> None:
        """Build the tree and reveal the initial path when possible."""
        self._tree = ui.column().classes(
            "w-full gap-0.5 max-h-[42vh] overflow-y-auto overflow-x-hidden "
            "p-2 rounded-xl border border-slate-200 dark:border-slate-700 "
            "bg-white dark:bg-slate-900"
        )

        with self._tree:
            if not self.roots:
                ui.label("No allowed storage roots configured.").classes(
                    "p-3 text-sm text-slate-400 italic"
                )
                return

            for root in self.roots:
                self._render_node(root, depth=0, is_root=True)

        self._reveal_initial()

    def refresh(self) -> None:
        """Clear cached listings and rebuild the tree."""
        if self._tree is None:
            return

        # 1. Preserve the user's current location across the rebuild
        self.initial_path = self._selected_path or self.initial_path

        # 2. Reset all state, including lazy-load caches and selection
        self._tree.clear()
        self._rows.clear()
        self._containers.clear()
        self._chevrons.clear()
        self._depths.clear()
        self._loaded.clear()
        self._expanded.clear()
        self._selected_row = None
        self._selected_path = None
        self._notify_selection(None)

        # 3. Rebuild roots and try to reveal the initial path again
        with self._tree:
            for root in self.roots:
                self._render_node(root, depth=0, is_root=True)
        self._reveal_initial()

    # ------------------------------------------------------------------
    # Tree rendering
    # ------------------------------------------------------------------

    def _render_node(self, path: Path, depth: int, is_root: bool = False) -> None:
        path_str = str(path)
        self._depths[path_str] = depth

        with ui.column().classes("w-full gap-0.5"):
            with ui.row().classes(_ROW_CLASSES).style(
                f"padding-left: {8 + depth * 18}px"
            ) as row:
                row.props("tabindex=0 role=button")
                row.on("click", lambda p=path_str: self._select(p))
                row.on("keydown.enter", lambda p=path_str: self._select(p))

                # Chevron button controls expansion without selecting the row
                chevron = (
                    ui.button(icon="chevron_right")
                    .props("flat round dense size=sm color=grey-7")
                    .classes("shrink-0 w-7 h-7")
                    .tooltip("Expand folder")
                )
                chevron.on("click.stop", lambda p=path_str: self._toggle(p))

                ui.icon("storage" if is_root else "folder", size="1.2rem").classes(
                    "text-blue-600 dark:text-blue-400 shrink-0"
                )
                ui.label(path_str if is_root else path.name).classes(
                    "text-sm text-slate-700 dark:text-slate-200 truncate min-w-0 flex-1"
                ).tooltip(path_str)

            # Children are created lazily when this folder is first expanded
            container = ui.column().classes("w-full gap-0.5")
            container.set_visibility(False)

        self._rows[path_str] = row
        self._containers[path_str] = container
        self._chevrons[path_str] = chevron

    def _render_placeholder(
        self,
        text: str,
        icon: str,
        depth: int,
        color_classes: str = "text-slate-400 dark:text-slate-500",
    ) -> None:
        with ui.row().classes(f"{_PLACEHOLDER_CLASSES} {color_classes}").style(
            f"padding-left: {8 + depth * 18 + 28}px"
        ):
            ui.icon(icon, size="1rem").classes("shrink-0")
            ui.label(text).classes("italic")

    # ------------------------------------------------------------------
    # Expansion and lazy loading
    # ------------------------------------------------------------------

    def _toggle(self, path_str: str) -> None:
        if path_str in self._expanded:
            self._collapse(path_str)
        else:
            self._expand(path_str)

    def _expand(self, path_str: str) -> None:
        if path_str not in self._rows:
            return

        if path_str not in self._loaded:
            self._load_children(path_str)

        self._containers[path_str].set_visibility(True)
        self._chevrons[path_str].set_icon("expand_more").tooltip("Collapse folder")
        self._expanded.add(path_str)

    def _collapse(self, path_str: str) -> None:
        if path_str not in self._containers:
            return

        self._containers[path_str].set_visibility(False)
        self._chevrons[path_str].set_icon("chevron_right").tooltip("Expand folder")
        self._expanded.discard(path_str)

    def _load_children(self, path_str: str) -> None:
        root = self._root_for(path_str)
        depth = self._depths.get(path_str, 0)
        self._loaded.add(path_str)

        # 1. Read only the direct children; errors become an inline message
        try:
            items = self.dir_manager.list_directory(path_str)
        except (PermissionError, OSError, ValueError) as exc:
            with self._containers[path_str]:
                self._render_placeholder(
                    "Cannot read this folder", "error", depth + 1,
                    "text-red-500 dark:text-red-400",
                )
            ui.notify(f"Cannot read '{path_str}': {exc}", type="negative")
            return

        # 2. Keep only directories that are still inside this root
        directories = []
        for item in items:
            if not item.get("is_dir"):
                continue
            child = Path(item["path"])
            if is_path_safe(child, [root]):
                directories.append(child)

        directories.sort(key=lambda child: child.name.casefold())

        # 3. Render child rows lazily; each child gets its own expand container
        with self._containers[path_str]:
            if not directories:
                self._render_placeholder("No subfolders", "subdirectory_arrow_right", depth + 1)
                return

            for child in directories:
                self._render_node(child, depth=depth + 1)

    def _root_for(self, path_str: str) -> Path:
        path = Path(path_str)
        for root in self.roots:
            if is_path_safe(path, [root]):
                return root
        return self.roots[0]

    # ------------------------------------------------------------------
    # Selection and initial reveal
    # ------------------------------------------------------------------

    def _select(self, path_str: str) -> None:
        row = self._rows.get(path_str)
        if row is None:
            return

        if self._selected_row is not None and self._selected_row != row:
            self._selected_row.classes(remove=_SELECTED_CLASSES)

        row.classes(add=_SELECTED_CLASSES)
        self._selected_row = row
        self._selected_path = path_str
        self._notify_selection(path_str)

    def _notify_selection(self, path_str: Optional[str]) -> None:
        if self.on_select is not None:
            self.on_select(path_str)

    def _resolve_initial_path(self) -> Path:
        raw_path = (self.initial_path or "").strip()
        if raw_path:
            try:
                candidate = Path(raw_path).resolve()
                if candidate.is_dir() and any(
                    is_path_safe(candidate, [root]) for root in self.roots
                ):
                    return candidate
            except (OSError, RuntimeError, ValueError):
                pass

        return self.roots[0]

    def _reveal_initial(self) -> None:
        if not self.roots:
            return

        target = self._resolve_initial_path()
        target_root = self._root_for(str(target))

        # 1. Build the ancestor chain from the owning root down to the target
        chain: list[Path] = []
        current = target
        while True:
            chain.append(current)
            if current == target_root:
                break
            parent = current.parent
            if parent == current:
                break
            current = parent
        chain.reverse()

        # 2. Expand each ancestor so the target node exists, then select it
        last_existing: Optional[str] = None
        for path in chain:
            path_str = str(path)
            if path_str not in self._rows:
                break
            last_existing = path_str
            self._expand(path_str)
            if path_str == str(target):
                break

        if last_existing is not None:
            self._select(last_existing)
