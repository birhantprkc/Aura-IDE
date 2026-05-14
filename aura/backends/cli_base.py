"""Base class for CLI-based agent backends that require device/CLI auth."""

from __future__ import annotations

import logging
import queue
import threading
import uuid
from pathlib import Path
from abc import abstractmethod
from collections.abc import Generator
from typing import Any

from aura.backends.base import AgentBackend
from aura.client.events import (
    AgentProcessFinished,
    AgentProcessOutput,
    AgentProcessStarted,
    Event,
)
from aura.sandbox import SandboxExecutor, SandboxResult

logger = logging.getLogger(__name__)


class CLIAgentBackend(AgentBackend):
    """Base for backends that shell out to a CLI tool (gcloud, gh, codex, etc.).

    Subclasses must provide:
      - auth_command: the shell command to run for interactive auth
        (e.g., "gcloud auth application-default login")
      - A check_auth() implementation that probes whether auth already exists
        (e.g., runs a credential check command or looks for a credential file)

    The default implementations of check_auth() and run_cli_auth() in the
    parent AgentBackend class assume API-key-based auth is always ready;
    CLI backends override them here.
    """

    # Override in subclasses — the shell command for interactive auth.
    auth_command: str | None = None

    # Maximum seconds to wait for auth to complete after launching terminal.
    auth_timeout_seconds: int = 120

    def __init__(self, workspace_root: Path | None = None) -> None:
        """Initialise the CLI backend.

        Args:
            workspace_root: Working directory for subprocess execution.
                Defaults to ``Path.cwd()``.
        """
        self._workspace_root = workspace_root or Path.cwd()

    def check_auth(self) -> bool:
        """Probe whether the CLI tool has valid credentials.

        Subclasses must override this to run the actual credential check.

        Returns:
            True if credentials are valid, False otherwise.
        """
        return False

    def run_cli_auth(self) -> bool:
        """Launch the auth_command in an interactive terminal, then poll for auth.

        Launches the terminal detached (fire-and-forget via
        :meth:`SandboxExecutor._launch_interactive_terminal`), then polls
        :meth:`check_auth` every 2 seconds until the timeout expires.

        Returns:
            True if authentication succeeded (check_auth returns True within
            the timeout), False otherwise.
        """
        if not self.auth_command:
            return True  # No auth command configured; assume already authed

        # Launch the terminal (non-blocking, fire-and-forget)
        launched = SandboxExecutor._launch_interactive_terminal(
            command=self.auth_command,
            workspace_root=self._workspace_root,
        )

        if not launched:
            logger.warning(
                "Failed to launch interactive terminal for auth command: %s",
                self.auth_command,
            )
            return False

        # Poll check_auth() until success or timeout
        import time

        deadline = time.monotonic() + self.auth_timeout_seconds
        while time.monotonic() < deadline:
            try:
                if self.check_auth():
                    logger.info("Auth succeeded for command: %s", self.auth_command)
                    return True
            except Exception as exc:
                logger.exception("check_auth() raised during polling: %s", exc)
                return False
            time.sleep(2)

        logger.warning(
            "Auth timed out after %d seconds for command: %s",
            self.auth_timeout_seconds,
            self.auth_command,
        )
        return False

    def _run_cli_agent_command(
        self,
        *,
        command: str,
        label: str,
        timeout: int = 120,
        cancel_event: threading.Event | None = None,
        input_data: str | None = None,
    ) -> Generator[Event, None, SandboxResult]:
        """Run a CLI agent command while yielding live process output events."""
        process_id = f"cli-{uuid.uuid4().hex}"
        events: queue.Queue[tuple[str, str | SandboxResult]] = queue.Queue()

        yield AgentProcessStarted(
            process_id=process_id,
            label=label,
            command=command,
        )

        def on_output(text: str) -> None:
            events.put(("output", text))

        def run_command() -> None:
            try:
                sandbox = SandboxExecutor(mode="host", workspace_root=self._workspace_root)
                result = sandbox.run_terminal_command(
                    command=command,
                    timeout=timeout,
                    cancel_event=cancel_event,
                    on_output=on_output,
                    input_data=input_data,
                )
            except Exception as exc:
                result = SandboxResult(
                    ok=False,
                    stdout="",
                    stderr=f"{type(exc).__name__}: {exc}",
                    exit_code=-1,
                )
            events.put(("result", result))

        thread = threading.Thread(
            target=run_command,
            name=f"Aura {label} CLI process",
            daemon=True,
        )
        thread.start()

        result: SandboxResult | None = None
        while result is None:
            kind, payload = events.get()
            if kind == "output":
                yield AgentProcessOutput(process_id=process_id, text=str(payload))
            else:
                result = payload if isinstance(payload, SandboxResult) else SandboxResult(
                    ok=False,
                    stdout="",
                    stderr="CLI process did not return a SandboxResult.",
                    exit_code=-1,
                )

        thread.join(timeout=0)
        yield AgentProcessFinished(process_id=process_id, exit_code=result.exit_code)
        return result

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        thinking: str,
        cancel_event: Any = None,
        temperature: float = 0.7,
    ) -> Any:
        """Stream a model response, yielding Event objects.

        Subclasses must implement this — it is the core backend interface.
        """
        ...
