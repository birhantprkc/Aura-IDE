"""Unified TODO rail owner for canonical dispatch campaigns.

DispatchTodoController is the single source of truth for the visible TODO
checklist during a Planner -> Worker dispatch. Once canonical objectives exist
for a tool_call_id, only the controller may emit visible TODO snapshots.

Rules:
- IDs and order never change after begin().
- Descriptions never change after begin().
- Worker-local TODOs are ignored during canonical dispatch.
- Worker cannot add, remove, reorder, or rename visible rows.
- Final checklist remains visible after dispatch finish.
- Clear canonical state only when a new dispatch begins for that tool ID,
  when the run is cancelled/reset, or when the owning conversation resets.

Allowed visible TODO states: pending, active, done.
There is no blocked state in the TODO row model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TodoObjective:
    """One stable row in the canonical dispatch TODO checklist."""

    id: str
    description: str
    status: str = "pending"
    files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "step_id": self.id,
            "description": self.description,
            "status": self.status,
        }
        if self.files:
            result["files"] = list(self.files)
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


class DispatchTodoController:
    """Owns canonical TODO state for every active tool_call_id.

    Once begin() is called for a tool_call_id, all visible TODO emissions
    for that ID must come through snapshot(). Worker-local updates are ignored.
    """

    def __init__(self) -> None:
        self._canonical: dict[str, dict[str, TodoObjective]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def begin(
        self,
        tool_call_id: str,
        objectives: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Set the canonical objective checklist for a tool_call_id.

        objectives: list of dicts with keys id, description, files, metadata.
        Returns the initial full snapshot.
        """
        ordered: dict[str, TodoObjective] = {}
        for obj in objectives:
            obj_id = str(obj.get("id") or "")
            if not obj_id:
                continue
            ordered[obj_id] = TodoObjective(
                id=obj_id,
                description=str(obj.get("description") or obj_id),
                status="pending",
                files=_str_list(obj.get("files")),
                metadata=dict(obj.get("metadata") or {}),
            )
        self._canonical[tool_call_id] = ordered
        return self.snapshot(tool_call_id)

    def snapshot(self, tool_call_id: str) -> list[dict[str, Any]]:
        """Return the full canonical checklist as a list of dicts.

        Order is stable (insertion order from begin()).
        """
        ordered = self._canonical.get(tool_call_id)
        if ordered is None:
            return []
        return [obj.to_dict() for obj in ordered.values()]

    def set_active(
        self, tool_call_id: str, objective_id: str
    ) -> list[dict[str, Any]]:
        """Mark one objective as active. Returns the full snapshot.

        Enforces one-active-row: any other non-done active row is
        returned to pending.
        """
        obj = self._get(tool_call_id, objective_id)
        if obj is None:
            return self.snapshot(tool_call_id)
        if obj.status == "done":
            return self.snapshot(tool_call_id)

        ordered = self._canonical.get(tool_call_id)
        if ordered is not None:
            for other_id, other in ordered.items():
                if other_id == objective_id:
                    continue
                if other.status == "done":
                    continue
                if other.status == "active":
                    other.status = "pending"

        obj.status = "active"
        return self.snapshot(tool_call_id)

    def mark_done(
        self, tool_call_id: str, objective_id: str
    ) -> list[dict[str, Any]]:
        """Mark one objective as done. Returns the full snapshot."""
        obj = self._get(tool_call_id, objective_id)
        if obj is None:
            return self.snapshot(tool_call_id)
        obj.status = "done"
        return self.snapshot(tool_call_id)

    def finish(self, tool_call_id: str) -> list[dict[str, Any]]:
        """Finalize the checklist. The checklist stays visible after finish.

        Returns the final full snapshot.
        """
        return self.snapshot(tool_call_id)

    def clear(self, tool_call_id: str) -> None:
        """Remove canonical state for a tool_call_id."""
        self._canonical.pop(tool_call_id, None)

    def clear_all(self) -> None:
        """Remove all canonical state across every tool_call_id.

        Called on conversation reset / new-chat to prevent stale TODO
        checklists from surviving into a fresh conversation.
        """
        self._canonical.clear()

    def has_canonical(self, tool_call_id: str) -> bool:
        """Return True if canonical objectives exist for this tool_call_id."""
        return tool_call_id in self._canonical

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(
        self, tool_call_id: str, objective_id: str
    ) -> TodoObjective | None:
        ordered = self._canonical.get(tool_call_id)
        if ordered is None:
            return None
        return ordered.get(objective_id)


def _str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


__all__ = [
    "DispatchTodoController",
    "TodoObjective",
]
