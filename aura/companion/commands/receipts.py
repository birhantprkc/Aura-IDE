"""Companion command handler: receipt.list_recent."""
from __future__ import annotations

import logging
from pathlib import Path

from aura.companion.commands import CommandContext
from aura.companion.protocol import ReceiptSummary
from aura.companion.replies import build_reply_envelope
from aura.drones.store import RunHistoryStore

logger = logging.getLogger(__name__)


def handle_receipt_list_recent(msg: dict, ctx: CommandContext) -> None:
    """List recent receipts in response to a mobile request."""
    workspace_root = ctx.state.workspace_root
    if not workspace_root:
        env = build_reply_envelope(msg, "receipt.list_result", {"receipts": []})
        if env:
            ctx.send_fn(env)
        return
    try:
        root = Path(workspace_root)
        runs = RunHistoryStore.list_runs(root, limit=20)
        receipts = []
        for r in runs:
            receipts.append(ReceiptSummary(
                run_id=r.get("run_id", ""),
                kind="drone",
                label=r.get("drone_name", r.get("drone_id", "Drone")),
                status=r.get("status", "unknown"),
                completed_at=r.get("ended_at", r.get("started_at", "")),
                summary=r.get("summary", ""),
            ).to_dict())
        env = build_reply_envelope(msg, "receipt.list_result", {"receipts": receipts})
        if env:
            ctx.send_fn(env)
    except Exception as exc:
        logger.error("[Companion] receipt.list_recent error: %s", exc)
        env = build_reply_envelope(msg, "receipt.list_result", {"receipts": [], "error": str(exc)})
        if env:
            ctx.send_fn(env)
