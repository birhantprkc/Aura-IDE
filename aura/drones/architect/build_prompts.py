from __future__ import annotations

from pathlib import Path

from aura.drones.build_spec import DroneBuildBrief
from aura.drones.workspaces.model import DroneWorkspace
from aura.drones.workspaces.paths import edit_candidate_dir


def build_candidate_dispatch_prompt(
    workspace: DroneWorkspace, brief: DroneBuildBrief
) -> dict:
    """Return a dispatch spec dict for the Worker to build a new Drone candidate."""
    cand = edit_candidate_dir(workspace)

    spec = f"""Write a complete folder-backed Drone in the candidate directory.

The candidate directory is: {cand}

Write the following files:
- drone.json — Drone manifest following the DroneDefinition fields from aura/drones/definition.py:
  id, name, description, instructions, write_policy, output_contract, budget,
  entrypoint (dict with kind/command/protocol), route, input_contract, cargo_contract,
  permissions, secrets, dependencies, manifest_version, scope, runtime
- An entrypoint program (e.g. main.py) — a self-contained script that reads JSON from
  stdin, calls an internal run(payload) function, prints JSON to stdout.
- requirements.txt — only if dependencies beyond stdlib are needed.
- Optional README.md.

CRITICAL RULES:
- Do NOT call register_drone_folder. Candidate build is NOT installation.
- Do NOT install anything globally.
- Write files inside {cand} using absolute or workspace-relative paths.
- Use "python" as the first entrypoint command element (or "node" for JS).
- The build brief below is the source of truth for what to build.

- input_contract and cargo_contract each take the shape:
  {{"type": "<PascalCaseName>", "description": "...", "schema": {{<field>: "<string|number|bool|list|object|any>"}}}}
  cargo_contract.schema lists the top-level fields the drone prints to stdout.
  input_contract.schema lists the top-level fields the drone requires from its stdin.
  When the build brief says this drone consumes another drone's output,
  input_contract.schema must name the fields it reads with coarse types,
  so the chain validator can match shapes structurally.
  A pure source drone may leave input_contract empty (or omit it);
  a pure sink may leave cargo_contract empty (or omit it).

BUILD BRIEF:
{brief.build_brief}
"""

    acceptance = """Acceptance criteria:
1. py_compile the entrypoint program if it's Python.
2. Verify drone.json is valid JSON with the required fields: id, name, description,
   instructions, write_policy, output_contract, entrypoint.
3. Verify the entrypoint command points to a file that exists in the candidate folder.
4. drone.json includes both input_contract and cargo_contract keys. Each non-empty
   contract contains a "schema" object whose values are drawn from the coarse type set
   (string|number|bool|list|object|any).
"""

    return {
        "goal": f"Build Drone: {workspace.display_name}",
        "files": [str(cand)],
        "spec": spec,
        "acceptance": acceptance,
        "summary": f"Build new Drone from workshop brief:\n{brief.build_brief[:500]}",
    }


def build_repair_dispatch_prompt(
    workspace: DroneWorkspace, user_revision: str
) -> dict:
    """Return a dispatch spec dict for the Worker to repair the existing candidate."""
    cand = edit_candidate_dir(workspace)

    spec = f"""Read the existing Drone candidate in {cand} and apply the revision feedback below.

REVISION FEEDBACK:
{user_revision}

RULES:
- Read existing candidate files first before making changes.
- Keep changes minimal and focused on the feedback.
- Do NOT call register_drone_folder.
- Do NOT change the drone id.
- Write files inside {cand} using absolute or workspace-relative paths.
"""

    acceptance = """Acceptance criteria:
1. py_compile the entrypoint program if it's Python (after changes).
2. Verify drone.json remains valid JSON with required fields.
3. Verify the entrypoint command still points to an existing file.
"""

    return {
        "goal": f"Repair Drone: {workspace.display_name}",
        "files": [str(cand)],
        "spec": spec,
        "acceptance": acceptance,
        "summary": f"Apply revision to Drone:\n{user_revision[:500]}",
    }
