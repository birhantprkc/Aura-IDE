"""Small prompt composer for Aura role prompts and conservative context."""
from __future__ import annotations

import logging
from pathlib import Path

from aura.repo_map import generate_repo_map

logger = logging.getLogger(__name__)

TIER1_CONTEXT_PLACEHOLDER = "{TIER1_CONTEXT}"

_GEARBOX_REBUILD_TODO = (
    "prompt source registry",
    "scoped context sources",
    "prompt source ledger",
    "deterministic current-info source gate",
    "Worker run ledger / acceptance proof ledger",
)

_SHARED_POSTURE = """Common posture:
- Work inside the selected workspace.
- Read files before making claims about repository contents.
- Keep the response and any changes scoped to the user's request."""

_PLANNER_ROLE = """Planner role:
- Identify the user's intent and the likely task lane.
- Inspect minimal repository context when needed.
- Dispatch implementation work instead of coding directly.
- Rely on deterministic router output and tool results when available."""

_WORKER_ROLE = """Worker role:
- Execute only the requested change.
- Use tools for repository reads and writes.
- Validate focused behavior when practical.
- Return a compact final result."""

_SINGLE_ROLE = """Single-agent role:
- Answer or edit within the workspace.
- Read files before claiming repository facts.
- Keep scope tight."""


PLANNER_SYSTEM_PROMPT = "\n\n".join(
    [TIER1_CONTEXT_PLACEHOLDER, _SHARED_POSTURE, _PLANNER_ROLE]
)

WORKER_SYSTEM_PROMPT = "\n\n".join(
    [TIER1_CONTEXT_PLACEHOLDER, _SHARED_POSTURE, _WORKER_ROLE]
)

SINGLE_SYSTEM_PROMPT = "\n\n".join(
    [TIER1_CONTEXT_PLACEHOLDER, _SHARED_POSTURE, _SINGLE_ROLE]
)


def inject_tier1_context(prompt: str, tier1_context: str) -> str:
    """Replace the Tier 1 placeholder in *prompt* with composed context."""
    return prompt.replace(TIER1_CONTEXT_PLACEHOLDER, tier1_context or "", 1)


def build_tier1_context(
    workspace_root: Path,
    force: bool = False,
    mode: str = "all",
    model: str | None = None,
    task_kind: str | None = None,
    target_files: tuple[str, ...] = (),
) -> str:
    """Compose minimal context for role prompts.

    Compatibility parameters are accepted for existing callers. This composer
    intentionally includes only explicit project rules and the existing repo map.
    Future gearbox work should replace this with the TODO sources listed above.
    """
    _ = (mode, model, task_kind, target_files)
    parts: list[str] = []

    rules_path = workspace_root / "project_rules.md"
    if rules_path.is_file():
        try:
            rules_content = rules_path.read_text(encoding="utf-8").strip()
            if rules_content:
                parts.append("### Project Rules\n" + rules_content)
        except (OSError, PermissionError):
            logger.debug("Project rules unavailable", exc_info=True)

    try:
        repo_map = generate_repo_map(workspace_root, force=force)
        if repo_map and "No Python/TypeScript files found." not in repo_map:
            parts.append(repo_map)
    except Exception:
        logger.debug("Repo map unavailable", exc_info=True)

    return "\n\n".join(parts)
