"""Initial scoped context source registry."""
from __future__ import annotations

from pathlib import Path

from aura.context_gearbox.models import ContextLedgerEntry, ContextSource, RuntimeRole
from aura.repo_map import generate_repo_map

CORE_KERNEL_TEXT = """Core kernel:
- Work inside the selected workspace.
- Read files before making claims about repository contents.
- Keep the response and any changes scoped to the user's request."""

GEARBOX_REBUILD_TODO = (
    "prompt source registry",
    "scoped context sources",
    "prompt source ledger",
    "deterministic current-info source gate",
    "Worker run ledger / acceptance proof ledger",
)

CONTEXT_SOURCES: tuple[ContextSource, ...] = (
    ContextSource(
        source_id="core_kernel",
        kind="kernel",
        roles=(RuntimeRole.PLANNER, RuntimeRole.WORKER, RuntimeRole.SINGLE),
        reason="baseline runtime posture",
    ),
    ContextSource(
        source_id="project_rules",
        kind="workspace_file",
        roles=(RuntimeRole.PLANNER, RuntimeRole.WORKER, RuntimeRole.SINGLE),
        reason="explicit project rules file",
    ),
    ContextSource(
        source_id="repo_map",
        kind="workspace_structure",
        roles=(RuntimeRole.PLANNER, RuntimeRole.WORKER, RuntimeRole.SINGLE),
        reason="repository structure overview",
    ),
)


def iter_context_sources(role: RuntimeRole) -> tuple[ContextSource, ...]:
    return tuple(source for source in CONTEXT_SOURCES if role in source.roles)


def collect_source_text(
    source: ContextSource,
    role: RuntimeRole,
    workspace_root: Path | None,
    *,
    force: bool = False,
) -> tuple[str, ContextLedgerEntry]:
    try:
        text, reason = _load_source_text(source, workspace_root, force=force)
        included = bool(text)
        return text, ContextLedgerEntry(
            source_id=source.source_id,
            kind=source.kind,
            role=role,
            reason=reason or source.reason,
            included=included,
            char_count=len(text),
        )
    except Exception as exc:
        return "", ContextLedgerEntry(
            source_id=source.source_id,
            kind=source.kind,
            role=role,
            reason=source.reason,
            included=False,
            char_count=0,
            error=f"{type(exc).__name__}: {exc}",
        )


def _load_source_text(
    source: ContextSource,
    workspace_root: Path | None,
    *,
    force: bool,
) -> tuple[str, str]:
    if source.source_id == "core_kernel":
        return CORE_KERNEL_TEXT, source.reason
    if workspace_root is None:
        return "", "no workspace root"
    if source.source_id == "project_rules":
        rules_path = workspace_root / "project_rules.md"
        if not rules_path.is_file():
            return "", "project_rules.md not found"
        try:
            rules = rules_path.read_text(encoding="utf-8").strip()
        except (OSError, PermissionError) as exc:
            raise RuntimeError(f"project_rules.md unavailable: {exc}") from exc
        if not rules:
            return "", "project_rules.md is empty"
        return "### Project Rules\n" + rules, source.reason
    if source.source_id == "repo_map":
        repo_map = generate_repo_map(workspace_root, force=force)
        if not repo_map:
            return "", "repo map unavailable"
        if "No Python/TypeScript files found." in repo_map:
            return "", "no Python/TypeScript files found"
        return repo_map, source.reason
    return "", "unknown context source"
