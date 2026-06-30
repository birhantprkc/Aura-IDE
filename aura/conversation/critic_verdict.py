from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CriticRoute = Literal["release", "worker", "planner"]


@dataclass
class CriticFinding:
    clause: str
    file: str
    message: str
    suggested_action: str

    def __post_init__(self) -> None:
        self.clause = str(self.clause or "").strip()
        self.file = str(self.file or "").strip()
        self.message = str(self.message or "").strip()
        self.suggested_action = str(self.suggested_action or "").strip()

    def to_dict(self) -> dict[str, str]:
        return {
            "clause": self.clause,
            "file": self.file,
            "message": self.message,
            "suggested_action": self.suggested_action,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "CriticFinding | None":
        if not isinstance(raw, dict):
            return None
        return cls(
            clause=str(raw.get("clause") or ""),
            file=str(raw.get("file") or ""),
            message=str(raw.get("message") or ""),
            suggested_action=str(raw.get("suggested_action") or ""),
        )


@dataclass
class CriticVerdict:
    conforms: bool
    route: CriticRoute
    findings: list[CriticFinding] = field(default_factory=list)
    instruction: str = ""
    planner_question: str = ""

    def __post_init__(self) -> None:
        self.findings = [
            finding
            for finding in (_coerce_finding(item) for item in self.findings)
            if finding is not None and finding.clause
        ]
        self.instruction = str(self.instruction or "").strip()
        self.planner_question = str(self.planner_question or "").strip()
        self.route = _coerce_route(self.route)
        self.conforms = bool(self.conforms)
        if not self.findings:
            self.conforms = True
            self.route = "release"
            self.instruction = ""
            self.planner_question = ""
        elif self.conforms or self.route == "release":
            self.findings = []
            self.instruction = ""
            self.planner_question = ""
            self.conforms = True
            self.route = "release"
        else:
            self.conforms = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "conforms": self.conforms,
            "route": self.route,
            "findings": [finding.to_dict() for finding in self.findings],
            "instruction": self.instruction,
            "planner_question": self.planner_question,
        }

    @classmethod
    def release(cls) -> "CriticVerdict":
        return cls(conforms=True, route="release", findings=[])

    @classmethod
    def from_dict(cls, raw: Any) -> "CriticVerdict":
        if not isinstance(raw, dict):
            return cls.release()
        findings = []
        raw_findings = raw.get("findings")
        if isinstance(raw_findings, list):
            findings = [
                finding
                for finding in (CriticFinding.from_dict(item) for item in raw_findings)
                if finding is not None
            ]
        return cls(
            conforms=bool(raw.get("conforms", False)),
            route=_coerce_route(raw.get("route")),
            findings=findings,
            instruction=str(raw.get("instruction") or ""),
            planner_question=str(raw.get("planner_question") or ""),
        )


def _coerce_finding(value: Any) -> CriticFinding | None:
    if isinstance(value, CriticFinding):
        return value
    return CriticFinding.from_dict(value)


def _coerce_route(value: Any) -> CriticRoute:
    route = str(value or "").strip()
    if route in {"worker", "planner"}:
        return route  # type: ignore[return-value]
    return "release"


__all__ = [
    "CriticFinding",
    "CriticRoute",
    "CriticVerdict",
]
