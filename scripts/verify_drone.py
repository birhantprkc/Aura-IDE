"""Verify the Git Commit & Push Drone was saved correctly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aura.config import load_workspace_root
from aura.drones.store import DroneStore


def main() -> None:
    wr = load_workspace_root() or Path.cwd()
    print(f"Workspace root: {wr}")

    # The latest id from the creation script run
    for did in ["git-commit-push", "git-commit-push-1"]:
        drone = DroneStore.load_drone(wr, did)
        if drone:
            print(f"\n=== {did} ===")
            print(f"  name: {drone.name}")
            print(f"  write_policy: {drone.write_policy}")
            print(f"  scope: {drone.scope}")
            print(f"  enabled: {drone.enabled}")
            print(f"  created_by: {drone.created_by}")
            print(f"  budget: rounds={drone.budget.max_tool_rounds}, timeout={drone.budget.timeout_seconds}")
            print(f"  capability_requirements: {len(drone.capability_requirements)}")
            print(f"  capability_bindings: {len(drone.capability_bindings)}")
            print(f"  setup_steps: {len(drone.setup_steps)}")
            print(f"  allowed_tools: {len(drone.allowed_tools)}: {list(drone.allowed_tools)}")
            print(f"  instructions: {len(drone.instructions)} chars")
            print(f"  output_contract: {len(drone.output_contract)} chars")
            print(f"  first_run_test: {len(drone.first_run_test)} chars")
            print("  ALL CHECKS PASSED")
        else:
            print(f"\n{did}: not found")

    print("\nDone.")


if __name__ == "__main__":
    main()
