"""Main application window: three-pane splitter, toolbar, chat + input."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from aura.bridge import ConversationBridge
from aura.config import (
    APP_NAME,
    DEFAULT_MODEL,
    DEFAULT_THINKING,
    MODELS,
    ModelId,
    ThinkingMode,
    load_workspace_root,
    save_workspace_root,
)
from aura.gui.chat_view import ChatView
from aura.gui.input_panel import Attachment, InputPanel, SendPayload
from aura.gui.theme import BG, BG_ALT, BORDER, FG, FG_DIM, FG_MUTED, WARN

SYSTEM_PROMPT = (
    "You are Aura, a desktop assistant focused on troubleshooting code with the user.\n"
    "You have filesystem tools (read_file, list_directory, glob, write_file, edit_file) "
    "scoped to the user's workspace. Workspace-relative paths only.\n"
    "When the user asks about their code, USE the tools to read the actual files before "
    "answering — do not guess. When proposing changes, prefer edit_file with a tightly-"
    "scoped old_str (include enough surrounding context that it's unique) over write_file. "
    "Every write requires the user's approval through a diff dialog. If a write tool is "
    "not available, the user has enabled Read-Only Mode; explain what you would change "
    "instead. Be concise; show the user code, not prose, where it helps. Never fabricate "
    "file contents or call paths you have not verified with read_file."
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 900)

        # Workspace.
        self._workspace_root: Path | None = load_workspace_root()
        if self._workspace_root is None:
            self._workspace_root = Path.cwd()

        # Bridge.
        self._bridge = ConversationBridge(parent_widget=self)
        self._bridge.set_workspace_root(self._workspace_root)
        self._bridge.set_system_prompt(SYSTEM_PROMPT)

        # ----- toolbar ----
        self._toolbar = QToolBar("Main")
        self._toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)
        self._build_toolbar()

        # ----- splitter ----
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # Left pane (Phase 1: workspace label + change root only)
        self._left_pane = self._build_left_pane()
        splitter.addWidget(self._left_pane)

        # Right pane = chat view + input panel
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._chat = ChatView()
        right_layout.addWidget(self._chat, 1)

        self._input = InputPanel(self._workspace_root)
        right_layout.addWidget(self._input)

        splitter.addWidget(right)
        splitter.setSizes([280, 1120])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.setCentralWidget(splitter)

        # ----- wire bridge ↔ view -----
        self._bridge.started.connect(self._on_started)
        self._bridge.finished.connect(self._on_finished)
        self._bridge.reasoningDelta.connect(self._chat.append_reasoning)
        self._bridge.contentDelta.connect(self._chat.append_content)
        self._bridge.toolCallStart.connect(self._chat.add_tool_call)
        self._bridge.toolCallArgs.connect(self._chat.append_tool_args)
        self._bridge.toolCallEnd.connect(lambda _id: None)
        self._bridge.toolResult.connect(self._on_tool_result)
        self._bridge.diffDecided.connect(self._on_diff_decided)
        self._bridge.streamDone.connect(self._on_stream_done)
        self._bridge.apiError.connect(self._on_api_error)

        self._input.sent.connect(self._on_send)
        self._input.stop_requested.connect(self._on_stop)

        self._update_workspace_label()

    # ----- toolbar build --------------------------------------------------

    def _build_toolbar(self) -> None:
        new_act = QAction("New Conversation", self)
        new_act.triggered.connect(self._on_new_conversation)
        self._toolbar.addAction(new_act)

        self._toolbar.addSeparator()

        # Read-Only toggle: prominent, with lock icon when on.
        self._read_only_act = QAction("Read-Only Mode", self)
        self._read_only_act.setCheckable(True)
        self._read_only_act.setChecked(False)
        self._read_only_act.triggered.connect(self._on_read_only_toggled)
        self._toolbar.addAction(self._read_only_act)

        self._read_only_badge = QLabel("")
        self._read_only_badge.setObjectName("readOnlyBadge")
        self._toolbar.addWidget(self._read_only_badge)

        # Spacer.
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._toolbar.addWidget(spacer)

        # Right side: workspace name (small)
        self._toolbar_workspace_label = QLabel("")
        self._toolbar_workspace_label.setStyleSheet(f"color: {FG_DIM};")
        self._toolbar.addWidget(self._toolbar_workspace_label)

    # ----- left pane ------------------------------------------------------

    def _build_left_pane(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("leftPane")
        frame.setMinimumWidth(220)
        frame.setMaximumWidth(420)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)

        title = QLabel("Workspace")
        title.setObjectName("paneTitle")
        layout.addWidget(title)

        self._workspace_label = QLabel("")
        self._workspace_label.setObjectName("workspaceLabel")
        self._workspace_label.setWordWrap(True)
        layout.addWidget(self._workspace_label)

        change_btn = QPushButton("Change Root...")
        change_btn.clicked.connect(self._on_change_root)
        layout.addWidget(change_btn)

        layout.addSpacing(12)

        hint = QLabel("Workspace tree, search, and history land in Phase 2.")
        hint.setObjectName("workspaceHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch(1)
        return frame

    # ----- handlers -------------------------------------------------------

    def _on_change_root(self) -> None:
        start = str(self._workspace_root) if self._workspace_root else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose workspace root", start)
        if not chosen:
            return
        path = Path(chosen)
        self._workspace_root = path
        self._bridge.set_workspace_root(path)
        self._input.set_workspace_root(path)
        save_workspace_root(path)
        self._update_workspace_label()

    def _update_workspace_label(self) -> None:
        if self._workspace_root is None:
            self._workspace_label.setText("(none)")
            self._toolbar_workspace_label.setText("")
            return
        full = str(self._workspace_root)
        self._workspace_label.setText(full)
        self._toolbar_workspace_label.setText(self._workspace_root.name)

    def _on_read_only_toggled(self, checked: bool) -> None:
        self._bridge.set_read_only(checked)
        if checked:
            self._read_only_act.setText("\U0001F512 Read-Only Mode")  # lock
            self._read_only_badge.setText("READ-ONLY")
        else:
            self._read_only_act.setText("Read-Only Mode")
            self._read_only_badge.setText("")

    def _on_new_conversation(self) -> None:
        if self._bridge.is_running():
            QMessageBox.information(
                self, APP_NAME, "Wait for the current response to finish, or click Stop."
            )
            return
        self._bridge.reset_history()
        self._chat.reset()

    def _on_send(self, payload: SendPayload) -> None:
        if self._bridge.is_running():
            return
        # Prepare history append: image attachments go via multimodal content array.
        text = payload.text
        # Add text refs from non-image attachments to the text body so the model knows.
        text_refs = [a.text_ref for a in payload.attachments if a.text_ref]
        if text_refs:
            ref_block = "\n".join(text_refs)
            text = f"{text}\n\n{ref_block}".strip() if text else ref_block
        image_atts = [a for a in payload.attachments if a.kind == "image" and a.b64]

        if image_atts:
            parts = []
            if text:
                parts.append({"type": "text", "text": text})
            for a in image_atts:
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{a.b64}"},
                    }
                )
            self._bridge.history.append_user_multimodal(parts)
        else:
            self._bridge.history.append_user_text(text)

        self._chat.add_user(text, [a.b64 for a in image_atts] or None)
        self._chat.begin_assistant()

        self._bridge.send(
            model=self._input.current_model(),
            thinking=self._input.current_thinking(),
        )

    def _on_stop(self) -> None:
        self._bridge.request_cancel()

    def _on_started(self) -> None:
        self._input.set_streaming(True)

    def _on_finished(self) -> None:
        self._input.set_streaming(False)
        self._chat.assistant_done()
        self._input.focus_editor()

    def _on_stream_done(self, finish_reason: str, full_message: dict) -> None:
        # Render markdown for the final answer.
        self._chat.assistant_done()
        # If the model finished with no tool_calls, this is the end of the turn —
        # bridge.finished will fire next.

    def _on_tool_result(self, tool_id: str, name: str, ok: bool, result: str, extras: dict) -> None:
        self._chat.set_tool_result(tool_id, ok, result)

    def _on_diff_decided(
        self,
        tool_call_id: str,
        decision: str,
        rel_path: str,
        old: str,
        new: str,
        is_new_file: bool,
    ) -> None:
        self._chat.add_diff_card(tool_call_id, rel_path, old, new, decision, is_new_file)

    def _on_api_error(self, status: int, message: str) -> None:
        title = f"API Error {status}" if status > 0 else "Error"
        self._chat.add_error(title, message)
