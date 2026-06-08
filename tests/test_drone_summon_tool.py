from __future__ import annotations

from aura.conversation.tools._types import ApprovalDecision
from aura.conversation.tools.registry import ToolRegistry
from aura.drones.definition import DroneBudget, DroneDefinition, default_tools_for_policy
from aura.drones.store import DroneStore


def _save_drone(tmp_path) -> None:
    DroneStore.save_drone(
        tmp_path,
        DroneDefinition(
            id="test-scout",
            name="Test Scout",
            description="Find tests.",
            instructions="Find relevant tests for the current change.",
            write_policy="read_only",
            allowed_tools=default_tools_for_policy("read_only"),
            output_contract="Test list and rationale.",
            budget=DroneBudget(max_tool_rounds=5, timeout_seconds=180),
        ),
    )


def test_summon_drone_returns_confirmation_metadata(tmp_path) -> None:
    _save_drone(tmp_path)
    registry = ToolRegistry(tmp_path, mode="planner")

    result = registry.execute(
        "summon_drone",
        {"drone_id": "test-scout", "goal": "Find the right tests"},
        lambda request: ApprovalDecision("approve"),
    )

    assert result.ok is True
    assert result.payload["status"] == "pending_user_confirmation"
    assert result.payload["drone_name"] == "Test Scout"
    assert result.extras["summon_drone"] is True


def test_summon_drone_rejects_unknown_drone(tmp_path) -> None:
    registry = ToolRegistry(tmp_path, mode="planner")

    result = registry.execute(
        "summon_drone",
        {"drone_id": "missing", "goal": "Find tests"},
        lambda request: ApprovalDecision("approve"),
    )

    assert result.ok is False
    assert "unknown drone" in result.payload["error"]
