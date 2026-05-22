from __future__ import annotations

from typing import Any
from aura.conversation.tools._types import ToolExecResult


class PlannerHandlersMixin:
    """Mixin for ToolRegistry implementing planner-specific tool handlers."""

    def _handle_get_workspace_snapshot(
        self,
        args: dict[str, Any],
        approval_cb: Any,
        reject_all: bool,
    ) -> ToolExecResult:
        from aura.conversation.tools.workspace_snapshot_handler import gather_workspace_snapshot

        try:
            snapshot = gather_workspace_snapshot(self._root)
            return ToolExecResult(ok=True, payload=snapshot)
        except Exception:
            import sys

            exc = sys.exc_info()[1]
            return ToolExecResult(
                ok=False,
                payload={"error": str(exc), "workspace_root": str(self._root)},
            )
