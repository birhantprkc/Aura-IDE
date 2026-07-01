"""GUI-side canonical Worker TODO reconciliation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from aura.todo_state import todo_task_description, todo_task_status


@dataclass
class WorkerTodoRow:
    id: str
    description: str
    status: str = "pending"
    files: list[str] = field(default_factory=list)
    match_keys: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "step_id": self.id,
            "description": self.description,
            "status": self.status,
        }
        if self.files:
            result["files"] = list(self.files)
        return result


class WorkerTodoState:
    """Keeps Planner dispatch steps canonical in the live Worker TODO list."""

    def __init__(self) -> None:
        self._canonical: dict[str, list[WorkerTodoRow]] = {}
        self._active_tool_call_id: str | None = None

    def begin_dispatch(self, tool_call_id: str, steps: list[Any]) -> list[dict[str, Any]]:
        self._canonical.clear()
        rows: list[WorkerTodoRow] = []
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            row_id = str(step.get("id") or step.get("step_id") or f"step-{index}").strip()
            description = _step_description(step, index)
            rows.append(
                WorkerTodoRow(
                    id=row_id,
                    description=description,
                    files=_str_list(step.get("files")),
                    match_keys=_step_match_keys(step, description),
                )
            )
        self._active_tool_call_id = tool_call_id
        if rows:
            self._canonical[tool_call_id] = rows
            return self.snapshot(tool_call_id)
        self._canonical.pop(tool_call_id, None)
        return []

    def render_active(self, tool_call_id: str) -> list[dict[str, Any]]:
        self._active_tool_call_id = tool_call_id
        return self.snapshot(tool_call_id)

    def reconcile(
        self,
        tasks: list[Any],
        *,
        tool_call_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if (
            tool_call_id is not None
            and self._active_tool_call_id is not None
            and tool_call_id != self._active_tool_call_id
        ):
            return self.snapshot(self._active_tool_call_id)
        dispatch_id = tool_call_id or self._active_tool_call_id
        if not dispatch_id or dispatch_id not in self._canonical:
            return tasks if isinstance(tasks, list) else []

        rows = self._canonical[dispatch_id]
        changed = False
        for task in tasks if isinstance(tasks, list) else []:
            if not isinstance(task, dict):
                continue
            status = todo_task_status(task)
            if status == "pending":
                continue

            row = self._match_row(rows, task)
            if row is None and status == "active":
                row = self._next_unfinished(rows)
            elif row is None and status == "done":
                row = self._single_active(rows)
            if row is None or row.status == "done":
                continue

            if status == "active":
                changed |= self._set_active(rows, row)
            elif status == "done":
                row.status = "done"
                changed = True

        return self.snapshot(dispatch_id) if changed else self.snapshot(dispatch_id)

    def finish(
        self,
        tool_call_id: str,
        *,
        ok: bool,
        needs_followup: bool,
    ) -> list[dict[str, Any]]:
        rows = self._canonical.get(tool_call_id)
        if not rows:
            return []
        if ok and not needs_followup:
            for row in rows:
                row.status = "done"
        return self.snapshot(tool_call_id)

    def clear(self, tool_call_id: str | None = None) -> list[dict[str, Any]]:
        if tool_call_id is None:
            self._canonical.clear()
            self._active_tool_call_id = None
            return []
        self._canonical.pop(tool_call_id, None)
        if self._active_tool_call_id == tool_call_id:
            self._active_tool_call_id = None
        return []

    def snapshot(self, tool_call_id: str) -> list[dict[str, Any]]:
        rows = self._canonical.get(tool_call_id, [])
        return [row.to_dict() for row in rows]

    @staticmethod
    def _match_row(rows: list[WorkerTodoRow], task: dict[str, Any]) -> WorkerTodoRow | None:
        task_id = str(task.get("id") or task.get("step_id") or "").strip()
        if task_id:
            for row in rows:
                if row.id == task_id:
                    return row

        keys = _task_match_keys(task)
        if not keys:
            return None
        for row in rows:
            if row.match_keys.intersection(keys):
                return row
        return None

    @staticmethod
    def _next_unfinished(rows: list[WorkerTodoRow]) -> WorkerTodoRow | None:
        for row in rows:
            if row.status != "done":
                return row
        return None

    @staticmethod
    def _single_active(rows: list[WorkerTodoRow]) -> WorkerTodoRow | None:
        active = [row for row in rows if row.status == "active"]
        return active[0] if len(active) == 1 else None

    @staticmethod
    def _set_active(rows: list[WorkerTodoRow], target: WorkerTodoRow) -> bool:
        changed = False
        for row in rows:
            if row is target:
                continue
            if row.status == "active":
                row.status = "pending"
                changed = True
        if target.status != "active":
            target.status = "active"
            changed = True
        return changed


def _step_description(step: dict[str, Any], index: int) -> str:
    text = str(
        step.get("title")
        or step.get("goal")
        or step.get("description")
        or f"Step {index}"
    ).strip()
    return text or f"Step {index}"


def _step_match_keys(step: dict[str, Any], description: str) -> set[str]:
    values = [
        description,
        step.get("title"),
        step.get("goal"),
        step.get("description"),
        step.get("content"),
        step.get("text"),
        step.get("task"),
    ]
    return {_normalize(value) for value in values if _normalize(value)}


def _task_match_keys(task: dict[str, Any]) -> set[str]:
    values = [
        todo_task_description(task),
        task.get("title"),
        task.get("goal"),
        task.get("description"),
        task.get("content"),
        task.get("text"),
        task.get("task"),
    ]
    return {_normalize(value) for value in values if _normalize(value)}


def _normalize(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]
