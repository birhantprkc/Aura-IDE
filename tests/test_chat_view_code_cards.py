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


class TestComputeChangedRegion:
    """Tests for CodeWriterCard._compute_changed_region pure helper."""

    def test_identical_text(self):
        assert CodeWriterCard._compute_changed_region("abc", "abc") == (3, 0, "", "")

    def test_insertion_middle(self):
        assert CodeWriterCard._compute_changed_region("abc", "abXYZc") == (2, 1, "", "XYZ")

    def test_deletion_middle(self):
        assert CodeWriterCard._compute_changed_region("abXYZc", "abc") == (2, 1, "XYZ", "")

    def test_replacement_middle(self):
        assert CodeWriterCard._compute_changed_region("abXXXc", "abYYc") == (2, 1, "XXX", "YY")

    def test_no_common_suffix(self):
        assert CodeWriterCard._compute_changed_region("abcdef", "abcXYZ") == (3, 0, "def", "XYZ")

    def test_no_common_prefix(self):
        assert CodeWriterCard._compute_changed_region("XXXX", "YYYY") == (0, 0, "XXXX", "YYYY")

    def test_empty_old(self):
        assert CodeWriterCard._compute_changed_region("", "hello") == (0, 0, "", "hello")

    def test_empty_new(self):
        assert CodeWriterCard._compute_changed_region("hello", "") == (0, 0, "hello", "")

    def test_both_empty(self):
        assert CodeWriterCard._compute_changed_region("", "") == (0, 0, "", "")

    def test_prefix_overlaps_suffix(self):
        # "aba" vs "aca": prefix="a", suffix="a" (position 2, no overlap with prefix at 0)
        # prefix_len=1, suffix_len=1, old_mid="b", new_mid="c"
        result = CodeWriterCard._compute_changed_region("aba", "aca")
        assert result == (1, 1, "b", "c"), f"Got {result}"
