from __future__ import annotations

from aura.drones.architect.build_prompts import (
    build_candidate_dispatch_prompt,
    build_repair_dispatch_prompt,
)
from aura.drones.architect.commands import DroneCommand, parse_drone_command
from aura.drones.architect.controller import DroneArchitectController
from aura.drones.architect.installer import install_or_reinstall
from aura.drones.architect.proof import run_candidate_proof
from aura.drones.architect.results import (
    AwaitingDecision,
    BuildCompleted,
    BuildFailed,
    BuildStarted,
    Discarded,
    ErrorResult,
    Installed,
    ModeEntered,
    ProofCompleted,
    ProofResult,
    ProofRunning,
    ReadinessFailed,
    ReadinessPassed,
    ReadinessRunning,
    WorkshopClarifying,
    WorkshopQuestion,
    WorkshopRequested,
    WorkspaceLoaded,
)
from aura.drones.architect.workshop_prompt import (
    WORKSHOP_SYSTEM_PROMPT,
    build_workshop_messages,
)

__all__ = [
    "DroneArchitectController",
    # Results
    "ModeEntered",
    "WorkspaceLoaded",
    "WorkshopRequested",
    "WorkshopQuestion",
    "WorkshopClarifying",
    "BuildStarted",
    "BuildCompleted",
    "BuildFailed",
    "ReadinessRunning",
    "ReadinessPassed",
    "ReadinessFailed",
    "ProofRunning",
    "ProofCompleted",
    "AwaitingDecision",
    "Installed",
    "Discarded",
    "ErrorResult",
    # Commands
    "DroneCommand",
    "parse_drone_command",
    # Workshop
    "WORKSHOP_SYSTEM_PROMPT",
    "build_workshop_messages",
    # Build
    "build_candidate_dispatch_prompt",
    "build_repair_dispatch_prompt",
    # Proof
    "ProofResult",
    "run_candidate_proof",
    # Installer
    "install_or_reinstall",
]
