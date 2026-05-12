"""Base class for CLI-based agent backends that require device/CLI auth."""

from __future__ import annotations

from pathlib import Path
from abc import abstractmethod
from typing import Any

from aura.backends.base import AgentBackend
from aura.sandbox import SandboxExecutor


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
        """Launch the auth_command in an interactive terminal subprocess.

        Blocks until the command exits. After success, calls check_auth()
        to verify credentials are now valid.

        Returns:
            True if authentication succeeded (exit code 0 and check_auth
            returns True), False otherwise.
        """
        if not self.auth_command:
            return True  # No auth command configured; assume already authed

        result = SandboxExecutor._run_interactive_command(
            command=self.auth_command,
            workspace_root=self._workspace_root,
        )

        if not result.ok:
            return False

        # Re-check auth after the command succeeds
        return self.check_auth()

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
