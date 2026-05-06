"""Persistent tool window for worker dispatch output.

Shows worker streaming (reasoning, tool calls, diffs, code) with auto-scroll
for every dispatch in a single, persistent window pinned to the main window.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QScrollArea,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from aura.gui.chat_view import (
    AssistantCard,
    CodeWriterCard,
    DiffCard,
    ErrorCard,
    ToolCallCard,
)
from aura.gui.theme import BG, DANGER, FG, FG_DIM, SUCCESS


CODE_WRITER_NAMES = frozenset({"write_file", "edit_file"})


class WorkerWindow(QMainWindow):
    """Persistent OS-level window showing live worker activity for all dispatches."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._shutting_down: bool = False

        self.setWindowTitle("Worker Activity")
        self.resize(800, 700)

        # Dark themed
        self.setStyleSheet(f"QMainWindow {{ background: {BG}; }}")

        # Central scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(12)
        self._layout.addStretch(1)
        scroll.setWidget(container)
        self.setCentralWidget(scroll)
        self._scroll = scroll

        # Status bar
        self._status_bar = QStatusBar()
        self._status_bar.setStyleSheet(
            f"QStatusBar {{ background: {BG}; border-top: 1px solid {BG}; "
            f"color: {FG_DIM}; }}"
        )
        self._status_label = QLabel("Running…")
        self._status_label.setStyleSheet(f"color: {FG_DIM};")
        self._status_bar.addWidget(self._status_label, 1)
        self.setStatusBar(self._status_bar)

        # Internal state
        self._current_assistant: AssistantCard | None = None
        self._tool_cards: dict[str, ToolCallCard | CodeWriterCard] = {}
        self._tool_owner: dict[str, AssistantCard] = {}

    # ---- helpers -----------------------------------------------------------

    def _scroll_to_bottom(self) -> None:
        """Immediate scroll-to-bottom — no animation, needed for streaming."""
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        QApplication.processEvents()

    def _add_card(self, w: QWidget) -> None:
        self._layout.insertWidget(self._layout.count() - 1, w)
        self._scroll_to_bottom()

    def _current_or_new_assistant(self) -> AssistantCard:
        if self._current_assistant is None:
            return self.begin_assistant()
        return self._current_assistant

    # ---- public streaming API ----------------------------------------------

    def begin_assistant(self) -> AssistantCard:
        card = AssistantCard()
        self._current_assistant = card
        self._add_card(card)
        return card

    def append_reasoning(self, text: str) -> None:
        self._current_or_new_assistant().append_reasoning(text)
        self._scroll_to_bottom()

    def append_content(self, text: str) -> None:
        ac = self._current_or_new_assistant()
        ac.reasoning_done()
        ac.append_content(text)
        self._scroll_to_bottom()

    def add_tool_call(self, worker_tool_id: str, name: str) -> None:
        ac = self._current_or_new_assistant()
        if name in CODE_WRITER_NAMES:
            card: ToolCallCard | CodeWriterCard = CodeWriterCard(name)
        else:
            card = ToolCallCard(name)
        # Add directly to the assistant's tool cluster (bypass add_tool_card
        # which always creates a plain ToolCallCard).
        ac._tool_cards[worker_tool_id] = card
        if not ac._tool_cluster.isVisible():
            ac._tool_cluster.setVisible(True)
        ac._tool_cluster_layout.addWidget(card)
        self._tool_cards[worker_tool_id] = card
        self._tool_owner[worker_tool_id] = ac
        self._scroll_to_bottom()

    def append_tool_args(self, worker_tool_id: str, fragment: str) -> None:
        card = self._tool_cards.get(worker_tool_id)
        if card is not None:
            card.append_args(fragment)
        self._scroll_to_bottom()

    def set_tool_result(self, worker_tool_id: str, ok: bool, result: str) -> None:
        card = self._tool_cards.get(worker_tool_id)
        if card is not None:
            card.set_result(ok, result)
        self._scroll_to_bottom()

    def add_diff_card(
        self,
        worker_tool_id: str,
        rel_path: str,
        old: str,
        new: str,
        decision: str,
        is_new_file: bool,
    ) -> None:
        ac = self._tool_owner.get(worker_tool_id) or self._current_or_new_assistant()
        card = DiffCard(rel_path, old, new, decision, is_new_file)
        ac.add_footer_widget(card)
        self._scroll_to_bottom()

    def add_error(self, message: str) -> None:
        err = ErrorCard("Worker error", message)
        self._add_card(err)

    def worker_finished(self, ok: bool, summary: str) -> None:
        # Finalize the last assistant card's markdown
        ac = self._current_assistant
        if ac is not None:
            ac.finalize_content()
            self._current_assistant = None

        if ok:
            self._status_label.setText("Completed")
            self._status_label.setStyleSheet(f"color: {SUCCESS}; font-weight: 600;")
        else:
            self._status_label.setText("Completed with errors")
            self._status_label.setStyleSheet(f"color: {DANGER}; font-weight: 600;")

    def worker_cancelled(self) -> None:
        self._status_label.setText("Cancelled")
        self._status_label.setStyleSheet(f"color: {DANGER};")

    def clear(self) -> None:
        """Remove all cards and reset state (called on New Conversation)."""
        # Remove every widget from the layout except the trailing stretch.
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        self._current_assistant = None
        self._tool_cards.clear()
        self._tool_owner.clear()

    def shutdown(self) -> None:
        """Permanently close and destroy this window (used on New Conversation)."""
        self._shutting_down = True
        self.close()

    # ---- close event -------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._shutting_down:
            event.accept()
            return
        # Just hide — the window can be re-shown via "View Worker".
        self.hide()
        event.ignore()
