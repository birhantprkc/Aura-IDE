"""Pure worker final-report message construction helpers."""
from __future__ import annotations

import json
from typing import Any


def build_worker_unrecoverable_message(
    *,
    failure_class: str,
    error: str,
    details: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build (content_json, full_message) for an unrecoverable worker failure."""
    payload: dict[str, Any] = {
        "ok": False,
        "failure_class": failure_class,
        "error": error,
    }
    if details:
        payload["details"] = details
    content = json.dumps(payload, ensure_ascii=False)
    full_message: dict[str, Any] = {
        "role": "assistant",
        "content": content,
        "reasoning_content": None,
    }
    return content, full_message


def build_worker_recoverable_followup_message(
    *,
    failure_class: str,
    error: str,
    details: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build (content_json, full_message) for a recoverable worker followup."""
    payload: dict[str, Any] = {
        "ok": False,
        "recoverable": True,
        "needs_follow_up": True,
        "failure_class": failure_class,
        "error": error,
    }
    if details:
        payload["details"] = details
    content = json.dumps(payload, ensure_ascii=False)
    full_message: dict[str, Any] = {
        "role": "assistant",
        "content": content,
        "reasoning_content": None,
    }
    return content, full_message
