"""Detect model-emitted fake tool-call markup in assistant content."""
from __future__ import annotations

from typing import Any


RAW_TOOL_MARKUP_RETRY_INSTRUCTION = (
    "You emitted tool-call markup as text. Do not write tool markup manually. "
    "Use the provided tool interface. Now perform the next required action "
    "with an actual tool call."
)

RAW_TOOL_MARKUP_FAILURE_CLASS = "raw_tool_markup_emitted"
RAW_TOOL_MARKUP_SUMMARY = (
    "Worker attempted to simulate a tool call instead of calling the tool interface."
)

_RAW_TOOL_MARKUP_MARKERS = (
    "<｜｜dsml｜｜tool_calls",
    "<｜｜dsml｜｜invoke",
    "<| dsml | tool_calls",
    "<| dsml | invoke",
    "<|dsml|tool_calls",
    "<|dsml|invoke",
    "<tool_calls",
    "<invoke name=",
    "</｜｜dsml｜｜tool_calls>",
    "</| dsml | tool_calls>",
    "</|dsml|tool_calls>",
)


def contains_raw_tool_markup(text: Any) -> bool:
    """Return True when assistant text contains fake tool-call markup."""
    if not isinstance(text, str) or not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _RAW_TOOL_MARKUP_MARKERS)


def message_contains_raw_tool_markup(message: dict[str, Any]) -> bool:
    """Check all visible assistant content shapes for leaked tool-call markup."""
    content = message.get("content")
    if contains_raw_tool_markup(content):
        return True
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and contains_raw_tool_markup(item.get("text")):
                return True
            if contains_raw_tool_markup(item):
                return True
    return contains_raw_tool_markup(message.get("reasoning_content"))


__all__ = [
    "RAW_TOOL_MARKUP_FAILURE_CLASS",
    "RAW_TOOL_MARKUP_RETRY_INSTRUCTION",
    "RAW_TOOL_MARKUP_SUMMARY",
    "contains_raw_tool_markup",
    "message_contains_raw_tool_markup",
]
