from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModeEntered:
    kind: str = "mode_entered"
    workspace_id: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class WorkspaceLoaded:
    kind: str = "workspace_loaded"
    workspace_id: str = ""
    display_name: str = ""
    phase: str = ""


@dataclass(frozen=True)
class WorkshopRequested:
    kind: str = "workshop_requested"
    messages: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class WorkshopQuestion:
    kind: str = "workshop_question"
    message: str = ""


@dataclass(frozen=True)
class WorkshopClarifying:
    kind: str = "workshop_clarifying"
    message: str = ""


@dataclass(frozen=True)
class BuildStarted:
    kind: str = "build_started"
    build_brief: str = ""
    dispatch_spec: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BuildCompleted:
    kind: str = "build_completed"
    candidate_path: str = ""
    drone_id: str = ""


@dataclass(frozen=True)
class BuildFailed:
    kind: str = "build_failed"
    error: str = ""


@dataclass(frozen=True)
class ReadinessRunning:
    kind: str = "readiness_running"


@dataclass(frozen=True)
class ReadinessPassed:
    kind: str = "readiness_passed"
    result: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ReadinessFailed:
    kind: str = "readiness_failed"
    error: str = ""
    detail: dict | None = None


@dataclass(frozen=True)
class ProofRunning:
    kind: str = "proof_running"


@dataclass(frozen=True)
class ProofCompleted:
    kind: str = "proof_completed"
    proof_result: ProofResult | None = None


@dataclass(frozen=True)
class AwaitingDecision:
    kind: str = "awaiting_decision"
    workspace_id: str = ""
    drone_name: str = ""
    proof_summary: str = ""


@dataclass(frozen=True)
class Installed:
    kind: str = "installed"
    drone_id: str = ""
    drone_name: str = ""


@dataclass(frozen=True)
class Discarded:
    kind: str = "discarded"
    workspace_id: str = ""


@dataclass(frozen=True)
class ErrorResult:
    kind: str = "error"
    message: str = ""


# ProofResult is defined here (not in proof.py) so results.py can reference it
# in the ProofCompleted dataclass.  proof.py re-exports it from this module.
@dataclass
class ProofResult:
    drone_name: str
    proof_status: str  # "passed", "failed", "warnings"
    what_tried: str
    route_used: str
    output_sample: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_result: dict = field(default_factory=dict)
    proof_run_path: str = ""
