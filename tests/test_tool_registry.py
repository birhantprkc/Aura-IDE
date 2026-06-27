from __future__ import annotations

from unittest.mock import MagicMock

from aura.conversation.tools._types import ApprovalDecision
from aura.conversation.tools._write_mixin import _is_delete_protected_path
from aura.conversation.tools.registry import ToolRegistry


def _approve():
    return MagicMock(return_value=ApprovalDecision(action="approve"))


def test_delete_guard_keeps_git_and_env_paths_protected():
    assert _is_delete_protected_path(".git/config") is True
    assert _is_delete_protected_path(".env") is True
    assert _is_delete_protected_path(".env.local") is True


def test_delete_guard_keeps_aura_root_protected():
    assert _is_delete_protected_path(".aura") is True


def test_delete_guard_allows_aura_tmp_cleanup_file():
    assert _is_delete_protected_path(".aura/tmp/check.py") is False


def test_delete_guard_allows_aura_drone_definition_cleanup_file():
    assert _is_delete_protected_path(".aura/drones/bug-scout/drone.json") is False


def test_delete_file_still_rejects_directories_under_allowed_aura_paths(tmp_workspace):
    target = tmp_workspace / ".aura" / "tmp" / "run-output"
    target.mkdir(parents=True)
    approval = _approve()
    registry = ToolRegistry(tmp_workspace, mode="worker")

    result = registry.execute(
        "delete_file",
        {"path": ".aura/tmp/run-output", "reason": "cleanup"},
        approval,
        False,
    )

    assert result.ok is False
    assert result.payload["failure_class"] == "delete_file_is_directory"
    assert target.exists()
    approval.assert_not_called()
