"""Tests for conversation replay — tool-card skipping and WorkerSummaryCard restoration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from aura.conversation.persistence import WorkerDispatchRecord
from aura.gui.conv_persistence import ConversationPersistence


# ---------------------------------------------------------------------------
# Fixtures (same pattern as tests/test_conv_persistence.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bridge():
    b = MagicMock()
    b.history.messages = [{"role": "user", "content": "hello"}]
    b.history.system_prompt = "Be helpful."
    b.planner_worker_mode = False
    b.dispatch_records = []
    b.registry.workspace_root = None
    return b


@pytest.fixture
def mock_chat():
    return MagicMock()


@pytest.fixture
def mock_playground():
    return MagicMock()


@pytest.fixture
def mock_input():
    return MagicMock()


@pytest.fixture
def mock_left_pane():
    return MagicMock()


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.temperature = 0.7
    s.worker_temperature = 0.5
    s.provider = "deepseek"
    s.system_prompt = ""
    s.planner_system_prompt = ""
    s.worker_system_prompt = ""
    return s


@pytest.fixture
def persistence(mock_bridge, mock_chat, mock_playground, mock_input,
                 mock_left_pane, mock_settings):
    return ConversationPersistence(
        bridge=mock_bridge,
        chat=mock_chat,
        playground=mock_playground,
        input_panel=mock_input,
        left_pane=mock_left_pane,
        settings=mock_settings,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_replay_skips_tool_call_rendering(persistence, mock_bridge, mock_chat):
    """Assistant messages with tool_calls must NOT call add_tool_call,
    append_tool_args, or set_tool_result on the chat mock."""
    mock_bridge.history.messages = [
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "Let me check that.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "read_file", "arguments": "{}"},
                },
            ],
        },
    ]
    # No dispatch records — nothing to restore
    mock_bridge.dispatch_records = []

    persistence.replay_history(synchronous=True)

    mock_chat.add_user.assert_called_once()
    mock_chat.begin_assistant.assert_called_once()
    mock_chat.append_content.assert_called_once_with("Let me check that.")
    mock_chat.assistant_done.assert_called_once()
    # Tool-call rendering methods must NOT be called
    mock_chat.add_tool_call.assert_not_called()
    mock_chat.append_tool_args.assert_not_called()
    mock_chat.set_tool_result.assert_not_called()


def test_replay_still_shows_user_messages(persistence, mock_bridge, mock_chat):
    """Normal user messages must still be replayed via add_user."""
    mock_bridge.history.messages = [
        {"role": "user", "content": "First message"},
        {"role": "user", "content": "Second message"},
    ]
    mock_bridge.dispatch_records = []

    persistence.replay_history(synchronous=True)

    assert mock_chat.add_user.call_count == 2
    mock_chat.add_user.assert_any_call("First message")
    mock_chat.add_user.assert_any_call("Second message")


def test_replay_still_shows_assistant_text(persistence, mock_bridge, mock_chat):
    """Assistant text content must still be replayed via begin_assistant/append_content."""
    mock_bridge.history.messages = [
        {"role": "user", "content": "Hi"},
        {
            "role": "assistant",
            "content": "Hello! How can I help?",
            "tool_calls": [],
        },
    ]
    mock_bridge.dispatch_records = []

    persistence.replay_history(synchronous=True)

    mock_chat.begin_assistant.assert_called_once()
    mock_chat.append_content.assert_called_once_with("Hello! How can I help?")
    mock_chat.assistant_done.assert_called_once()


def test_completed_dispatch_restores_summary_card(
    persistence, mock_bridge, mock_chat,
):
    """When dispatch_records contain a record with non-empty result_summary,
    add_worker_summary must be called with the right arguments."""
    mock_bridge.history.messages = [
        {"role": "user", "content": "Refactor the utils module"},
    ]
    mock_bridge.dispatch_records = [
        WorkerDispatchRecord(
            after_message_index=0,
            tool_call_id="dispatch_1",
            spec={"goal": "Refactor utils"},
            worker_history=[],
            result_summary="Refactored utils.py: extracted helpers.",
        ),
    ]

    persistence.replay_history(synchronous=True)

    mock_chat.add_worker_summary.assert_called_once_with(
        "dispatch_1",
        "Refactor utils",
        True,
        "Refactored utils.py: extracted helpers.",
    )


def test_incomplete_dispatch_omitted(persistence, mock_bridge, mock_chat):
    """When dispatch_records have an empty result_summary (in-flight/interrupted),
    add_worker_summary must NOT be called."""
    mock_bridge.history.messages = [
        {"role": "user", "content": "Clean up the code"},
    ]
    mock_bridge.dispatch_records = [
        WorkerDispatchRecord(
            after_message_index=0,
            tool_call_id="dispatch_2",
            spec={"goal": "Clean up code"},
            worker_history=[],
            result_summary="",  # In-flight / interrupted
        ),
    ]

    persistence.replay_history(synchronous=True)

    mock_chat.add_worker_summary.assert_not_called()


def test_mixed_messages_with_tool_calls(
    persistence, mock_bridge, mock_chat,
):
    """A realistic conversation with user messages, assistant text, tool calls,
    and a completed dispatch should replay user text, assistant text, and a
    WorkerSummaryCard — but no tool-call methods."""
    mock_bridge.history.messages = [
        {"role": "user", "content": "Can you update the config?"},
        {
            "role": "assistant",
            "content": "I'll dispatch a worker for that.",
            "tool_calls": [
                {
                    "id": "dispatch_3",
                    "function": {
                        "name": "dispatch_to_worker",
                        "arguments": '{"goal": "Update config"}',
                    },
                },
            ],
        },
    ]
    mock_bridge.dispatch_records = [
        WorkerDispatchRecord(
            after_message_index=1,
            tool_call_id="dispatch_3",
            spec={"goal": "Update config"},
            worker_history=[],
            result_summary="Updated config.yaml with new settings.",
        ),
    ]

    persistence.replay_history(synchronous=True)

    # User text replayed
    mock_chat.add_user.assert_called_once_with(
        "Can you update the config?"
    )
    # Assistant text replayed
    mock_chat.begin_assistant.assert_called_once()
    mock_chat.append_content.assert_called_once_with(
        "I'll dispatch a worker for that."
    )
    mock_chat.assistant_done.assert_called_once()
    # WorkerSummaryCard restored from dispatch records
    mock_chat.add_worker_summary.assert_called_once_with(
        "dispatch_3",
        "Update config",
        True,
        "Updated config.yaml with new settings.",
    )
    # Tool-call rendering methods must NOT be called
    mock_chat.add_tool_call.assert_not_called()
    mock_chat.append_tool_args.assert_not_called()
    mock_chat.set_tool_result.assert_not_called()
