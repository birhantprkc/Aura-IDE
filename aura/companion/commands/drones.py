"""Companion command handlers: drone.list_recent, drone.status."""
from __future__ import annotations

import logging
from pathlib import Path

from aura.companion.commands import CommandContext
from aura.companion.protocol import ActiveRunSummary
from aura.companion.replies import build_reply_envelope
from aura.drones.store import RunHistoryStore

logger = logging.getLogger(__name__)


def handle_drone_list_recent(msg: dict, ctx: CommandContext) -> None:
    """List recent drone runs in response to a mobile request."""
    workspace_root = ctx.state.workspace_root
    if not workspace_root:
        env = build_reply_envelope(msg, "drone.list_result", {"runs": []})
        if env:
            ctx.send_fn(env)
        return
    try:
        root = Path(workspace_root)
        runs = RunHistoryStore.list_runs(root, limit=20)
        summaries = []
        for r in runs:
            summaries.append(ActiveRunSummary(
                run_id=r.get("run_id", ""),
                kind="drone",
                label=r.get("drone_name", r.get("drone_id", "Drone")),
                status=r.get("status", "unknown"),
                started_at=r.get("started_at"),
            ).to_dict())
        env = build_reply_envelope(msg, "drone.list_result", {"runs": summaries})
        if env:
            ctx.send_fn(env)
    except Exception as exc:
        logger.error("[Companion] drone.list_recent error: %s", exc)
        env = build_reply_envelope(msg, "drone.list_result", {"runs": [], "error": str(exc)})
        if env:
            ctx.send_fn(env)


def handle_drone_status(msg: dict, ctx: CommandContext) -> None:
    """Report current drone runner status."""
    if ctx.drone_runner is not None:
        try:
            state = ctx.drone_runner.run_state()
            from datetime import datetime
            started_at_str = (
                datetime.fromtimestamp(state.started_at).isoformat()
                if state.started_at
                else None
            )
            summary = ActiveRunSummary(
                run_id=state.run_id,
                kind="drone",
                label=(
                    state.drone.name
                    if hasattr(state, "drone") and state.drone
                    else "Drone"
                ),
                status=state.status,
                started_at=started_at_str,
            ).to_dict()
            env = build_reply_envelope(msg, "drone.status_result", {"running": True, "run": summary})
            if env:
                ctx.send_fn(env)
            return
        except Exception as exc:
            logger.error("[Companion] drone.status error: %s", exc)
    env = build_reply_envelope(msg, "drone.status_result", {"running": False, "run": None})
    if env:
        ctx.send_fn(env)
