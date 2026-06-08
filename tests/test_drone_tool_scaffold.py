from __future__ import annotations

from aura.conversation.tools.dynamic import parse_tool_schema
from aura.drones.definition import DroneBudget, DroneDefinition, default_tools_for_policy
from aura.drones.tool_scaffold import dynamic_tool_name_for_drone, scaffold_dynamic_tool


def _drone() -> DroneDefinition:
    return DroneDefinition(
        id="release-check",
        name="Release Check",
        description="Check release readiness.",
        instructions="Inspect git state and identify validation commands.",
        write_policy="read_only",
        allowed_tools=default_tools_for_policy("read_only"),
        output_contract="Summary and validation notes.",
        budget=DroneBudget(max_tool_rounds=5, timeout_seconds=180),
    )


def test_dynamic_tool_name_for_drone() -> None:
    assert dynamic_tool_name_for_drone(_drone()) == "release_check"


def test_scaffold_dynamic_tool_creates_valid_schema(tmp_path) -> None:
    path = scaffold_dynamic_tool(tmp_path, _drone())

    assert path == tmp_path / ".aura" / "tools" / "release_check.py"
    assert path.exists()
    schema = parse_tool_schema(path)
    assert schema["function"]["name"] == "release_check"
    assert schema["function"]["parameters"]["properties"]["note"]["type"] == "string"


def test_scaffold_dynamic_tool_does_not_overwrite_existing_file(tmp_path) -> None:
    path = scaffold_dynamic_tool(tmp_path, _drone())
    path.write_text("sentinel = True\n", encoding="utf-8")

    assert scaffold_dynamic_tool(tmp_path, _drone()) == path
    assert path.read_text(encoding="utf-8") == "sentinel = True\n"
