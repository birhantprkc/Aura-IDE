import json

from aura.conversation.dispatch_failure import classify_failed_worker_dispatch
from aura.conversation.history import History
from aura.conversation.loop_detection import LoopDetector
from aura.conversation.tool_runner import ToolRunner
from aura.conversation.tools.registry import ToolRegistry
from aura.conversation.verification_progress import VerificationProgressTracker
from aura.conversation.workflow_state import WorkflowStatus


def _flat_steps_required_dispatch() -> dict:
    return {
        "goal": "Fix the live Worker Log regression during canonical dispatch.",
        "files": ["aura/gui/worker_handler.py"],
        "spec": (
            "Remove the canonical-dispatch early return guards from "
            "_on_worker_reasoning and _on_worker_content. Delete the guards "
            "only; do not change playground.py."
        ),
        "acceptance": (
            "- _on_worker_reasoning no longer returns early during canonical dispatch\n"
            "- _on_worker_content no longer returns early during canonical dispatch\n"
            "- python -m compileall aura/gui/worker_handler.py passes\n"
            "- python -m aura --selfcheck passes"
        ),
        "summary": "Allow Worker text through during canonical dispatch.",
        "validation_commands": [
            "python -m compileall aura/gui/worker_handler.py",
            "python -m aura --selfcheck",
        ],
    }


def test_flat_dispatch_rejection_has_visible_retry_constraint(tmp_path):
    runner = ToolRunner(
        History(),
        tmp_path,
        LoopDetector(),
        VerificationProgressTracker(),
    )
    states = []

    result = runner.handle_dispatch(
        "call_dispatch",
        _flat_steps_required_dispatch(),
        on_event=lambda event: None,
        dispatch_cb=lambda _tool_id, _req: None,
        workflow_state_cb=lambda *items: states.append(items),
    )

    assert result is not None
    assert result.ok is False
    assert result.recoverable is True
    assert result.extras["dispatch_spec_rejected"] is True
    assert result.extras["planner_resolution_needed"] is True
    assert result.extras["internal_planner_handoff"] is True
    assert result.extras["campaign_errors"] == [
        "Broad implementation dispatches must include a decomposed steps campaign."
    ]

    constraint = result.extras["failure_constraint"]
    assert constraint.startswith("CONSTRAINT FOR NEXT DISPATCH ATTEMPT:")
    assert "rejected before Worker start" in constraint
    assert "steps array" in constraint
    assert "id, title, goal, spec, files, and acceptance" in constraint
    assert "Do not call edit/write tools." in constraint
    assert "The Worker was not started" in result.summary
    assert "Planner must retry dispatch_to_worker" in result.summary
    assert states and states[-1][3] == WorkflowStatus.planner_resolving


def test_failed_dispatch_classification_preserves_campaign_constraint(tmp_path):
    runner = ToolRunner(
        History(),
        tmp_path,
        LoopDetector(),
        VerificationProgressTracker(),
    )
    result = runner.handle_dispatch(
        "call_dispatch",
        _flat_steps_required_dispatch(),
        on_event=lambda event: None,
        dispatch_cb=lambda _tool_id, _req: None,
    )
    assert result is not None

    action = classify_failed_worker_dispatch(
        args=_flat_steps_required_dispatch(),
        result=result,
        failures={},
        failed_attempts=0,
    )

    assert action["blocker_reason"] == ""
    assert action["failure_constraint"] == result.extras["failure_constraint"]


def test_planner_edit_tool_misuse_gets_dispatch_correction(tmp_path):
    registry = ToolRegistry(tmp_path, mode="planner")

    result = registry.execute("edit_file", {}, approval_cb=lambda request: None)

    assert result.ok is False
    assert result.payload["planner_tool_unavailable"] is True
    assert result.payload["suggested_next_tool"] == "dispatch_to_worker"
    assert result.extras["internal_planner_handoff"] is True
    assert "Planner never edits files directly" in result.payload["error"]
    assert "Do not call edit/write tools" in result.extras["failure_constraint"]
    assert "dispatch_to_worker" in result.extras["failure_constraint"]


def test_planner_registered_write_tool_is_also_blocked_with_correction(tmp_path):
    registry = ToolRegistry(tmp_path, mode="planner")

    result = registry.execute(
        "write_file",
        {"path": "example.py", "content": "print('nope')\n"},
        approval_cb=lambda request: None,
    )

    assert result.ok is False
    payload = json.loads(result.to_tool_message_content())
    assert payload["planner_tool_unavailable"] is True
    assert payload["suggested_next_tool"] == "dispatch_to_worker"
    assert "write_file is not available in Planner mode" in payload["error"]
