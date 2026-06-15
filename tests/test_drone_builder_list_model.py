from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from aura import paths as aura_paths
from aura.drones.architect.commands import DroneCommand, parse_drone_command
from aura.drones.architect.controller import DroneArchitectController
from aura.drones.architect.installer import install_or_reinstall
from aura.drones.store import DroneStore
from aura.drones.workspaces.model import WorkspacePhase
from aura.drones.workspaces.paths import candidate_dir, chats_dir
from aura.drones.workspaces.store import DroneWorkspaceStore


@pytest.fixture(autouse=True)
def _patch_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(aura_paths, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr("aura.drones.store.data_dir", lambda: tmp_path / "data")


def _write_drone_folder(folder: Path, *, drone_id: str = "repo-scout") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "main.py").write_text(
        "import json, sys\n"
        "payload = json.loads(sys.stdin.read() or '{}')\n"
        "print(json.dumps({'ok': True, 'goal': payload.get('goal')}))\n",
        encoding="utf-8",
    )
    (folder / "drone.json").write_text(
        json.dumps(
            {
                "id": drone_id,
                "name": "Repo Scout",
                "description": "Finds repository updates.",
                "instructions": "Inspect repository activity.",
                "write_policy": "read_only",
                "output_contract": "Return repository updates.",
                "entrypoint": {
                    "kind": "command",
                    "command": ["python", "main.py"],
                    "protocol": "json-stdio",
                },
            }
        ),
        encoding="utf-8",
    )
    return folder


def test_drone_enter_mode_does_not_create_blank_draft_entry(tmp_path: Path) -> None:
    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)

    result = controller.enter_mode()

    assert result.kind == "mode_entered"
    assert result.workspace_id is None
    assert DroneStore.list_drone_entries(tmp_path) == []


def test_first_real_description_creates_visible_builder_entry(tmp_path: Path) -> None:
    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)
    controller.enter_mode()

    result = controller.handle_user_message("Build a Drone that summarizes PRs")

    assert result.kind == "workshop_requested"
    entries = DroneStore.list_drone_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0].name == "New Drone"
    assert entries[0].status == "Draft"
    assert entries[0].ready is False
    assert entries[0].workspace_id == controller.active_workspace.workspace_id


@pytest.mark.parametrize(
    "phase",
    [
        WorkspacePhase.BUILD_FAILED.value,
        WorkspacePhase.INSTALLED.value,
        WorkspacePhase.DISCARDED.value,
    ],
)
def test_drone_enter_mode_ignores_stale_failed_or_terminal_active_workspace(
    tmp_path: Path,
    phase: str,
) -> None:
    stale = DroneWorkspaceStore.create_workspace(tmp_path, "Broken Drone")
    stale.phase = phase
    stale.build_brief = "Old failed work"
    stale.last_error = "Old failure"
    DroneWorkspaceStore.save_workspace(stale)
    DroneWorkspaceStore.set_active_workspace(tmp_path, stale)

    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)

    entered = controller.enter_mode()
    result = controller.handle_user_message("Build a Drone that checks releases")

    reloaded_stale = DroneWorkspaceStore.load_workspace(tmp_path, stale.workspace_id)

    assert entered.kind == "mode_entered"
    assert result.kind == "workshop_requested"
    assert controller.active_workspace.workspace_id != stale.workspace_id
    assert reloaded_stale.phase == phase


@pytest.mark.parametrize(
    "phase",
    [WorkspacePhase.BUILD_FAILED.value],
)
def test_explicitly_selected_failed_builder_drone_accepts_revision(
    tmp_path: Path,
    phase: str,
) -> None:
    workspace = DroneWorkspaceStore.create_workspace(tmp_path, "Broken Drone")
    workspace.phase = phase
    workspace.build_brief = "Old failed work"
    DroneWorkspaceStore.save_workspace(workspace)

    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)

    loaded = controller.load_workspace(workspace.workspace_id)
    result = controller.handle_user_message("Make the manifest valid JSON")

    assert loaded.kind == "workspace_loaded"
    assert result.kind == "build_started"
    assert controller.active_workspace.workspace_id == workspace.workspace_id


