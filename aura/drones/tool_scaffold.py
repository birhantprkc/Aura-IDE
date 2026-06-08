"""Helpers for turning a Drone into a dynamic-tool starter."""
from __future__ import annotations

from pathlib import Path

from aura.drones.definition import DroneDefinition, slugify


def dynamic_tool_name_for_drone(drone: DroneDefinition) -> str:
    """Return a Python-safe dynamic tool function name for a Drone."""
    base = slugify(drone.id or drone.name).replace("-", "_").strip("_")
    if not base:
        base = "drone_tool"
    if base[0].isdigit():
        base = f"drone_{base}"
    return base


def scaffold_dynamic_tool(workspace_root: Path, drone: DroneDefinition) -> Path:
    """Create a valid dynamic-tool scaffold for a Drone and return its path.

    Existing tool files are left untouched. The generated function is a safe
    starter that can be refined later by the user or Aura.
    """
    tools_dir = workspace_root / ".aura" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    tool_name = dynamic_tool_name_for_drone(drone)
    path = tools_dir / f"{tool_name}.py"
    if path.exists():
        return path

    content = _scaffold_source(tool_name, drone)
    path.write_text(content, encoding="utf-8")
    return path


def _scaffold_source(tool_name: str, drone: DroneDefinition) -> str:
    description = (drone.description or drone.instructions or drone.name).strip()
    instructions = drone.instructions.strip()
    output_contract = drone.output_contract.strip()
    return f'''"""Dynamic tool scaffold generated from the "{drone.name}" Drone."""
from __future__ import annotations


def {tool_name}(note: str = "") -> dict:
    """Run the tool-backed starter for the {drone.name} Drone.

    This is a scaffold. Replace the placeholder body with deterministic Python
    that performs the repeatable part of this Drone's workflow.

    Args:
        note: Optional caller note or run-specific context.

    Returns:
        JSON-serializable result data for Aura.
    """
    return {{
        "ok": True,
        "drone": {drone.name!r},
        "note": note,
        "description": {description!r},
        "instructions": {instructions!r},
        "output_contract": {output_contract!r},
        "next_step": "Replace this scaffold with deterministic local tool logic.",
    }}
'''
