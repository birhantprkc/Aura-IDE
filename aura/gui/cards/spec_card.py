"""Worker dispatch spec — collapsible, with Dispatch/Edit/Cancel buttons."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from aura.gui.cards._collapsible import _CollapsibleSection
from aura.gui.cards._helpers import _MarkdownTextBlock
from aura.gui.markdown_renderer import _render_markdown_with_code
from aura.gui.theme import ACCENT, BG_ALT, BG_RAISED, BORDER, DANGER, FG, FG_DIM, FG_MUTED, SUCCESS, WARN


class SpecCard(QFrame):
    """Worker dispatch spec — collapsible, with Dispatch/Edit/Cancel buttons.

    After dispatch, the buttons collapse into a status header and a "View Worker"
    button appears to open the pop-out WorkerWindow.
    """

    dispatch_clicked = Signal(str)  # tool_call_id (with current spec values)
    edit_clicked = Signal(str)
    cancel_clicked = Signal(str)
    view_worker_clicked = Signal(str)  # tool_call_id

    def __init__(
        self,
        tool_call_id: str,
        goal: str,
        files: list[str],
        spec: str,
        acceptance: str,
        summary: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._tool_call_id = tool_call_id
        self._goal = goal
        self._files = files
        self._spec = spec
        self._acceptance = acceptance
        self._summary = summary
        self._dispatched = False
        self._cancelled = False
        self._worker_running = False

        self.setStyleSheet(
            f"QFrame#card {{ background: {BG_ALT}; "
            f"border: 1px solid rgba(255, 255, 255, 0.08); "
            f"border-left: 3px solid {ACCENT}; border-radius: 8px; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(8)

        # ---- Header row: "Plan Ready" + chips ----
        header_row = QHBoxLayout()
        header_label = QLabel("⚡ Plan Ready", parent=self)
        header_label.setStyleSheet(f"color: {ACCENT}; font-weight: 700; font-size: 12px;")
        header_row.addWidget(header_label)
        header_row.addStretch(1)

        _chip_style = (
            f"background: {BG_RAISED}; color: {FG_DIM}; "
            f"border: 1px solid {BORDER}; border-radius: 4px; "
            f"padding: 2px 8px; font-size: 10px; font-weight: 600;"
        )
        planner_chip = QLabel("Planner", parent=self)
        planner_chip.setStyleSheet(_chip_style)
        header_row.addWidget(planner_chip)

        review_chip = QLabel("Review", parent=self)
        review_chip.setStyleSheet(
            _chip_style.replace(f"color: {FG_DIM}", f"color: {WARN}")
        )
        header_row.addWidget(review_chip)

        outer.addLayout(header_row)

        # ---- Goal ----
        self._goal_label = _MarkdownTextBlock(_render_markdown_with_code(self._goal), parent=self)
        self._goal_label.setStyleSheet(f"background: transparent; border: none; color: {FG}; font-size: 14px;")
        outer.addWidget(self._goal_label)

        # ---- STRATEGY section ----
        outer.addSpacing(6)
        strategy_header = QLabel("STRATEGY", parent=self)
        strategy_header.setStyleSheet(f"color: {FG_MUTED}; font-weight: 700; font-size: 10px;")
        outer.addWidget(strategy_header)

        strategy_text = self._compute_strategy_text()
        self._strategy_label = _MarkdownTextBlock(
            _render_markdown_with_code(strategy_text), parent=self
        )
        self._strategy_label.setStyleSheet(f"background: transparent; border: none; color: {FG};")
        outer.addWidget(self._strategy_label)

        # ---- SCOPE section (formerly FILES) ----
        outer.addSpacing(6)
        self._files_header = QLabel("SCOPE", parent=self)
        self._files_header.setStyleSheet(f"color: {FG_MUTED}; font-weight: 700; font-size: 10px;")
        outer.addWidget(self._files_header)

        self._files_container = QWidget(self)
        files_layout = QVBoxLayout(self._files_container)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(4)
        outer.addWidget(self._files_container)

        self._refresh_files_list(files_layout)

        # ---- VALIDATION section (formerly ACCEPTANCE CRITERIA) ----
        outer.addSpacing(6)
        acc_header = QLabel("VALIDATION", parent=self)
        acc_header.setStyleSheet(f"color: {FG_MUTED}; font-weight: 700; font-size: 10px;")
        outer.addWidget(acc_header)

        self._acceptance_label = _MarkdownTextBlock(
            _render_markdown_with_code(self._acceptance), parent=self
        )
        self._acceptance_label.setStyleSheet(f"background: transparent; border: none; color: {FG_DIM};")
        outer.addWidget(self._acceptance_label)

        # ---- FULL WORKER SPEC section ----
        outer.addSpacing(6)
        raw_spec_header = QLabel("FULL WORKER SPEC", parent=self)
        raw_spec_header.setStyleSheet(f"color: {FG_MUTED}; font-weight: 700; font-size: 10px;")
        outer.addWidget(raw_spec_header)

        self._spec_body_label = _MarkdownTextBlock(
            _render_markdown_with_code(self._spec), parent=self
        )
        self._spec_body_label.setStyleSheet(f"background: transparent; border: none; color: {FG};")

        self._raw_spec_section: _CollapsibleSection | None = None
        if self._spec.count("\n") > 6 or len(self._spec) > 600:
            section = _CollapsibleSection(
                "Show Full Spec", self._spec_body_label, start_open=False, prominent=False
            )
            self._raw_spec_section = section
            outer.addWidget(section)
        else:
            outer.addWidget(self._spec_body_label)

        # ---- Buttons row ----
        self._buttons_row = QWidget(self)
        btn_layout = QHBoxLayout(self._buttons_row)
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(8)

        self._dispatch_btn = QPushButton("Dispatch", parent=self._buttons_row)
        self._dispatch_btn.setObjectName("primary")
        self._dispatch_btn.clicked.connect(self._on_dispatch)
        btn_layout.addWidget(self._dispatch_btn)

        self._edit_btn = QPushButton("Edit Spec", parent=self._buttons_row)
        self._edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self._tool_call_id))
        btn_layout.addWidget(self._edit_btn)

        self._make_smaller_btn = QPushButton("Make Smaller", parent=self._buttons_row)
        self._make_smaller_btn.setEnabled(False)
        self._make_smaller_btn.setToolTip("Spec rewrite controls coming soon")
        btn_layout.addWidget(self._make_smaller_btn)

        self._make_safer_btn = QPushButton("Make Safer", parent=self._buttons_row)
        self._make_safer_btn.setEnabled(False)
        self._make_safer_btn.setToolTip("Spec rewrite controls coming soon")
        btn_layout.addWidget(self._make_safer_btn)

        self._go_deeper_btn = QPushButton("Go Deeper", parent=self._buttons_row)
        self._go_deeper_btn.setEnabled(False)
        self._go_deeper_btn.setToolTip("Spec rewrite controls coming soon")
        btn_layout.addWidget(self._go_deeper_btn)

        self._cancel_btn = QPushButton("Cancel", parent=self._buttons_row)
        self._cancel_btn.setObjectName("danger")
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)

        btn_layout.addStretch(1)

        outer.addWidget(self._buttons_row)

        # ---- "View Worker" button — hidden until dispatch ----
        self._view_worker_btn = QPushButton("View Worker", parent=self)
        self._view_worker_btn.setVisible(False)
        self._view_worker_btn.clicked.connect(
            lambda: self.view_worker_clicked.emit(self._tool_call_id)
        )
        outer.addWidget(self._view_worker_btn)

        # ---- Status label, hidden until dispatch/cancel ----
        self._status_label = QLabel("", parent=self)
        self._status_label.setStyleSheet(f"color: {FG_DIM}; font-size: 11px;")
        self._status_label.setVisible(False)
        outer.addWidget(self._status_label)

    # ---- helpers ---------------------------------------------------------

    def _refresh_files_list(self, layout: QVBoxLayout) -> None:
        # Clear layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self._files:
            lbl = QLabel("(no files listed)", parent=self._files_container)
            lbl.setStyleSheet(f"color: {FG_MUTED}; font-style: italic; font-size: 11px;")
            layout.addWidget(lbl)
            return

        for path in self._files:
            row = QWidget(self._files_container)
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            
            icon = QLabel("📄", parent=row) # Could use a real SVG icon later
            icon.setFixedWidth(16)
            h.addWidget(icon)
            
            p_lbl = QLabel(path, parent=row)
            p_lbl.setStyleSheet(
                f"color: {FG_DIM}; font-family: 'Geist Mono', 'JetBrains Mono', monospace; "
                "font-size: 11px;"
            )
            h.addWidget(p_lbl)
            h.addStretch(1)
            layout.addWidget(row)

    @staticmethod
    def _format_files(files: list[str]) -> str:
        if not files:
            return "(no files listed)"
        return "  ".join(f"• {p}" for p in files)

    def _compute_strategy_text(self) -> str:
        """Return the text to display in the STRATEGY section."""
        if self._summary:
            return self._summary
        if len(self._spec) <= 600 and self._spec.count("\n") <= 6:
            return self._spec
        return self._spec[:300] + "…"

    def update_spec(
        self, goal: str, files: list[str], spec: str, acceptance: str, summary: str = ""
    ) -> None:
        self._goal = goal
        self._files = list(files)
        self._spec = spec
        self._acceptance = acceptance
        self._summary = summary
        self._goal_label.setHtml(_render_markdown_with_code(self._goal))

        # Refresh files list
        if hasattr(self, "_files_container"):
            self._refresh_files_list(self._files_container.layout())

        # Update strategy label
        strategy_text = self._compute_strategy_text()
        if hasattr(self, "_strategy_label"):
            self._strategy_label.setHtml(_render_markdown_with_code(strategy_text))

        # Update raw spec body
        if hasattr(self, "_spec_body_label"):
            self._spec_body_label.setHtml(_render_markdown_with_code(self._spec))

        self._acceptance_label.setHtml(_render_markdown_with_code(self._acceptance))

    def current_spec(self) -> tuple[str, list[str], str, str, str]:
        return (self._goal, list(self._files), self._spec, self._acceptance, self._summary)

    def tool_call_id(self) -> str:
        return self._tool_call_id

    # ---- button handlers -------------------------------------------------

    def _on_dispatch(self) -> None:
        self._dispatched = True
        self._worker_running = True
        self._buttons_row.setVisible(False)
        self._status_label.setText("Worker running…")
        self._status_label.setVisible(True)
        self._view_worker_btn.setVisible(True)
        self.dispatch_clicked.emit(self._tool_call_id)

    def _on_cancel(self) -> None:
        self._cancelled = True
        self._buttons_row.setVisible(False)
        self._status_label.setText("Cancelled.")
        self._status_label.setStyleSheet(f"color: {DANGER}; font-size: 11px;")
        self._status_label.setVisible(True)
        self.cancel_clicked.emit(self._tool_call_id)

    def disable_buttons(self) -> None:
        self._dispatch_btn.setEnabled(False)
        self._edit_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._make_smaller_btn.setEnabled(False)
        self._make_safer_btn.setEnabled(False)
        self._go_deeper_btn.setEnabled(False)

    def worker_finished(self, ok: bool, summary: str) -> None:
        self._worker_running = False
        verb = "Completed" if ok else "Completed with errors"
        color = SUCCESS if ok else DANGER
        self._status_label.setText(verb)
        self._status_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        # Keep "View Worker" button visible for later review.

    def set_dispatched_and_finished(self, ok: bool) -> None:
        """Force the card into a read-only finished state (for history replay)."""
        self._dispatched = True
        self._worker_running = False
        self._buttons_row.setVisible(False)
        verb = "Completed" if ok else "Completed with errors"
        color = SUCCESS if ok else DANGER
        self._status_label.setText(verb)
        self._status_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._status_label.setVisible(True)
        # Note: We don't show the "View Worker" button during replay because
        # the background worker process doesn't exist anymore.
