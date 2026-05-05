"""Conversation persistence — JSON files in `<workspace>/.aura/conversations/`.

Each file stores the full History (messages including reasoning_content), plus
the model and thinking state that were active when the conversation was last
extended. This is enough to round-trip a chat into the GUI on next launch.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aura.config import DEFAULT_MODEL, DEFAULT_THINKING, ModelId, ThinkingMode
from aura.conversation.history import History

SCHEMA_VERSION = 1
CONVERSATIONS_SUBDIR = ".aura/conversations"


@dataclass
class ConversationMeta:
    path: Path
    created_at: str
    title: str
    model: ModelId
    thinking: ThinkingMode


def conversations_dir(workspace_root: Path) -> Path:
    return workspace_root / CONVERSATIONS_SUBDIR


def _slugify(text: str, max_len: int = 40) -> str:
    if not text:
        return "untitled"
    words = text.strip().split()[:6]
    s = "-".join(words).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    if not s:
        return "untitled"
    return s[:max_len].rstrip("-") or "untitled"


def _first_user_text(history: History) -> str:
    for msg in history.messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    return str(part.get("text", ""))
    return ""


def save_conversation(
    history: History,
    workspace_root: Path,
    model: ModelId,
    thinking: ThinkingMode,
    *,
    title: str | None = None,
    existing_path: Path | None = None,
) -> Path:
    """Write the conversation to disk and return the file path.

    If `existing_path` is supplied and lives under `<workspace>/.aura/conversations/`,
    we overwrite it in place — that's how auto-save updates a single file across
    rounds within one chat.
    """
    target_dir = conversations_dir(workspace_root)
    target_dir.mkdir(parents=True, exist_ok=True)

    if existing_path is not None:
        try:
            existing_path.resolve().relative_to(target_dir.resolve())
            path = existing_path
        except ValueError:
            path = _new_path(target_dir, history, title)
    else:
        path = _new_path(target_dir, history, title)

    payload: dict[str, Any] = {
        "version": SCHEMA_VERSION,
        "created_at": _read_created_at(path) or _utc_iso(),
        "model": model,
        "thinking": thinking,
        "system_prompt": history.system_prompt,
        "messages": copy.deepcopy(history.messages),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _new_path(target_dir: Path, history: History, title: str | None) -> Path:
    ts = _file_timestamp()
    slug = _slugify(title if title is not None else _first_user_text(history))
    return target_dir / f"{ts}-{slug}.json"


def _read_created_at(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    val = data.get("created_at") if isinstance(data, dict) else None
    return val if isinstance(val, str) else None


@dataclass
class LoadedConversation:
    history: History
    model: ModelId
    thinking: ThinkingMode
    path: Path


def load_conversation(path: Path) -> LoadedConversation:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Conversation file is not a JSON object: {path}")
    if data.get("version") != SCHEMA_VERSION:
        # Forward-compatible: keep loading, just don't trust unknown fields.
        pass

    history = History()
    sp = data.get("system_prompt")
    if isinstance(sp, str):
        history.set_system(sp)
    msgs = data.get("messages")
    if isinstance(msgs, list):
        history.messages = [m for m in msgs if isinstance(m, dict)]

    model = data.get("model") if data.get("model") in ("deepseek-v4-flash", "deepseek-v4-pro") else DEFAULT_MODEL
    thinking = data.get("thinking") if data.get("thinking") in ("off", "high", "max") else DEFAULT_THINKING

    return LoadedConversation(history=history, model=model, thinking=thinking, path=path)


def list_conversations(workspace_root: Path) -> list[Path]:
    target_dir = conversations_dir(workspace_root)
    if not target_dir.is_dir():
        return []
    return sorted(target_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def most_recent_conversation(workspace_root: Path) -> Path | None:
    files = list_conversations(workspace_root)
    return files[0] if files else None


# ---- helpers --------------------------------------------------------------


def _utc_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _file_timestamp() -> str:
    # Filename-safe ISO timestamp, e.g. 2026-05-05T13-42-17Z.
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
