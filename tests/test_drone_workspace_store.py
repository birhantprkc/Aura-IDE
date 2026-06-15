from __future__ import annotations

import json
from pathlib import Path

import pytest

from aura.drones.workspaces.paths import candidate_dir
from aura.drones.workspaces.store import DroneWorkspaceStore


def _write_candidate_drone_json(
    project_root: Path, workspace_id: str, name: str
) -> Path:
    """Write a minimal drone.json with the given name into the candidate folder."""
    folder = candidate_dir(project_root, workspace_id)
    folder.mkdir(parents=True, exist_ok=True)
    drone_json = folder / "drone.json"
    drone_json.write_text(
        json.dumps({"name": name, "description": "test drone"}, indent=2),
        encoding="utf-8",
    )
    return drone_json


class TestSyncDisplayNameFromCandidate:
    def test_sync_display_name_updates_from_candidate_name(
        self, tmp_path: Path
    ) -> None:
        workspace = DroneWorkspaceStore.create_workspace(tmp_path, "New Drone")
        original_id = workspace.workspace_id

        _write_candidate_drone_json(
            tmp_path, workspace.workspace_id, "File Size Mapper"
        )

        changed = DroneWorkspaceStore.sync_display_name_from_candidate(
            tmp_path, workspace
        )
        assert changed is True
        assert workspace.display_name == "File Size Mapper"
        assert workspace.workspace_id == original_id

        # Reload from disk and verify persistence
        reloaded = DroneWorkspaceStore.load_workspace(
            tmp_path, workspace.workspace_id
        )
        assert reloaded is not None
        assert reloaded.display_name == "File Size Mapper"

    def test_sync_display_name_noop_when_no_candidate(
        self, tmp_path: Path
    ) -> None:
        workspace = DroneWorkspaceStore.create_workspace(tmp_path, "My Drone")

        changed = DroneWorkspaceStore.sync_display_name_from_candidate(
            tmp_path, workspace
        )
        assert changed is False
        assert workspace.display_name == "My Drone"

    def test_sync_display_name_noop_when_name_matches(
        self, tmp_path: Path
    ) -> None:
        workspace = DroneWorkspaceStore.create_workspace(tmp_path, "Already Good")
        _write_candidate_drone_json(
            tmp_path, workspace.workspace_id, "Already Good"
        )

        changed = DroneWorkspaceStore.sync_display_name_from_candidate(
            tmp_path, workspace
        )
        assert changed is False
        assert workspace.display_name == "Already Good"

    def test_sync_display_name_preserves_threads(
        self, tmp_path: Path
    ) -> None:
        workspace = DroneWorkspaceStore.create_workspace(tmp_path, "New Drone")

        thread = DroneWorkspaceStore.create_thread(
            tmp_path, workspace.workspace_id, "Test Thread"
        )
        assert thread is not None

        _write_candidate_drone_json(
            tmp_path, workspace.workspace_id, "File Size Mapper"
        )

        changed = DroneWorkspaceStore.sync_display_name_from_candidate(
            tmp_path, workspace
        )
        assert changed is True
        assert workspace.display_name == "File Size Mapper"

        # Reload and check threads are still present
        reloaded = DroneWorkspaceStore.load_workspace(
            tmp_path, workspace.workspace_id
        )
        assert reloaded is not None
        assert reloaded.display_name == "File Size Mapper"

        threads = DroneWorkspaceStore.list_threads(
            tmp_path, workspace.workspace_id
        )
        assert len(threads) == 1
        assert threads[0].title == "Test Thread"
