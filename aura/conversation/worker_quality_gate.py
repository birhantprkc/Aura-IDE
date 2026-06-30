from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from aura.client import ContentDelta, Done, Event
from aura.conversation.history import History
from aura.conversation.manager_send_state import _SendState
from aura.conversation.worker_fingerprints import fingerprint_paths
from aura.conversation.worker_finish import build_worker_recoverable_followup_message
from aura.conversation.worker_quality import (
    evaluate_worker_quality,
    findings_to_receipt,
)

EventCallback = Callable[[Event], None]


def handle_worker_quality_gate(
    *,
    state: _SendState,
    workspace_root,
    history: History,
    on_event: EventCallback,
) -> str:
    if not state.worker_quality_enabled:
        return "none"
    changed_files = sorted(state.worker_app_writes)
    if not changed_files:
        return "none"
    root = Path(workspace_root)
    if not (root / ".git").exists():
        return "none"

    fingerprint = fingerprint_paths(set(changed_files), root)
    if fingerprint and fingerprint == state.last_quality_ok_fingerprint:
        return "none"

    diff_text = _diff_changed_files(root, changed_files)
    decision = evaluate_worker_quality(
        root,
        changed_files,
        diff_text,
        validation_passed=True,
    )
    state.last_quality_findings = findings_to_receipt(decision.findings)

    if decision.hard_block:
        _finish_worker_quality_hard_block(
            history=history,
            on_event=on_event,
            changed_files=changed_files,
            findings=state.last_quality_findings,
        )
        return "finished"

    if decision.needs_cleanup:
        if not state.worker_quality_nudge_sent:
            history.append_user_text(decision.instruction)
            state.worker_quality_nudge_sent = True
            state.worker_quality_cleanup_attempted = True
            return "cleanup"
        if fingerprint:
            state.last_quality_ok_fingerprint = fingerprint
        return "none"

    if fingerprint:
        state.last_quality_ok_fingerprint = fingerprint
    state.last_quality_findings = []
    return "none"


def _diff_changed_files(workspace_root: Path, changed_files: list[str]) -> str:
    if not changed_files:
        return ""
    result = subprocess.run(
        ["git", "-C", str(workspace_root), "diff", "--", *sorted(changed_files)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def _finish_worker_quality_hard_block(
    *,
    history: History,
    on_event: EventCallback,
    changed_files: list[str],
    findings: list[dict],
) -> None:
    content, full_message = build_worker_recoverable_followup_message(
        failure_class="worker_quality_hard_block",
        error=(
            "Worker final candidate failed deterministic structural review "
            "after validation."
        ),
        details={
            "recoverable": True,
            "phase_boundary": True,
            "changed_files": changed_files,
            "findings": findings,
            "suggested_next_tool": "dispatch_to_worker",
            "suggested_next_action": (
                "Redispatch a focused repair for the listed hard-block findings."
            ),
        },
    )
    payload = json.loads(content)
    payload["phase_boundary"] = True
    content = json.dumps(payload, ensure_ascii=False)
    full_message["content"] = content
    history.append_assistant(full_message)
    on_event(ContentDelta(text=content))
    on_event(Done(finish_reason="stop", full_message=full_message))
