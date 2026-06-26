from __future__ import annotations

import json
import threading
from unittest.mock import MagicMock, PropertyMock

from aura.client.events import ContentDelta, Done, ToolCallStart
from aura.conversation.history import History
from aura.conversation.manager import ConversationManager
from aura.conversation.tool_markup_guard import (
    RAW_TOOL_MARKUP_FAILURE_CLASS,
    RAW_TOOL_MARKUP_RETRY_INSTRUCTION,
    contains_raw_tool_markup,
)
from aura.conversation.tools._types import ApprovalDecision, ToolExecResult
from aura.conversation.tools.registry import ToolRegistry
from aura.hooks import hooks


def _done(content: str) -> Done:
    return Done(
        finish_reason="stop",
        full_message={
            "role": "assistant",
            "content": content,
            "reasoning_content": None,
        },
    )


def _tool_done(tool_call_id: str, name: str, args: dict) -> Done:
    return Done(
        finish_reason="tool_calls",
        full_message={
            "role": "assistant",
            "content": "",
            "reasoning_content": None,
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(args),
                    },
                }
            ],
        },
    )


def _worker_tools(tmp_path):
    tools = MagicMock(spec=ToolRegistry)
    tools.tool_defs.return_value = []
    tools.execute.return_value = ToolExecResult(
        ok=True,
        payload={"ok": True, "path": "sample.txt", "content": "data"},
    )
    type(tools).workspace_root = PropertyMock(return_value=tmp_path)
    type(tools).mode = PropertyMock(return_value="worker")
    return tools


def test_detects_raw_tool_call_markup_variants() -> None:
    assert contains_raw_tool_markup('<｜｜DSML｜｜tool_calls>')
    assert contains_raw_tool_markup('<｜｜DSML｜｜invoke name="write_file">')
    assert contains_raw_tool_markup('<| DSML | tool_calls>')
    assert contains_raw_tool_markup('<|DSML|invoke name="write_file">')
    assert contains_raw_tool_markup("<tool_calls>")
    assert contains_raw_tool_markup('<invoke name="write_file">')
    assert contains_raw_tool_markup("</｜｜DSML｜｜tool_calls>")
    assert not contains_raw_tool_markup("<continuation_report>")


def test_worker_retries_once_without_showing_raw_markup(tmp_path) -> None:
    history = History()
    tools = _worker_tools(tmp_path)
    manager = ConversationManager(history, tools)
    events = []
    fake_markup = '<｜｜DSML｜｜invoke name="write_file">'

    def backend(**_kwargs):
        yield ContentDelta(text=fake_markup)
        yield _done(fake_markup)

    backend_mock = MagicMock()
    backend_mock.side_effect = [
        backend(),
        iter([
            ToolCallStart(index=0, id="read1", name="read_file"),
            _tool_done("read1", "read_file", {"path": "sample.txt"}),
        ]),
        iter([ContentDelta(text="Done."), _done("Done.")]),
    ]
    hooks.register("generate_worker_code", backend_mock)
    try:
        manager.send(
            on_event=events.append,
            approval_cb=lambda _req: ApprovalDecision("approve"),
            cancel_event=threading.Event(),
            model="deepseek-chat",
            thinking="off",
            hook_name="generate_worker_code",
        )
    finally:
        hooks.unregister("generate_worker_code")

    visible_text = "".join(ev.text for ev in events if isinstance(ev, ContentDelta))
    assert fake_markup not in visible_text
    assert "Done." in visible_text
    assert any(
        msg.get("role") == "user" and msg.get("content") == RAW_TOOL_MARKUP_RETRY_INSTRUCTION
        for msg in history.messages
    )
    tools.execute.assert_called_once()


def test_repeated_worker_raw_markup_becomes_structured_boundary(tmp_path) -> None:
    history = History()
    tools = _worker_tools(tmp_path)
    manager = ConversationManager(history, tools)
    events = []
    fake_markup = '<｜｜DSML｜｜invoke name="write_file">'

    backend_mock = MagicMock()
    backend_mock.side_effect = [
        iter([ContentDelta(text=fake_markup), _done(fake_markup)]),
        iter([ContentDelta(text=fake_markup), _done(fake_markup)]),
    ]
    hooks.register("generate_worker_code", backend_mock)
    try:
        manager.send(
            on_event=events.append,
            approval_cb=lambda _req: ApprovalDecision("approve"),
            cancel_event=threading.Event(),
            model="deepseek-chat",
            thinking="off",
            hook_name="generate_worker_code",
        )
    finally:
        hooks.unregister("generate_worker_code")

    visible_text = "".join(ev.text for ev in events if isinstance(ev, ContentDelta))
    assert fake_markup not in visible_text
    payload = json.loads(visible_text)
    assert payload["failure_class"] == RAW_TOOL_MARKUP_FAILURE_CLASS
    assert payload["phase_boundary"] is True
    assert payload["needs_followup"] is True
    assert payload["followup_reason"] == RAW_TOOL_MARKUP_FAILURE_CLASS
    tools.execute.assert_not_called()
