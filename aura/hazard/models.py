from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HazardRecord:
    model: str
    status: str
    failure_class: str | None
    target_files: tuple[str, ...]
    task_kind: str | None
    error_signature: str | None
    raw_errors: tuple[str, ...]
    tool_call_id: str
    created_at: str

    def to_row(self) -> tuple[Any, ...]:
        return (
            self.model,
            self.status,
            self.failure_class,
            json.dumps(list(self.target_files)),
            self.task_kind,
            self.error_signature,
            json.dumps(list(self.raw_errors)),
            self.tool_call_id,
            self.created_at,
        )
