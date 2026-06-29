"""Companion command handler: project.list_recent."""
from __future__ import annotations

import logging

from aura.companion.commands import CommandContext
from aura.companion.protocol import CompanionProject
from aura.companion.replies import build_reply_envelope
from aura.projects.store import ProjectStore

logger = logging.getLogger(__name__)


def handle_project_list_recent(msg: dict, ctx: CommandContext) -> None:
    """List recent projects in response to a mobile request."""
    workspace_root = ctx.state.workspace_root
    if not workspace_root:
        env = build_reply_envelope(msg, "project.list_result", {"projects": []})
        if env:
            ctx.send_fn(env)
        return
    try:
        store = ProjectStore()
        projects = store.list_projects()
        projects.sort(key=lambda p: p.updated_at, reverse=True)
        dtos = []
        for p in projects[:20]:
            thread_count = 0
            try:
                threads = store.list_threads(p)
                thread_count = len(threads)
            except Exception as exc:
                logger.debug("[Companion] thread count for %s: %s", p.id, exc)
            dtos.append(CompanionProject(
                id=p.id,
                name=p.name,
                updated_at=p.updated_at,
                thread_count=thread_count,
            ).to_dict())
        env = build_reply_envelope(msg, "project.list_result", {"projects": dtos})
        if env:
            ctx.send_fn(env)
    except Exception as exc:
        logger.error("[Companion] project.list_recent error: %s", exc)
        env = build_reply_envelope(msg, "project.list_result", {"projects": [], "error": str(exc)})
        if env:
            ctx.send_fn(env)
