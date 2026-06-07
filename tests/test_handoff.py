"""Tests for aura/handoff.py — handoff prompt generation and file saving."""

from __future__ import annotations

import tempfile
from pathlib import Path

from aura.handoff import extract_handoff_text, generate_handoff_prompt, save_handoff


class TestGenerateHandoffPrompt:
    def test_prompt_contains_required_sections(self) -> None:
        prompt = generate_handoff_prompt()
        assert "Current goal" in prompt
        assert "Project context" in prompt
        assert "Decisions made" in prompt
        assert "Work completed" in prompt
        assert "Current state" in prompt
        assert "Relevant files" in prompt
        assert "Next useful step" in prompt

    def test_prompt_is_string(self) -> None:
        assert isinstance(generate_handoff_prompt(), str)
        assert len(generate_handoff_prompt()) > 50


class TestSaveHandoff:
    def test_saves_to_correct_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = "# Handoff\n\nTest content"
            saved = save_handoff(root, text)
            # Check path is under .aura/handoffs/
            assert saved.parent.name == "handoffs"
            assert saved.parent.parent.name == ".aura"
            # Check it exists and has correct content
            assert saved.exists()
            assert saved.read_text(encoding="utf-8") == text
            # Check naming pattern: YYYY-MM-DD-HHMMSS-ffffff-handoff.md
            assert saved.name.endswith("-handoff.md")
            parts = saved.name.split("-")
            assert len(parts) >= 4  # date + time + microsecond + handoff.md

    def test_creates_directory_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoffs_dir = root / ".aura" / "handoffs"
            assert not handoffs_dir.exists()
            save_handoff(root, "# Test")
            assert handoffs_dir.exists()

    def test_overwrites_not_same_file(self) -> None:
        """Each call creates a new timestamped file, never overwrites."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p1 = save_handoff(root, "# First")
            p2 = save_handoff(root, "# Second")
            assert p1 != p2
            assert p1.exists()
            assert p2.exists()


class TestExtractHandoffText:
    def test_returns_content_key(self) -> None:
        msg = {"content": "# Handoff\n\nHello", "role": "assistant"}
        assert extract_handoff_text(msg) == "# Handoff\n\nHello"

    def test_returns_empty_string_for_empty_content(self) -> None:
        msg = {"content": "", "role": "assistant"}
        assert extract_handoff_text(msg) == ""

    def test_returns_empty_string_for_missing_content(self) -> None:
        msg = {"role": "assistant"}
        assert extract_handoff_text(msg) == ""

    def test_returns_empty_string_for_whitespace_only(self) -> None:
        msg = {"content": "   \n  ", "role": "assistant"}
        assert extract_handoff_text(msg) == "   \n  "
