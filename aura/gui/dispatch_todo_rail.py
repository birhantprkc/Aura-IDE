"""Render cache for bridge-owned dispatch TODO snapshots.

The bridge DispatchTodoController is the sole owner of dispatch TODO state.
DispatchTodoRail only replays bridge-emitted snapshots so the GUI can repaint
the rail after widget clears. It contains no status logic, matching, or
Planner-step seeding.
"""

from __future__ import annotations

from typing import Any


class DispatchTodoRail:
    """Cache the last canonical dispatch TODO snapshot by tool call id."""

    def __init__(self) -> None:
        self._snapshots: dict[str, list[Any]] = {}

    def set(self, tool_call_id: str | None, tasks: list[Any]) -> list[Any]:
        if tool_call_id is None:
            return list(tasks) if isinstance(tasks, list) else []
        snapshot = list(tasks) if isinstance(tasks, list) else []
        self._snapshots[tool_call_id] = snapshot
        return snapshot

    def replay(self, tool_call_id: str) -> list[Any]:
        return list(self._snapshots.get(tool_call_id, []))

    def reset(self, tool_call_id: str) -> None:
        self._snapshots.pop(tool_call_id, None)

    def clear(self) -> None:
        self._snapshots.clear()
