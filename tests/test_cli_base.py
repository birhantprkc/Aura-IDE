"""Tests for CLI backend process event streaming."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

from aura.backends.cli_base import CLIAgentBackend
from aura.client.events import (
    AgentProcessFinished,
    AgentProcessOutput,
    AgentProcessStarted,
    Event,
)
from aura.sandbox import SandboxResult


class DummyCLIBackend(CLIAgentBackend):
    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        thinking: str,
        cancel_event: Any = None,
        temperature: float = 0.7,
    ) -> Iterator[Event]:
        return iter(())


def exhaust_with_return(iterator):
    events = []
    while True:
        try:
            events.append(next(iterator))
        except StopIteration as stop:
            return events, stop.value


def test_run_cli_agent_command_streams_process_events(tmp_path: Path) -> None:
    backend = DummyCLIBackend(workspace_root=tmp_path)
    expected = SandboxResult(ok=True, stdout="first\nsecond\n", stderr="", exit_code=0)

    def fake_run_terminal_command(
        command: str,
        timeout: int,
        cancel_event: Any,
        on_output: Any,
        input_data: str | None = None,
    ) -> SandboxResult:
        on_output("first\n")
        on_output("second\n")
        return expected

    with patch(
        "aura.backends.cli_base.SandboxExecutor.run_terminal_command",
        side_effect=fake_run_terminal_command,
    ):
        events, result = exhaust_with_return(
            backend._run_cli_agent_command(
                command="dummy run",
                label="Dummy",
                input_data="prompt",
            )
        )

    assert result == expected
    assert isinstance(events[0], AgentProcessStarted)
    assert events[0].label == "Dummy"
    assert events[0].command == "dummy run"
    assert [event.text for event in events if isinstance(event, AgentProcessOutput)] == [
        "first\n",
        "second\n",
    ]
    assert isinstance(events[-1], AgentProcessFinished)
    assert events[-1].process_id == events[0].process_id
    assert events[-1].exit_code == 0
