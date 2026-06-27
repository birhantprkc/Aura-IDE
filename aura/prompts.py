"""Compatibility exports for Aura runtime prompt composition."""
from __future__ import annotations

from pathlib import Path

from aura.context_gearbox.models import RuntimeRole
from aura.context_gearbox.runtime import (
    CONTEXT_PLACEHOLDER,
    PLANNER_SYSTEM_PROMPT,
    SINGLE_SYSTEM_PROMPT,
    WORKER_SYSTEM_PROMPT,
    build_context_text,
)

TIER1_CONTEXT_PLACEHOLDER = CONTEXT_PLACEHOLDER

__all__ = [
    "TIER1_CONTEXT_PLACEHOLDER",
    "PLANNER_SYSTEM_PROMPT",
    "WORKER_SYSTEM_PROMPT",
    "SINGLE_SYSTEM_PROMPT",
    "inject_tier1_context",
    "build_tier1_context",
]


def inject_tier1_context(prompt: str, tier1_context: str) -> str:
    """Compatibility wrapper for old callers that already built context text."""
    return prompt.replace(TIER1_CONTEXT_PLACEHOLDER, tier1_context or "", 1)


def build_tier1_context(
    workspace_root: Path,
    force: bool = False,
    mode: str = "all",
    model: str | None = None,
    task_kind: str | None = None,
    target_files: tuple[str, ...] = (),
) -> str:
    """Compatibility wrapper returning only composed context text."""
    role = _role_from_mode(mode)
    return build_context_text(
        role,
        workspace_root,
        force=force,
        model=model,
        task_kind=task_kind,
        target_files=target_files,
    ).context_text


def _role_from_mode(mode: str) -> RuntimeRole:
    if mode == "worker":
        return RuntimeRole.WORKER
    if mode == "single":
        return RuntimeRole.SINGLE
    return RuntimeRole.PLANNER
