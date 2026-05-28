"""Detect repeated non-progress tool loops."""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LoopDetectionResult:
    """Result payload after observing a tool execution."""

    content: str
    info: dict[str, Any] | None = None

    @property
    def triggered(self) -> bool:
        return self.info is not None


class LoopDetector:
    """Detect repeated identical tool failures.

    A success is treated as progress and clears prior failure history. Repeated
    identical failures are annotated for all modes, and become a recoverable
    phase boundary in worker mode so the planner can revise the approach.
    """

    def __init__(self, *, threshold: int = 3) -> None:
        self.threshold = threshold
        self._failures: dict[str, tuple[str, int]] = {}
        self._no_progress: dict[str, tuple[str, int]] = {}

    def observe(
        self,
        *,
        mode: str,
        tool_name: str,
        args: dict[str, Any],
        ok: bool,
        content: str,
    ) -> LoopDetectionResult:
        if ok:
            if tool_name == "update_todo_list":
                key = _tool_key(tool_name, args)
                last_output, count = self._no_progress.get(key, ("", 0))
                count = count + 1 if last_output == content else 1
                self._no_progress[key] = (content, count)
                if count >= self.threshold:
                    phase_boundary = mode == "worker"
                    info = {
                        "ok": False,
                        "loop_detected": True,
                        "recoverable": phase_boundary,
                        "phase_boundary": phase_boundary,
                        "reason": "repeated_no_progress",
                        "tool": tool_name,
                        "message": (
                            "Loop detected: this TODO update has repeated without changing "
                            "state. Stop calling tools and report completed work, blockers, "
                            "and remaining work so the planner can adjust the approach."
                            if phase_boundary
                            else (
                                "Loop detected: this TODO update has repeated without changing "
                                "state. Stop repeating the same call and move to the next step."
                            )
                        ),
                        "loop": {
                            "tool": tool_name,
                            "args_signature": key,
                            "repeated_calls": count,
                            "threshold": self.threshold,
                        },
                    }
                    return LoopDetectionResult(content=_annotate_content(content, info), info=info)
            else:
                self._no_progress.clear()
            self._failures.clear()
            return LoopDetectionResult(content=content)

        self._no_progress.clear()
        key = _tool_key(tool_name, args)
        last_output, count = self._failures.get(key, ("", 0))
        count = count + 1 if last_output == content else 1
        self._failures[key] = (content, count)

        if count < self.threshold:
            return LoopDetectionResult(content=content)

        phase_boundary = mode == "worker"
        info = {
            "ok": False,
            "loop_detected": True,
            "recoverable": phase_boundary,
            "phase_boundary": phase_boundary,
            "reason": "loop_detected",
            "tool": tool_name,
            "message": (
                "Loop detected: this tool has produced the same failure repeatedly. "
                "Stop calling tools and report completed work, blockers, and remaining "
                "work so the planner can adjust the approach."
                if phase_boundary
                else (
                    "Loop detected: this tool has produced the same failure repeatedly. "
                    "Stop repeating the same call and revise the approach."
                )
            ),
            "loop": {
                "tool": tool_name,
                "args_signature": key,
                "repeated_failures": count,
                "threshold": self.threshold,
            },
        }
        return LoopDetectionResult(content=_annotate_content(content, info), info=info)


def _tool_key(tool_name: str, args: dict[str, Any]) -> str:
    try:
        args_json = json.dumps(args, sort_keys=True, ensure_ascii=False)
    except TypeError:
        args_json = repr(args)
    if tool_name == "run_terminal_command":
        command = args.get("command", "")
        return f"terminal:{command}"
    if tool_name == "apply_edit_transaction":
        return f"{tool_name}:{json.dumps(_apply_edit_transaction_signature(args), sort_keys=True, ensure_ascii=False)}"
    return f"{tool_name}:{args_json}"


def _apply_edit_transaction_signature(args: dict[str, Any]) -> dict[str, Any]:
    operations = args.get("operations")
    markers: list[dict[str, Any]] = []
    if isinstance(operations, list):
        for op in operations:
            if not isinstance(op, dict):
                markers.append({"op": "invalid"})
                continue
            kind = str(op.get("op") or op.get("type") or "")
            marker: dict[str, Any] = {
                "op": kind,
                "symbol_type": op.get("symbol_type"),
                "symbol_name": op.get("symbol_name") or op.get("function_name") or op.get("method_name") or op.get("name"),
                "class_name": op.get("class_name"),
                "occurrence": op.get("occurrence"),
                "allow_multiple": op.get("allow_multiple"),
            }
            for source_key, marker_key in (
                ("old", "old_hash"),
                ("new", "new_hash"),
                ("text", "text_hash"),
                ("new_definition", "new_definition_hash"),
                ("content", "content_hash"),
                ("start_marker", "start_marker_hash"),
                ("end_marker", "end_marker_hash"),
            ):
                value = op.get(source_key)
                if isinstance(value, str):
                    marker[marker_key] = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
            markers.append({k: v for k, v in marker.items() if v not in (None, "")})
    return {"path": args.get("path"), "operations": markers}


def _annotate_content(content: str, info: dict[str, Any]) -> str:
    repeated = info["loop"].get("repeated_failures") or info["loop"].get("repeated_calls")
    warning = (
        f"\n\n[LOOP DETECTOR / CIRCUIT BREAKER: Repeated non-progress call "
        f"#{repeated}]\n"
        f"The tool '{info['tool']}' repeated without progress.\n"
        f"{info['message']}"
    )
    try:
        parsed = json.loads(content)
    except Exception:
        return content + warning

    if not isinstance(parsed, dict):
        return content + warning

    for key, value in info.items():
        parsed[key] = value

    if isinstance(parsed.get("output"), str):
        parsed["output"] += warning
    elif isinstance(parsed.get("error"), str):
        parsed["error"] += warning
    else:
        parsed["loop_detector_warning"] = warning.strip()
    return json.dumps(parsed, ensure_ascii=False)


__all__ = ["LoopDetectionResult", "LoopDetector"]
