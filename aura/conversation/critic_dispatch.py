from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from aura.client import Done
from aura.conversation.critic_verdict import CriticFinding, CriticVerdict
from aura.conversation.dispatch import WorkerDispatchRequest
from aura.hooks import hooks

CriticCallback = Callable[[str, "CriticRequest"], CriticVerdict]

_EDIT_TOOL_NAMES = {
    "write_file",
    "patch_file",
    "delete_file",
    "run_terminal_command",
    "run_and_watch",
    "summon_drone",
}

CRITIC_SYSTEM_PROMPT = """You are Aura's dispatch critic.

Judge whether the worker's unified diff conforms to the planner's WorkerDispatchRequest.
Return only one strict JSON object with this shape:
{"conforms": true|false, "route": "release"|"worker"|"planner", "findings": [{"clause": "...", "file": "...", "message": "...", "suggested_action": "..."}], "instruction": "...", "planner_question": "..."}

Rules:
- Every finding must cite a concrete request clause in "clause"; omit vague concerns with no clause.
- Use route "worker" when the request is achievable and the worker missed it.
- Use route "planner" only when the request is conflicting, impossible, or needs a planner/product decision.
- Use route "release" when the diff conforms or the request lacks a concrete clause to judge.
- Do not propose broad redesigns. Do not mention this critic.
"""


@dataclass
class CriticRequest:
    original_request: WorkerDispatchRequest
    diff_text: str
    deterministic_findings: list[CriticFinding] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.diff_text = str(self.diff_text or "")
        if not self.deterministic_findings:
            self.deterministic_findings = deterministic_critic_findings(
                self.original_request,
                self.diff_text,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_request": self.original_request.to_dict(),
            "diff_text": self.diff_text,
            "deterministic_findings": [
                finding.to_dict() for finding in self.deterministic_findings
            ],
        }


def evaluate_deterministic_critic_request(request: CriticRequest) -> CriticVerdict | None:
    if not request.deterministic_findings:
        return None
    return CriticVerdict(
        conforms=False,
        route="worker",
        findings=list(request.deterministic_findings),
        instruction=_worker_instruction_from_findings(request.deterministic_findings),
    )


def deterministic_critic_findings(
    request: WorkerDispatchRequest,
    diff_text: str,
) -> list[CriticFinding]:
    added_text = _added_diff_text(diff_text)
    findings: list[CriticFinding] = []

    for symbol in request.expected_public_symbols:
        expected = str(symbol or "").strip()
        if not expected:
            continue
        if _contains_identifier(added_text, expected):
            continue
        findings.append(
            CriticFinding(
                clause=f"expected_public_symbols: {expected}",
                file=_first_request_file(request),
                message=f"Expected public symbol '{expected}' is not present in the worker diff.",
                suggested_action=(
                    f"Add or expose the requested public symbol '{expected}', or report why it cannot be done."
                ),
            )
        )

    for forbidden in [*request.forbidden_calls, *request.forbidden_public_methods]:
        item = str(forbidden or "").strip()
        if not item:
            continue
        if not _contains_forbidden_reference(added_text, item):
            continue
        findings.append(
            CriticFinding(
                clause=f"forbidden_calls/forbidden_public_methods: {item}",
                file=_first_request_file(request),
                message=f"Worker diff introduces forbidden reference '{item}'.",
                suggested_action=f"Remove '{item}' and use an allowed implementation path.",
            )
        )

    return findings


def run_critic_dispatch(
    tool_call_id: str,
    request: CriticRequest,
    *,
    model: Any,
    thinking: Any,
    temperature: float = 0.0,
    hook_name: str = "generate_worker_code",
    cancel_event: threading.Event | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> CriticVerdict:
    deterministic = evaluate_deterministic_critic_request(request)
    if deterministic is not None:
        return deterministic

    safe_tools = _without_edit_tools(tools or [])
    messages = _critic_messages(request)
    final_message: dict[str, Any] | None = None
    try:
        for ev in hooks.trigger(
            hook_name,
            messages=messages,
            tools=safe_tools,
            model=model,
            thinking=thinking,
            cancel_event=cancel_event or threading.Event(),
            temperature=temperature,
        ):
            if isinstance(ev, Done):
                final_message = ev.full_message
    except Exception:
        return CriticVerdict.release()

    content = ""
    if isinstance(final_message, dict):
        content = str(final_message.get("content") or "")
    return parse_critic_verdict(content)


def parse_critic_verdict(content: str) -> CriticVerdict:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = _strip_markdown_fence(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return CriticVerdict.release()
    return CriticVerdict.from_dict(parsed)


def _critic_messages(request: CriticRequest) -> list[dict[str, str]]:
    payload = {
        "worker_dispatch_request": request.original_request.to_dict(),
        "worker_unified_diff": request.diff_text,
    }
    return [
        {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def _worker_instruction_from_findings(findings: list[CriticFinding]) -> str:
    lines = [
        "Patch only the critic conformance findings.",
        "Do not redesign.",
        "Preserve behavior outside the cited clauses.",
        "Rerun the smallest relevant validation.",
        "",
        "Findings:",
    ]
    for finding in findings:
        location = finding.file or "<workspace>"
        lines.append(
            f"- {location} - {finding.clause}: {finding.message} - {finding.suggested_action}"
        )
    return "\n".join(lines)


def _added_diff_text(diff_text: str) -> str:
    lines: list[str] = []
    for line in str(diff_text or "").splitlines():
        if line.startswith("+++") or not line.startswith("+"):
            continue
        lines.append(line[1:])
    return "\n".join(lines)


def _contains_identifier(text: str, identifier: str) -> bool:
    if not identifier:
        return False
    escaped = re.escape(identifier)
    return bool(re.search(rf"(?<![\w.]){escaped}(?![\w.])", text))


def _contains_forbidden_reference(text: str, reference: str) -> bool:
    if not reference:
        return False
    if "(" in reference or "." in reference:
        return reference in text
    escaped = re.escape(reference)
    return bool(re.search(rf"(?<![\w.]){escaped}\s*\(", text))


def _first_request_file(request: WorkerDispatchRequest) -> str:
    return str(request.files[0]) if request.files else ""


def _without_edit_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe_tools: list[dict[str, Any]] = []
    for tool in tools:
        function = tool.get("function") if isinstance(tool, dict) else None
        name = str(function.get("name") or "") if isinstance(function, dict) else ""
        if name in _EDIT_TOOL_NAMES:
            continue
        safe_tools.append(tool)
    return safe_tools


def _strip_markdown_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


__all__ = [
    "CRITIC_SYSTEM_PROMPT",
    "CriticCallback",
    "CriticRequest",
    "deterministic_critic_findings",
    "evaluate_deterministic_critic_request",
    "parse_critic_verdict",
    "run_critic_dispatch",
]
