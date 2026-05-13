"""Tests for chat code writer card routing."""

from __future__ import annotations

import pytest

from aura.gui.cards.code_writer_card import CodeWriterCard
from aura.gui.chat_view import ChatView


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_reuses_code_writer_card_for_repeated_path(qapp) -> None:
    chat = ChatView()
    chat.begin_assistant()

    chat.add_tool_call("tool-1", "edit_file")
    chat.append_tool_args("tool-1", '{"path": "a.py", "new_str": "one"}')

    cards = chat.findChildren(CodeWriterCard)
    assert len(cards) == 1
    first_card = cards[0]

    chat.add_tool_call("tool-2", "edit_file")
    chat.append_tool_args("tool-2", '{"path": "a.py", "new_str": "two"}')

    cards = chat.findChildren(CodeWriterCard)
    assert cards == [first_card]
    assert chat._tool_to_code_card["tool-1"] is first_card
    assert chat._tool_to_code_card["tool-2"] is first_card


def test_buffers_code_content_until_path_resolves(qapp) -> None:
    chat = ChatView()
    chat.begin_assistant()

    chat.add_tool_call("tool-1", "edit_file")
    chat.append_tool_args("tool-1", '{"new_str": "one"')

    assert chat.findChildren(CodeWriterCard) == []

    chat.append_tool_args("tool-1", ', "path": "a.py"}')
    cards = chat.findChildren(CodeWriterCard)

    assert len(cards) == 1
    assert chat._pending_code_content == {}
