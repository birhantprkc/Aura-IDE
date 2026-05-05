"""Planner -> Worker dispatch types.

The planner manager calls `dispatch_to_worker` (a tool) when it has enough
information to delegate a code change. Args are validated here, the manager
emits a WorkerDispatchRequested event to the GUI, then calls a
DispatchCallback to actually run the worker; the result is fed back to the
planner as the tool_result for that call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class WorkerDispatchRequest:
    goal: str
    files: list[str]
    spec: str
    acceptance: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "files": list(self.files),
            "spec": self.spec,
            "acceptance": self.acceptance,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkerDispatchRequest":
        files = data.get("files") or []
        if not isinstance(files, list):
            files = []
        return cls(
            goal=str(data.get("goal", "")),
            files=[str(f) for f in files],
            spec=str(data.get("spec", "")),
            acceptance=str(data.get("acceptance", "")),
        )


@dataclass
class WorkerDispatchResult:
    ok: bool
    summary: str
    cancelled: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    def to_tool_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "cancelled": self.cancelled,
            "summary": self.summary,
            **({"extras": self.extras} if self.extras else {}),
        }


DispatchCallback = Callable[[str, WorkerDispatchRequest], WorkerDispatchResult]
"""Called from the planner's worker thread.

Args: (tool_call_id, request). Blocks until the GUI/user has approved or
cancelled the dispatch and (if approved) the worker manager has finished.
"""


__all__ = [
    "WorkerDispatchRequest",
    "WorkerDispatchResult",
    "DispatchCallback",
]