def test_builder_candidate_entry_is_visible_but_not_runnable(tmp_path: Path) -> None:
    workspace = DroneWorkspaceStore.create_workspace(tmp_path, "Repo Scout")
    _write_drone_folder(candidate_dir(tmp_path, workspace.workspace_id))
    workspace.phase = WorkspacePhase.BUILDING.value
    workspace.candidate_drone_id = "repo-scout"
    DroneWorkspaceStore.save_workspace(workspace)

    entries = DroneStore.list_drone_entries(tmp_path)

    assert [(entry.name, entry.status, entry.ready) for entry in entries] == [
        ("Repo Scout", "Building", False)
    ]
    assert DroneStore.load_drone(tmp_path, "repo-scout") is None


def test_ready_step_promotes_builder_entry_to_ready_drone(
    tmp_path: Path,
) -> None:
    workspace = DroneWorkspaceStore.create_workspace(tmp_path, "Repo Scout")
    _write_drone_folder(candidate_dir(tmp_path, workspace.workspace_id))

    result = install_or_reinstall(workspace, tmp_path)

    assert result["ok"] is True, result
    entries = DroneStore.list_drone_entries(tmp_path)
    assert [(entry.id, entry.status, entry.ready) for entry in entries] == [
        ("repo-scout", "Ready", True)
    ]
    assert DroneStore.load_drone(tmp_path, "repo-scout") is not None


def test_installed_drone_appears_only_once_when_present(
    tmp_path: Path,
) -> None:
    """An installed Drone with its global folder intact appears exactly once as Ready."""
    workspace = DroneWorkspaceStore.create_workspace(tmp_path, "Repo Scout")
    _write_drone_folder(candidate_dir(tmp_path, workspace.workspace_id))

    result = install_or_reinstall(workspace, tmp_path)
    assert result["ok"] is True, result

    entries = DroneStore.list_drone_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0].id == "repo-scout"
    assert entries[0].status == "Ready"
    assert entries[0].ready is True


def test_installed_workspace_with_missing_global_drone_shows_as_needs_fix(
    tmp_path: Path,
) -> None:
    """When an installed Drone's global folder is deleted, the workspace shows as Needs Fix."""
    workspace = DroneWorkspaceStore.create_workspace(tmp_path, "Repo Scout")
    _write_drone_folder(candidate_dir(tmp_path, workspace.workspace_id))

    result = install_or_reinstall(workspace, tmp_path)
    assert result["ok"] is True, result

    # Delete the global drone folder to simulate corruption / accidental removal
    global_drone_dir = aura_paths.data_dir() / "drones" / "repo-scout"
    assert global_drone_dir.exists()
    shutil.rmtree(global_drone_dir)

    entries = DroneStore.list_drone_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0].name == "Repo Scout"
    assert entries[0].status == "Needs Fix"
    assert entries[0].ready is False


def test_install_candidate_fails_when_load_drone_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """install_or_reinstall fails if the registered Drone cannot be loaded back."""
    workspace = DroneWorkspaceStore.create_workspace(tmp_path, "Repo Scout")
    _write_drone_folder(candidate_dir(tmp_path, workspace.workspace_id))
    original_phase = workspace.phase

    monkeypatch.setattr(
        DroneStore,
        "load_drone",
        lambda *args, **kwargs: None,
    )

    result = install_or_reinstall(workspace, tmp_path)
    assert result["ok"] is False

    # Reload workspace to verify phase was NOT changed to "installed"
    reloaded = DroneWorkspaceStore.load_workspace(tmp_path, workspace.workspace_id)
    assert reloaded is not None
    assert reloaded.phase != "installed"


def test_install_and_register_are_not_user_commands() -> None:
    assert parse_drone_command("register it", "build_failed")[0] is DroneCommand.UNKNOWN
    assert parse_drone_command("register the drone", "build_failed")[0] is DroneCommand.UNKNOWN
    assert parse_drone_command("install", "build_failed")[0] is DroneCommand.UNKNOWN
    assert parse_drone_command("install the drone", "build_failed")[0] is DroneCommand.UNKNOWN


def test_build_failure_uses_dispatch_metadata_error(tmp_path: Path) -> None:
    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)
    controller.create_workspace("Broken Drone")

    result = controller.on_build_completed(
        False,
        error="",
        failure_detail={
            "status": "",
            "metadata": {
                "extras": {
                    "errors": ["Validation command failed (exit code 1): python -m py_compile main.py"],
                }
            },
        },
    )

    assert result.kind == "build_failed"
    assert "py_compile main.py" in result.error


def test_build_failure_uses_status_before_unknown(tmp_path: Path) -> None:
    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)
    controller.create_workspace("Broken Drone")

    result = controller.on_build_completed(
        False,
        error="",
        failure_detail={"status": "validation_failed", "metadata": {}},
    )

    assert result.kind == "build_failed"
    assert result.error == "Worker status: validation_failed"


