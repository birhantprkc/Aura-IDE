"""Artifact and receipt builders for browse drone."""

from __future__ import annotations

import datetime as dt
from typing import Any

from aura.drones.browse.models import BrowseCandidate, BrowseSnapshot
from aura.drones.browse.policy import PolicyResult
from aura.drones.definition import DroneDefinition
from aura.drones.receipt import DroneReceipt
from aura.drones.run import DroneRun


def build_boundary_artifact(
    *,
    start_url: str,
    final_url: str,
    page_title: str,
    before_snapshot: BrowseSnapshot,
    action_trace: list[dict[str, Any]],
    policy_result: PolicyResult,
    candidate: BrowseCandidate,
    action_type: str,
    skipped_reason: str,
) -> dict[str, Any]:
    """Build a produced_artifact dict for a boundary (policy-blocked) action.

    The artifact status is ``needs_planner_decision`` when the policy verdict
    is ``needs_planner_decision``, otherwise ``blocked_manual``.
    """
    proposed_action = {
        "action_type": action_type,
        "target_id": candidate.id,
        "target_label": candidate.label,
        "target_role": candidate.role,
        "target_tag": candidate.tag,
        "target_href": candidate.href,
        "current_url": final_url,
        "page_title": page_title,
        "reason": policy_result.reason,
        "matched_text": policy_result.matched_text,
    }
    artifact_status = (
        "needs_planner_decision"
        if policy_result.verdict == "needs_planner_decision"
        else "blocked_manual"
    )
    return {
        "kind": "browse",
        "status": artifact_status,
        "start_url": start_url,
        "final_url": final_url,
        "title": page_title,
        "action_trace": action_trace,
        "before_snapshot": before_snapshot.to_dict(),
        "after_snapshot": None,
        "candidate_count": before_snapshot.candidate_count,
        "skipped_reason": skipped_reason,
        "errors": [],
        "proposed_action": proposed_action,
    }


def build_completed_artifact(
    *,
    start_url: str,
    final_url: str,
    page_title: str,
    before_snapshot: BrowseSnapshot,
    after_snapshot: BrowseSnapshot | None,
    action_trace: list[dict[str, Any]],
    skipped_reason: str | None,
) -> dict[str, Any]:
    """Build a produced_artifact dict for a successfully completed browse run."""
    return {
        "kind": "browse",
        "status": "completed",
        "start_url": start_url,
        "final_url": final_url,
        "title": page_title,
        "action_trace": action_trace,
        "before_snapshot": before_snapshot.to_dict(),
        "after_snapshot": after_snapshot.to_dict() if after_snapshot else None,
        "candidate_count": before_snapshot.candidate_count,
        "skipped_reason": skipped_reason,
        "errors": [],
    }


def build_failed_receipt(
    *,
    run: DroneRun,
    drone: DroneDefinition,
    start_url: str,
    summary: str,
    errors: list[str],
    action_trace: list[dict] | None = None,
) -> DroneReceipt:
    """Build a failed DroneReceipt without emitting signals or saving.

    The caller is responsible for calling ``on_receipt``, ``RunHistoryStore.save_run``,
    ``run.mark("failed")``, and ``on_status("failed")``.
    """
    ended = dt.datetime.now(dt.timezone.utc).isoformat()
    receipt = DroneReceipt(
        run_id=run.run_id,
        drone_id=drone.id,
        drone_name=drone.name,
        status="failed",
        started_at=dt.datetime.fromtimestamp(
            run.started_at, tz=dt.timezone.utc
        ).isoformat(),
        ended_at=ended,
        summary=summary,
        produced_artifact={
            "kind": "browse",
            "status": "failed",
            "start_url": start_url,
            "final_url": "",
            "title": "",
            "action_trace": action_trace or [],
            "before_snapshot": None,
            "after_snapshot": None,
            "candidate_count": 0,
            "skipped_reason": None,
            "errors": errors,
        },
        errors=errors,
        elapsed_seconds=run.elapsed_seconds,
    )
    return receipt
