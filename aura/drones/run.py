"""Mutable runtime state for a single Drone execution."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from aura.drones.definition import DroneDefinition


@dataclass
class DroneRun:
    """Mutable runtime state for a single Drone execution.

    Lives on the GUI thread; the runner thread reads/writes cancel_event and status.
    """
    drone: DroneDefinition
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = "summoning"  # summoning, running, completed, failed, cancelled, timed_out
    cancel_event: threading.Event = field(default_factory=threading.Event)
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    events: list[Any] = field(default_factory=list)

    def cancel(self) -> None:
        """Request cancellation (thread-safe)."""
        self.cancel_event.set()

    @property
    def is_active(self) -> bool:
        return self.status in ("summoning", "running")

    @property
    def elapsed_seconds(self) -> float:
        end = self.ended_at or time.time()
        return end - self.started_at

    def mark(self, status: str) -> None:
        self.status = status
        if status in ("completed", "failed", "cancelled", "timed_out"):
            self.ended_at = time.time()