def test_build_failure_without_worker_detail_uses_explicit_fallback(
    tmp_path: Path,
) -> None:
    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)
    controller.create_workspace("Broken Drone")

    result = controller.on_build_completed(False, error="", failure_detail={})

    assert result.kind == "build_failed"
    assert result.error == "Build failed without an error message from the Worker."


def test_build_failure_ignores_old_placeholder_summary(tmp_path: Path) -> None:
    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)
    controller.create_workspace("Broken Drone")
    old_placeholder = "Unknown " + "build error"

    result = controller.on_build_completed(
        False,
        error=old_placeholder,
        failure_detail={},
    )

    assert result.kind == "build_failed"
    assert result.error == "Build failed without an error message from the Worker."
    assert result.error != old_placeholder


# ---------------------------------------------------------------------------
# Thread persistence tests
# ---------------------------------------------------------------------------


def test_create_thread_persists_to_chats_dir(tmp_path: Path) -> None:
    """Creating a thread via the store writes a JSON file in chats_dir."""
    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)
    result = controller.create_workspace("Test Drone")
    assert result.kind == "workspace_loaded"
    ws_id = result.workspace_id

    cd = chats_dir(tmp_path, ws_id)
    json_files = list(cd.glob("*.json"))
    assert len(json_files) == 1

    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert data["workspace_id"] == ws_id
    assert data["title"] == "New thread"


def test_load_workspace_restores_thread_messages(tmp_path: Path) -> None:
    """Messages added to a thread survive a workspace reload."""
    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)
    controller.create_workspace("Test Drone")

    # Add a message via the workshop mechanism.
    msg_text = "Build a drone that checks for updates"
    controller._start_workshop_from_text(msg_text)  # type: ignore[attr-defined]

    assert len(controller.workshop_messages) == 1
    assert controller.workshop_messages[0]["role"] == "user"
    assert controller.workshop_messages[0]["content"] == msg_text

    # Reload the workspace
    ws = controller.active_workspace
    assert ws is not None
    controller.load_workspace(ws.workspace_id)

    assert len(controller.workshop_messages) == 1
    assert controller.workshop_messages[0]["content"] == msg_text


def test_multiple_threads_per_workspace(tmp_path: Path) -> None:
    """Multiple threads can exist for the same workspace."""
    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)
    controller.create_workspace("Test Drone")
    ws = controller.active_workspace
    assert ws is not None

    controller.create_new_thread()

    threads = DroneWorkspaceStore.list_threads(tmp_path, ws.workspace_id)
    assert len(threads) == 2


def test_exit_mode_saves_thread(tmp_path: Path) -> None:
    """Messages survive exit_mode / re-enter."""
    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)
    controller.create_workspace("Test Drone")

    msg_text = "Create a notification drone"
    controller._start_workshop_from_text(msg_text)  # type: ignore[attr-defined]

    assert len(controller.workshop_messages) == 1

    # Exit then re-enter
    controller.exit_mode()
    result = controller.enter_mode()
    assert result.kind == "workspace_loaded"

    assert len(controller.workshop_messages) == 1
    assert controller.workshop_messages[0]["content"] == msg_text


def test_switch_threads_preserves_each(tmp_path: Path) -> None:
    """Each thread retains its own messages when switching."""
    controller = DroneArchitectController()
    controller.set_workspace_root(tmp_path)
    controller.create_workspace("Test Drone")
    ws = controller.active_workspace
    assert ws is not None

    # First thread with its message
    first_msg = "Build drone one"
    controller._start_workshop_from_text(first_msg)  # type: ignore[attr-defined]
    assert len(controller.workshop_messages) == 1
    # Capture first thread ID before creating second.
    first_id = controller._active_thread.id  # type: ignore[union-attr]

    controller.create_new_thread()
    second_msg = "Build drone two"
    controller._start_workshop_from_text(second_msg)  # type: ignore[attr-defined]
    assert len(controller.workshop_messages) == 1
    assert controller.workshop_messages[0]["content"] == second_msg
    second_id = controller._active_thread.id  # type: ignore[union-attr]

    # Switch back to first thread
    controller.switch_thread(first_id)
    assert len(controller.workshop_messages) == 1
    assert controller.workshop_messages[0]["content"] == first_msg

    # Switch to second thread
    controller.switch_thread(second_id)
    assert len(controller.workshop_messages) == 1
    assert controller.workshop_messages[0]["content"] == second_msg
