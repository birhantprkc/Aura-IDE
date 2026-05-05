"""Bridge between the (sync) ConversationManager worker thread and Qt's GUI thread.

- send() spawns a QThread that runs ConversationManager.send.
- Each event becomes a Qt signal on the GUI thread.
- The approval callback is bridged via QMetaObject.invokeMethod with
  Qt.BlockingQueuedConnection — the worker thread blocks until the user clicks
  in the modal dialog on the main thread.
"""
from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import (
    Q_ARG,
    QMetaObject,
    QObject,
    QThread,
    Qt,
    Signal,
    Slot,
)

from aura.client import (
    ApiError,
    ContentDelta,
    DeepSeekClient,
    Done,
    Event,
    ReasoningDelta,
    ToolCallArgsDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolResult,
    Usage,
)
from aura.config import ModelId, ThinkingMode
from aura.conversation import ConversationManager, History
from aura.conversation.tools import (
    ApprovalDecision,
    ApprovalRequest,
    ToolRegistry,
)
from aura.gui.diff_dialog import DiffApprovalDialog


class _Worker(QObject):
    """Lives on the worker thread. Runs the conversation loop."""

    reasoningDelta = Signal(str)
    contentDelta = Signal(str)
    toolCallStart = Signal(int, str, str)  # index, id, name
    toolCallArgs = Signal(int, str)  # index, fragment
    toolCallEnd = Signal(int)
    usageEmitted = Signal(int, int, int, int)  # prompt, completion, hit, miss
    apiError = Signal(int, str)  # status (-1 if None), message
    streamDone = Signal(str, dict)  # finish_reason, full_message
    toolResultEmitted = Signal(str, str, bool, str, dict)
    finished = Signal()

    def __init__(
        self,
        manager: ConversationManager,
        approval_proxy: "_ApprovalProxy",
        cancel_event: threading.Event,
        model: ModelId,
        thinking: ThinkingMode,
    ) -> None:
        super().__init__()
        self._manager = manager
        self._approval_proxy = approval_proxy
        self._cancel = cancel_event
        self._model = model
        self._thinking = thinking
        # Track tool name by id so result event can label it.
        self._tool_id_to_index: dict[int, str] = {}

    @Slot()
    def run(self) -> None:
        try:
            self._manager.send(
                on_event=self._on_event,
                approval_cb=self._approval_proxy.request_approval,
                cancel_event=self._cancel,
                model=self._model,
                thinking=self._thinking,
            )
        except Exception as exc:
            self.apiError.emit(-1, f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()

    def _on_event(self, ev: Event) -> None:
        if isinstance(ev, ReasoningDelta):
            self.reasoningDelta.emit(ev.text)
        elif isinstance(ev, ContentDelta):
            self.contentDelta.emit(ev.text)
        elif isinstance(ev, ToolCallStart):
            self.toolCallStart.emit(ev.index, ev.id, ev.name)
        elif isinstance(ev, ToolCallArgsDelta):
            self.toolCallArgs.emit(ev.index, ev.args_chunk)
        elif isinstance(ev, ToolCallEnd):
            self.toolCallEnd.emit(ev.index)
        elif isinstance(ev, Usage):
            self.usageEmitted.emit(
                ev.prompt_tokens, ev.completion_tokens, ev.cache_hit_tokens, ev.cache_miss_tokens
            )
        elif isinstance(ev, ApiError):
            self.apiError.emit(ev.status_code if ev.status_code is not None else -1, ev.message)
        elif isinstance(ev, Done):
            self.streamDone.emit(ev.finish_reason or "", ev.full_message)
        elif isinstance(ev, ToolResult):
            self.toolResultEmitted.emit(ev.tool_call_id, ev.name, ev.ok, ev.result, ev.extras or {})


class _ApprovalProxy(QObject):
    """Marshals approval requests from the worker thread onto the GUI thread.

    The worker calls request_approval() which uses QMetaObject.invokeMethod with
    BlockingQueuedConnection, synchronously running _open_dialog on the GUI thread.
    """

    def __init__(self, parent_widget) -> None:
        super().__init__()
        self._parent_widget = parent_widget
        self._last_decision: ApprovalDecision = ApprovalDecision(action="reject")
        self._last_request: ApprovalRequest | None = None
        # Side-channel for bridge consumers to know what was decided + on what.
        self.last_event: dict[str, Any] | None = None

    def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        # Called from worker thread. Block until GUI thread has shown the dialog.
        self._last_request = request
        QMetaObject.invokeMethod(
            self,
            "_open_dialog",
            Qt.ConnectionType.BlockingQueuedConnection,
        )
        return self._last_decision

    @Slot()
    def _open_dialog(self) -> None:
        # Runs on GUI thread.
        req = self._last_request
        if req is None:
            self._last_decision = ApprovalDecision(action="reject")
            return
        dlg = DiffApprovalDialog(req, parent=self._parent_widget)
        dlg.exec()
        self._last_decision = dlg.decision()
        self.last_event = {
            "rel_path": req.rel_path,
            "old_content": req.old_content,
            "new_content": req.new_content,
            "is_new_file": req.is_new_file,
            "decision": self._last_decision.action,
        }


class ConversationBridge(QObject):
    """Public Qt-facing facade for one running conversation.

    Owns the ConversationManager + History + ToolRegistry. The MainWindow
    creates one bridge per app session and reuses it across turns.
    """

    reasoningDelta = Signal(str)
    contentDelta = Signal(str)
    toolCallStart = Signal(str, str)  # tool_call_id, name
    toolCallArgs = Signal(str, str)  # tool_call_id, fragment
    toolCallEnd = Signal(str)  # tool_call_id
    apiError = Signal(int, str)
    streamDone = Signal(str, dict)
    toolResult = Signal(str, str, bool, str, dict)  # id, name, ok, result, extras
    diffApplied = Signal(str, str, str, str, bool)  # tool_call_id, rel_path, old, new, is_new_file -> approve
    diffDecided = Signal(str, str, str, str, str, bool)
    # diffDecided: tool_call_id, decision, rel_path, old, new, is_new_file
    started = Signal()
    finished = Signal()
    usageEmitted = Signal(int, int, int, int)

    def __init__(self, parent_widget) -> None:
        super().__init__()
        self._client = DeepSeekClient()
        self._history = History()
        self._registry = ToolRegistry(workspace_root=_dummy_root())
        self._manager = ConversationManager(self._client, self._history, self._registry)
        self._parent_widget = parent_widget
        self._approval_proxy = _ApprovalProxy(parent_widget)
        self._cancel: threading.Event = threading.Event()
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        # Map streaming-index -> tool_call_id (for routing args/end events).
        self._index_to_id: dict[int, str] = {}
        self._index_to_name: dict[int, str] = {}
        # Pending approval correlation: when worker's tool_call_id is unknown to
        # _ApprovalProxy, we match by rel_path and most-recent worker tool id.
        self._last_proposed_tool_call_id: str | None = None

    # ---- config -----------------------------------------------------------

    @property
    def history(self) -> History:
        return self._history

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def set_workspace_root(self, root) -> None:
        self._registry.set_workspace_root(root)

    def set_read_only(self, value: bool) -> None:
        self._registry.set_read_only(value)

    def set_system_prompt(self, prompt: str) -> None:
        self._history.set_system(prompt)

    def reset_history(self) -> None:
        self._history.messages.clear()
        self._index_to_id.clear()
        self._index_to_name.clear()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    # ---- send / cancel ----------------------------------------------------

    def send(self, model: ModelId, thinking: ThinkingMode) -> None:
        if self.is_running():
            return
        self._cancel = threading.Event()
        self._index_to_id.clear()
        self._index_to_name.clear()
        self._thread = QThread()
        self._worker = _Worker(
            manager=self._manager,
            approval_proxy=self._approval_proxy,
            cancel_event=self._cancel,
            model=model,
            thinking=thinking,
        )
        self._worker.moveToThread(self._thread)

        # Wire signals from worker to bridge.
        self._worker.reasoningDelta.connect(self.reasoningDelta)
        self._worker.contentDelta.connect(self.contentDelta)
        self._worker.toolCallStart.connect(self._on_tool_call_start)
        self._worker.toolCallArgs.connect(self._on_tool_call_args)
        self._worker.toolCallEnd.connect(self._on_tool_call_end)
        self._worker.apiError.connect(self.apiError)
        self._worker.streamDone.connect(self.streamDone)
        self._worker.toolResultEmitted.connect(self._on_tool_result)
        self._worker.usageEmitted.connect(self.usageEmitted)
        self._worker.finished.connect(self._on_finished)

        self._thread.started.connect(self._worker.run)
        self.started.emit()
        self._thread.start()

    def request_cancel(self) -> None:
        self._cancel.set()

    # ---- private slots ----------------------------------------------------

    @Slot(int, str, str)
    def _on_tool_call_start(self, index: int, tool_id: str, name: str) -> None:
        self._index_to_id[index] = tool_id
        self._index_to_name[index] = name
        self._last_proposed_tool_call_id = tool_id
        self.toolCallStart.emit(tool_id, name)

    @Slot(int, str)
    def _on_tool_call_args(self, index: int, fragment: str) -> None:
        tool_id = self._index_to_id.get(index, "")
        if tool_id:
            self.toolCallArgs.emit(tool_id, fragment)

    @Slot(int)
    def _on_tool_call_end(self, index: int) -> None:
        tool_id = self._index_to_id.get(index, "")
        if tool_id:
            self.toolCallEnd.emit(tool_id)

    @Slot(str, str, bool, str, dict)
    def _on_tool_result(
        self, tool_id: str, name: str, ok: bool, result: str, extras: dict
    ) -> None:
        # If this was an approval-bearing tool, surface a diff card with the user's decision.
        approval = extras.get("approval")
        if approval and self._approval_proxy.last_event is not None:
            ev = self._approval_proxy.last_event
            self.diffDecided.emit(
                tool_id,
                str(approval),
                str(ev["rel_path"]),
                str(ev["old_content"]),
                str(ev["new_content"]),
                bool(ev["is_new_file"]),
            )
            self._approval_proxy.last_event = None
        self.toolResult.emit(tool_id, name, ok, result, extras)

    @Slot()
    def _on_finished(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread.deleteLater()
        if self._worker is not None:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None
        self.finished.emit()


def _dummy_root():
    """Returns an existing path so ToolRegistry init doesn't fail. The real
    workspace is set via set_workspace_root() before any tool is dispatched."""
    from pathlib import Path
    return Path.home()
