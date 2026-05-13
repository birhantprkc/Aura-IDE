"""Tabbed code editor pane with syntax highlighting and character-by-character
typing animation for streaming file content from the worker.

Each tab represents a file being written/edited by the worker.  Content is
revealed progressively via a QTimer-driven typing effect, and tabs are
automatically closed when the worker finishes.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QInputDialog,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from aura.focused_actions import ACTION_LABELS, build_prompt_for_action, is_edit_action
from aura.gui.cards._helpers import _mono_font
from aura.gui.syntax import PygmentsHighlighter, language_from_path
from aura.gui.theme import ACCENT, BG, BORDER, FG

logger = logging.getLogger(__name__)


class CodeEditorPane(QWidget):
    """Tabbed code editor with streaming typewriter animation.

    Public API:
        open_or_focus_tab(tool_id, file_path) -> None
        stream_content(tool_id, content) -> None
        finalize_tab(tool_id) -> None
        close_all_tabs() -> None
    """

    focused_action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget(self)
        self._tabs.setMinimumSize(0, 0)
        self._tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.setStyleSheet(self._tab_widget_style())
        layout.addWidget(self._tabs)

        # Internal tracking
        self._editors: dict[str, QPlainTextEdit] = {}
        self._typing_state: dict[str, dict] = {}
        self._tool_aliases: dict[str, str] = {}
        self._worker_tabs_by_path: dict[str, str] = {}
        # Map tab index -> tool_id so we can clean up on close
        self._tab_index_to_tool_id: dict[int, str] = {}
        self._file_tabs: dict[Path, QPlainTextEdit] = {}
        self._editor_file_paths: dict[QPlainTextEdit, Path] = {}
        self._workspace_root: Path | None = None
        self._read_only_mode = False

        self._ask_shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
        self._ask_shortcut.activated.connect(self.ask_about_current_selection)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_workspace_root(self, root: Path | None) -> None:
        self._workspace_root = root

    def set_read_only_mode(self, enabled: bool) -> None:
        self._read_only_mode = enabled

    def open_file(self, file_path: Path) -> None:
        """Open a workspace file in a readonly selectable editor tab."""
        path = Path(file_path)
        if not path.exists() or path.is_dir():
            return
        resolved = path.resolve()
        if resolved in self._file_tabs:
            idx = self._tabs.indexOf(self._file_tabs[resolved])
            if idx >= 0:
                self._tabs.setCurrentIndex(idx)
            return

        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            QMessageBox.warning(self, "Open File", f"Could not open {path}:\n{exc}")
            logger.exception("Failed to open file for focused actions: %s", path)
            return

        editor = self._create_editor(resolved)
        editor.setPlainText(text)
        PygmentsHighlighter(editor.document(), language_from_path(str(resolved)))

        idx = self._tabs.addTab(editor, resolved.name)
        self._tabs.setTabToolTip(idx, self._rel_path(resolved))
        self._tabs.setCurrentIndex(idx)

        self._file_tabs[resolved] = editor
        self._editor_file_paths[editor] = resolved
        logger.info("Opened file for focused actions: %s", resolved)

    def open_or_focus_tab(self, tool_id: str, file_path: str) -> None:
        """Create a new tab for *file_path* or focus an existing one.

        Args:
            tool_id: Unique identifier for this tool call (worker_tool_id).
            file_path: Absolute or relative path to the file being edited.
        """
        # If a tab for this tool_id already exists, just focus it
        canonical_tool_id = self._canonical_tool_id(tool_id)
        if canonical_tool_id in self._editors:
            idx = self._tabs.indexOf(self._editors[canonical_tool_id])
            if idx >= 0:
                self._tabs.setCurrentIndex(idx)
            return

        path_key = self._worker_path_key(file_path)
        basename = Path(file_path).name
        language = language_from_path(file_path)
        existing_tool_id = self._worker_tabs_by_path.get(path_key)
        existing_editor = (
            self._editors.get(existing_tool_id) if existing_tool_id is not None else None
        )
        if existing_tool_id is not None and existing_editor is not None:
            self._tool_aliases[tool_id] = existing_tool_id
            self._editors[tool_id] = existing_editor
            state = self._typing_state.get(existing_tool_id)
            if state is not None:
                state["active_count"] = state.get("active_count", 0) + 1
                state["target"] = ""
                state["position"] = 0
                state["timer"].stop()
            existing_editor.clear()
            idx = self._tabs.indexOf(existing_editor)
            if idx >= 0:
                self._tabs.setTabText(idx, f"{basename} ●")
                self._tabs.setCurrentIndex(idx)
            return

        editor = self._create_editor(Path(file_path))

        # Attach syntax highlighter
        PygmentsHighlighter(editor.document(), language)

        idx = self._tabs.addTab(editor, f"{basename} ●")
        self._tabs.setCurrentIndex(idx)

        self._editors[tool_id] = editor
        self._tool_aliases[tool_id] = tool_id
        self._worker_tabs_by_path[path_key] = tool_id
        self._tab_index_to_tool_id[idx] = tool_id

        # Initialise typing state
        self._typing_state[tool_id] = {
            "timer": QTimer(self),
            "target": "",
            "position": 0,
            "language": language,
            "path": file_path,
            "path_key": path_key,
            "basename": basename,
            "active_count": 1,
        }
        timer: QTimer = self._typing_state[tool_id]["timer"]
        timer.timeout.connect(lambda tid=tool_id: self._on_typing_tick(tid))
        timer.setInterval(33)  # ~30 fps

    def stream_content(self, tool_id: str, content: str) -> None:
        """Update the target content for the typing animation.

        If the typing timer is not yet running, it will be started.  The
        animation progressively reveals characters from the current position
        toward the new target.

        Args:
            tool_id: The worker_tool_id previously passed to open_or_focus_tab.
            content: The latest full content of the file.
        """
        canonical_tool_id = self._canonical_tool_id(tool_id)
        state = self._typing_state.get(canonical_tool_id)
        if state is None:
            return
        editor = self._editors.get(canonical_tool_id)
        if editor is not None:
            visible_content = editor.toPlainText()
            if visible_content and not content.startswith(visible_content):
                state["position"] = 0
                editor.clear()
        state["target"] = content
        timer: QTimer = state["timer"]
        if not timer.isActive():
            timer.start()

    def finalize_tab(self, tool_id: str) -> None:
        """Flush remaining characters immediately and mark the tab as done.

        Args:
            tool_id: The worker_tool_id previously passed to open_or_focus_tab.
        """
        canonical_tool_id = self._canonical_tool_id(tool_id)
        state = self._typing_state.get(canonical_tool_id)
        if state is None:
            return

        timer: QTimer = state["timer"]
        timer.stop()

        editor = self._editors.get(canonical_tool_id)
        if editor is not None:
            # Flush all remaining content
            target = state["target"]
            editor.setPlainText(target)
            # Auto-scroll to bottom
            sb = editor.verticalScrollBar()
            sb.setValue(sb.maximum())

        # Update tab label
        state["active_count"] = max(0, state.get("active_count", 1) - 1)
        self._tool_aliases.pop(tool_id, None)
        if tool_id != canonical_tool_id:
            self._editors.pop(tool_id, None)

        idx = self._tabs.indexOf(editor) if editor is not None else -1
        if idx >= 0 and state["active_count"] == 0:
            basename = state["basename"]
            self._tabs.setTabText(idx, f"{basename} ✓")

    def close_all_tabs(self) -> None:
        """Remove every tab, disconnect timers, and clear internal tracking."""
        # Stop all typing timers
        for state in self._typing_state.values():
            timer: QTimer = state["timer"]
            timer.stop()
            timer.deleteLater()

        self._typing_state.clear()
        self._editors.clear()
        self._tool_aliases.clear()
        self._worker_tabs_by_path.clear()
        self._tab_index_to_tool_id.clear()
        self._file_tabs.clear()
        self._editor_file_paths.clear()

        # Remove all tabs without triggering close handlers
        self._tabs.blockSignals(True)
        while self._tabs.count() > 0:
            self._tabs.removeTab(0)
        self._tabs.blockSignals(False)

    def close_worker_tabs(self) -> None:
        """Remove streaming worker tabs while preserving user-opened file tabs."""
        for state in self._typing_state.values():
            timer: QTimer = state["timer"]
            timer.stop()
            timer.deleteLater()
        worker_editors = list(dict.fromkeys(self._editors.values()))
        self._typing_state.clear()
        self._editors.clear()
        self._tool_aliases.clear()
        self._worker_tabs_by_path.clear()
        self._tab_index_to_tool_id.clear()

        self._tabs.blockSignals(True)
        for editor in worker_editors:
            idx = self._tabs.indexOf(editor)
            if idx >= 0:
                self._tabs.removeTab(idx)
            self._editor_file_paths.pop(editor, None)
        self._tabs.blockSignals(False)

    def ask_about_current_selection(self) -> None:
        editor = self._current_editor()
        if editor is None:
            return
        self._run_focused_action(editor, "ask")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_editor(self, file_path: Path) -> QPlainTextEdit:
        editor = QPlainTextEdit(self)
        editor.setReadOnly(True)
        editor.setMinimumSize(0, 0)
        editor.setFont(_mono_font(10))
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        editor.customContextMenuRequested.connect(
            lambda pos, e=editor: self._on_editor_context_menu(e, pos)
        )
        editor.setStyleSheet(
            f"background: {BG}; color: {FG}; border: none; padding: 8px;"
        )
        self._editor_file_paths[editor] = Path(file_path)
        return editor

    def _current_editor(self) -> QPlainTextEdit | None:
        current = self._tabs.currentWidget()
        return current if isinstance(current, QPlainTextEdit) else None

    def _canonical_tool_id(self, tool_id: str) -> str:
        return self._tool_aliases.get(tool_id, tool_id)

    def _worker_path_key(self, file_path: str) -> str:
        return Path(file_path).as_posix()

    def _on_editor_context_menu(self, editor: QPlainTextEdit, pos) -> None:
        menu = QMenu(editor)
        has_selection = editor.textCursor().hasSelection()
        if not has_selection:
            whole_file = QAction("No selection: use whole file", menu)
            whole_file.setEnabled(False)
            menu.addAction(whole_file)
            menu.addSeparator()

        for action_key in (
            "ask",
            "explain",
            "fix",
            "refactor",
            "simplify",
            "add_logging",
            "add_type_hints",
            "write_tests",
        ):
            label = ACTION_LABELS[action_key]
            if self._read_only_mode and is_edit_action(action_key):
                label = f"{label} (suggest only)"
            action = QAction(label, menu)
            action.triggered.connect(
                lambda _checked=False, key=action_key: self._run_focused_action(editor, key)
            )
            menu.addAction(action)

        menu.addSeparator()
        default_menu = editor.createStandardContextMenu()
        for action in default_menu.actions():
            menu.addAction(action)
        menu.exec(editor.viewport().mapToGlobal(pos))

    def _run_focused_action(self, editor: QPlainTextEdit, action_key: str) -> None:
        path = self._editor_file_paths.get(editor)
        if path is None:
            QMessageBox.information(
                self,
                "Focused Action",
                "Open a workspace file before using focused actions.",
            )
            return

        cursor = editor.textCursor()
        selected_text = cursor.selectedText().replace("\u2029", "\n")
        start_offset: int | None = cursor.selectionStart()
        end_offset: int | None = cursor.selectionEnd()
        if not cursor.hasSelection():
            selected_text = editor.toPlainText()
            start_offset = 0
            end_offset = len(selected_text)
            QMessageBox.information(
                self,
                "Focused Action",
                "No text is selected, so Aura will use the whole current file.",
            )

        custom_question = ""
        if action_key == "ask":
            custom_question, ok = QInputDialog.getText(
                self,
                "Ask Aura About Selection",
                "What do you want Aura to know or do?",
            )
            if not ok or not custom_question.strip():
                return
            custom_question = custom_question.strip()

        try:
            prompt = build_prompt_for_action(
                action_key=action_key,
                relative_path=self._rel_path(path),
                full_file_text=editor.toPlainText(),
                selected_text=selected_text,
                selection_start_offset=start_offset,
                selection_end_offset=end_offset,
                custom_question=custom_question,
                read_only_mode=self._read_only_mode,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Focused Action", str(exc))
            logger.exception("Failed to build focused action prompt for %s", path)
            return

        logger.info(
            "Created focused action prompt action=%s path=%s selected_chars=%s",
            action_key,
            path,
            len(selected_text),
        )
        self.focused_action_requested.emit(prompt)

        # Restore the same cursor so the highlighted region remains visible.
        if start_offset is not None and end_offset is not None:
            keep = QTextCursor(editor.document())
            keep.setPosition(start_offset)
            keep.setPosition(end_offset, QTextCursor.MoveMode.KeepAnchor)
            editor.setTextCursor(keep)

    def _on_typing_tick(self, tool_id: str) -> None:
        """Reveal ~5 more characters of the target content."""
        canonical_tool_id = self._canonical_tool_id(tool_id)
        state = self._typing_state.get(canonical_tool_id)
        if state is None:
            return

        editor = self._editors.get(canonical_tool_id)
        if editor is None:
            return

        target = state["target"]
        pos = state["position"]

        if pos >= len(target):
            state["timer"].stop()
            return

        pos += 5
        state["position"] = pos
        editor.setPlainText(target[:pos])

        # Auto-scroll to bottom
        sb = editor.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_tab_close_requested(self, index: int) -> None:
        """Handle user clicking the close button on a tab."""
        closed_widget = self._tabs.widget(index)
        tool_id = self._tab_index_to_tool_id.pop(index, None)
        if tool_id is not None:
            state = self._typing_state.pop(tool_id, None)
            if state is not None:
                timer: QTimer = state["timer"]
                timer.stop()
                timer.deleteLater()
                self._worker_tabs_by_path.pop(state.get("path_key", ""), None)
            aliases = [
                tid for tid, canonical in self._tool_aliases.items()
                if canonical == tool_id
            ]
            for alias in aliases:
                self._tool_aliases.pop(alias, None)
                self._editors.pop(alias, None)
            self._editors.pop(tool_id, None)

        self._tabs.removeTab(index)

        if isinstance(closed_widget, QPlainTextEdit):
            self._editor_file_paths.pop(closed_widget, None)

        # Rebuild the index -> tool_id mapping since indices shifted
        self._tab_index_to_tool_id.clear()
        for tid, editor in self._editors.items():
            if self._canonical_tool_id(tid) != tid:
                continue
            idx = self._tabs.indexOf(editor)
            if idx >= 0:
                self._tab_index_to_tool_id[idx] = tid

        stale_paths = [
            path for path, editor in self._file_tabs.items()
            if self._tabs.indexOf(editor) < 0
        ]
        for path in stale_paths:
            editor = self._file_tabs.pop(path)
            self._editor_file_paths.pop(editor, None)

    def _rel_path(self, path: Path) -> str:
        if self._workspace_root is None:
            return str(path)
        try:
            return path.resolve().relative_to(self._workspace_root.resolve()).as_posix()
        except ValueError:
            return str(path)

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    @staticmethod
    def _tab_widget_style() -> str:
        """Return a dark, minimal QTabWidget stylesheet consistent with Aura."""
        return f"""
            QTabWidget::pane {{
                background: {BG};
                border: none;
                border-top: 1px solid {BORDER};
            }}
            QTabBar::tab {{
                background: {BG};
                color: {FG};
                border: 1px solid transparent;
                border-bottom: 1px solid {BORDER};
                padding: 6px 14px;
                margin-right: 2px;
                font-size: 12px;
            }}
            QTabBar::tab:hover {{
                background: #1e1e26;
                border-color: {BORDER};
            }}
            QTabBar::tab:selected {{
                background: #1c1c24;
                border: 1px solid {BORDER};
                border-bottom: 2px solid {ACCENT};
                color: {FG};
                font-weight: 600;
            }}
            QTabBar::close-button {{
                image: none;
                background: transparent;
                border: none;
                padding: 0;
                margin: 0 0 0 6px;
            }}
            QTabBar::close-button:hover {{
                background: rgba(247, 118, 142, 0.20);
                border-radius: 3px;
            }}
        """
