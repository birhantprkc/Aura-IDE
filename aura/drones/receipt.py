"""Receipt produced after a Drone execution completes."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DroneReceipt:
    """Summary of a completed Drone run."""
    run_id: str
    drone_id: str
    drone_name: str
    status: str  # completed, failed, cancelled, timed_out
    started_at: str  # ISO format
    ended_at: str    # ISO format
    tool_calls_made: int = 0
    tool_errors: int = 0
    summary: str = ""
    output_contract: str = ""
