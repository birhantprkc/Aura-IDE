from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from aura.conversation.history import History
from aura.conversation.manager import ConversationManager
from aura.conversation.tools.registry import ToolRegistry
from aura.python_env import (
    build_project_python_command,
    build_project_tool_command,
    detect_project_python_env,
)


def test_detect_project_python_env_prefers_dot_venv_scripts(tmp_path: Path) -> None:
    dot_venv = tmp_path / ".venv" / "Scripts"
    plain_venv = tmp_path / "venv" / "Scripts"
    plain_venv.mkdir(parents=True)
    dot_venv.mkdir(parents=True)
    (plain_venv / "python.exe").write_text("", encoding="utf-8")
    expected = dot_venv / "python.exe"
    expected.write_text("", encoding="utf-8")

    env = detect_project_python_env(tmp_path)

    assert env.python == expected


def test_py_compile_command_rewrites_to_project_venv(tmp_path: Path) -> None:
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")

    plan = build_project_python_command(
        tmp_path,
        "python -m py_compile aura/config.py",
    )

    assert str(python) in plan.command
    assert "-m py_compile aura/config.py" in plan.command


def test_pytest_without_project_venv_is_environment_setup_needed(tmp_path: Path) -> None:
    plan = build_project_tool_command(tmp_path, "pytest tests/test_x.py")

    assert plan.missing_dependency == "pytest"
    assert plan.command == "pytest tests/test_x.py"


def test_focused_py_compile_uses_project_venv(tmp_path: Path) -> None:
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    target = tmp_path / "aura" / "config.py"
    target.parent.mkdir()
    target.write_text("x = 1\n", encoding="utf-8")
    tools = MagicMock(spec=ToolRegistry)
    type(tools).workspace_root = PropertyMock(return_value=tmp_path)
    manager = ConversationManager(History(), tools)

    with patch("aura.conversation.manager.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, diagnostics = manager._run_focused_py_compile(["aura/config.py"])

    assert ok is True
    assert diagnostics == "aura/config.py: ok"
    assert run.call_args.args[0][0] == str(python)
