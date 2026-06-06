"""Hidden TaskShape inference for Planner -> Worker dispatches."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


TASK_KINDS = {
    "new_tool_or_app",
    "bugfix",
    "gui_polish",
    "cleanup",
    "refactor",
    "diagnostic",
    "docs",
    "unknown",
}


@dataclass
class TaskShape:
    task_kind: str = "unknown"
    user_intent: str = ""
    core_flow: list[str] = field(default_factory=list)
    likely_entities: list[str] = field(default_factory=list)
    forbidden_moves: list[str] = field(default_factory=list)
    quality_pressure: list[str] = field(default_factory=list)
    proof_targets: list[str] = field(default_factory=list)
    craft_pressure: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.task_kind not in TASK_KINDS:
            self.task_kind = "unknown"
        self.user_intent = str(self.user_intent)
        self.core_flow = _string_list(self.core_flow)
        self.likely_entities = _string_list(self.likely_entities)
        self.forbidden_moves = _string_list(self.forbidden_moves)
        self.quality_pressure = _string_list(self.quality_pressure)
        self.proof_targets = _string_list(self.proof_targets)
        self.craft_pressure = _string_list(self.craft_pressure)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_kind": self.task_kind,
            "user_intent": self.user_intent,
            "core_flow": list(self.core_flow),
            "likely_entities": list(self.likely_entities),
            "forbidden_moves": list(self.forbidden_moves),
            "quality_pressure": list(self.quality_pressure),
            "proof_targets": list(self.proof_targets),
            "craft_pressure": list(self.craft_pressure),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "TaskShape":
        if not isinstance(data, dict):
            return unknown_task_shape()
        try:
            return cls(
                task_kind=str(data.get("task_kind", "unknown")),
                user_intent=str(data.get("user_intent", "")),
                core_flow=_string_list(data.get("core_flow")),
                likely_entities=_string_list(data.get("likely_entities")),
                forbidden_moves=_string_list(data.get("forbidden_moves")),
                quality_pressure=_string_list(data.get("quality_pressure")),
                proof_targets=_string_list(data.get("proof_targets")),
                craft_pressure=_string_list(data.get("craft_pressure")),
            )
        except Exception:
            return unknown_task_shape()


def unknown_task_shape(user_intent: str = "") -> TaskShape:
    return TaskShape(
        task_kind="unknown",
        user_intent=user_intent,
        proof_targets=["prefer focused validation over unrelated validation"],
        quality_pressure=["keep the implementation direct and scoped"],
    )


def infer_task_shape(
    goal: str = "",
    spec: str = "",
    files: list[str] | None = None,
    user_text: str = "",
) -> TaskShape:
    """Infer a compact, deterministic work shape from existing dispatch text."""
    files = files or []
    text_parts = [goal, spec, user_text, " ".join(files)]
    joined = " ".join(part for part in text_parts if part).strip()
    normalized = _normalize_text(joined)
    task_kind = _classify_task_kind(normalized)
    intent = _first_non_empty(goal, user_text, spec)
    entities = _likely_entities(normalized, files)

    if task_kind == "new_tool_or_app":
        return TaskShape(
            task_kind=task_kind,
            user_intent=intent,
            core_flow=[
                "configure or create the thing",
                "run the main action",
                "review useful results",
                "handle empty/error states",
                "continue from saved state when relevant",
            ],
            likely_entities=entities,
            forbidden_moves=[
                "placeholder TODO bodies",
                "pass/NotImplementedError as implementation",
                "fake integrations",
                "demo/mock production scaffolding",
                "generic Manager/Processor/Handler soup unless clearly earned",
                "silent failure or fake success",
                "broad architecture ceremony without behavior",
            ],
            quality_pressure=[
                "build the smallest shippable slice, not a demo",
                "make the core user flow real",
                "represent state explicitly",
                "use domain-shaped names",
                "surface empty/error states honestly",
                "keep the implementation direct and understandable",
                "add only extension seams that naturally serve the product",
            ],
            proof_targets=[
                "prove the core flow runs or is directly exercised",
                "run py_compile for touched Python files when relevant",
                "prefer focused validation over unrelated validation",
            ],
            craft_pressure=[
                "block placeholder/demo/fake production code",
                "block stub implementations",
                "block silent exception swallowing",
                "block markdown/code-fence residue",
                "discourage generic scaffolding names",
            ],
        )

    base = _base_shape(task_kind, intent, entities)
    return base


def implementation_standard_lines(shape: TaskShape | None) -> list[str]:
    """Return compact Worker-facing implementation guidance for a shape."""
    if shape is None:
        shape = unknown_task_shape()
    kind = shape.task_kind if shape.task_kind in TASK_KINDS else "unknown"
    if kind == "new_tool_or_app":
        return [
            "Build the smallest shippable slice, not a demo.",
            "Make the core user flow real.",
            "Use explicit state and domain-shaped names.",
            "Surface empty/error states honestly.",
            "Avoid fake integrations, placeholder bodies, demo/mock production scaffolding, and generic abstraction soup.",
            "Add only extension seams that naturally serve the product.",
        ]
    if kind == "bugfix":
        return [
            "Make the fix surgical and preserve compatibility.",
            "Change only the behavior needed to remove the bug.",
            "Prove the changed behavior with focused validation.",
        ]
    if kind == "gui_polish":
        return [
            "Keep user states, copy, and layout clear.",
            "Preserve the existing signal/data flow.",
            "Validate the UI-facing behavior when practical.",
        ]
    if kind == "cleanup":
        return [
            "Remove dead code and simplify directly.",
            "Do not replace clutter with architecture ceremony.",
            "Keep proof focused on unchanged behavior.",
        ]
    if kind == "refactor":
        return [
            "Preserve behavior and public compatibility.",
            "Reduce complexity without broadening scope.",
            "Keep validation focused on affected behavior.",
        ]
    if kind == "diagnostic":
        return [
            "Inspect first and report concrete findings.",
            "Avoid speculative edits unless the fix is directly proven.",
        ]
    if kind == "docs":
        return [
            "Make the documentation accurate, concrete, and scoped.",
            "Keep examples aligned with current code.",
        ]
    return [
        "Keep the implementation direct and scoped.",
        "Avoid placeholders, fake success, and unrelated architecture.",
        "Use focused validation for touched files when relevant.",
    ]


def _base_shape(task_kind: str, intent: str, entities: list[str]) -> TaskShape:
    if task_kind == "bugfix":
        return TaskShape(
            task_kind=task_kind,
            user_intent=intent,
            likely_entities=entities,
            forbidden_moves=["broad unrelated rewrites", "silent failure or fake success"],
            quality_pressure=["make the fix surgical", "preserve compatibility"],
            proof_targets=["prove the changed behavior", "run focused validation"],
        )
    if task_kind == "gui_polish":
        return TaskShape(
            task_kind=task_kind,
            user_intent=intent,
            likely_entities=entities,
            forbidden_moves=["unrelated signal-flow rewrites", "placeholder copy"],
            quality_pressure=["clarify user states, copy, and layout", "preserve signal flow"],
            proof_targets=["exercise the visible state or affected UI path"],
        )
    if task_kind == "cleanup":
        return TaskShape(
            task_kind=task_kind,
            user_intent=intent,
            likely_entities=entities,
            forbidden_moves=["new architecture ceremony", "behavior changes without proof"],
            quality_pressure=["remove dead code", "simplify without broadening scope"],
            proof_targets=["prove behavior remains unchanged where relevant"],
        )
    if task_kind == "refactor":
        return TaskShape(
            task_kind=task_kind,
            user_intent=intent,
            likely_entities=entities,
            forbidden_moves=["behavior changes without proof", "unrelated redesign"],
            quality_pressure=["preserve behavior", "reduce complexity"],
            proof_targets=["run focused compatibility validation"],
        )
    if task_kind == "diagnostic":
        return TaskShape(
            task_kind=task_kind,
            user_intent=intent,
            likely_entities=entities,
            forbidden_moves=["speculative production edits", "fake certainty"],
            quality_pressure=["inspect before changing", "separate findings from fixes"],
            proof_targets=["show concrete evidence for the finding"],
        )
    if task_kind == "docs":
        return TaskShape(
            task_kind=task_kind,
            user_intent=intent,
            likely_entities=entities,
            forbidden_moves=["stale examples", "unsupported claims"],
            quality_pressure=["keep docs accurate and concrete"],
            proof_targets=["cross-check examples against current code when practical"],
        )
    return unknown_task_shape(intent)


def _classify_task_kind(text: str) -> str:
    if _has(text, r"\b(?:fix|bug|broken|failing|error|blocked|regression)\b"):
        return "bugfix"
    if _has(text, r"\b(?:ui|gui|button|card|dialog|copy|label|layout|screen)\b"):
        return "gui_polish"
    if _has(text, r"\b(?:cleanup|clean up|remove|delete|dead code|simplify)\b"):
        return "cleanup"
    if _has(text, r"\b(?:refactor|restructure|extract|rename)\b"):
        return "refactor"
    if _has(text, r"\b(?:inspect|debug|investigate|find why|check)\b"):
        return "diagnostic"
    if _has(text, r"\b(?:docs|readme|documentation|guide)\b"):
        return "docs"
    if _has(
        text,
        r"\b(?:build|create|make|add)\b.*\b(?:tool|app|dashboard|scout|tracker|workflow|project)\b",
    ):
        return "new_tool_or_app"
    return "unknown"


def _likely_entities(text: str, files: list[str]) -> list[str]:
    entities: list[str] = []
    for noun in ("tool", "app", "dashboard", "scout", "tracker", "workflow", "project"):
        if re.search(rf"\b{noun}\b", text):
            entities.append(noun)
    for file_path in files:
        name = str(file_path).replace("\\", "/").rsplit("/", 1)[-1]
        stem = name.rsplit(".", 1)[0]
        if stem and stem not in entities:
            entities.append(stem)
    return entities[:8]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _has(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _first_non_empty(*items: str) -> str:
    for item in items:
        stripped = str(item).strip()
        if stripped:
            return stripped
    return ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


__all__ = [
    "TASK_KINDS",
    "TaskShape",
    "implementation_standard_lines",
    "infer_task_shape",
    "unknown_task_shape",
]
