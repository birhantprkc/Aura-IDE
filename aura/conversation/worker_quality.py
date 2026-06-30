from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from aura.code_intel.audit import audit_changed_files

QualitySeverity = Literal["info", "warning", "error"]

DUPLICATE_STRING_MIN_LENGTH = 16
LARGE_DIFF_LINE_THRESHOLD = 400
PROTECTED_CONTROL_FLOW_FILES = frozenset({
    "manager.py",
    "dispatch.py",
    "worker_flow.py",
})

_CONTROL_FLOW_RE = re.compile(
    r"^\s*(?:if|elif|else|for|while|try|except|finally|with|return|raise|break|continue|match|case)\b"
    r"|^\s*else\s*:",
)
_DOUBLE_QUOTED_RE = re.compile(r'(?:[rRuUbBfF]{0,3})"((?:\\.|[^"\\])*)"')
_SINGLE_QUOTED_RE = re.compile(r"(?:[rRuUbBfF]{0,3})'((?:\\.|[^'\\])*)'")


@dataclass
class QualityFinding:
    kind: str
    severity: QualitySeverity
    file: str
    line: int | None
    message: str
    suggested_action: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerQualityDecision:
    ok: bool
    hard_block: bool
    needs_cleanup: bool
    findings: list[QualityFinding]
    instruction: str = ""


@dataclass
class _DiffFile:
    path: str
    added: list[tuple[int | None, str]] = field(default_factory=list)
    removed: list[tuple[int | None, str]] = field(default_factory=list)
    new_file: bool = False

    @property
    def changed_line_count(self) -> int:
        return len(self.added) + len(self.removed)


def evaluate_worker_quality(
    workspace_root: Path,
    changed_files: list[str],
    diff_text: str,
    validation_passed: bool,
) -> WorkerQualityDecision:
    normalized_files = _normalize_changed_files(changed_files)
    findings: list[QualityFinding] = []

    for audit_finding in audit_changed_files(Path(workspace_root), normalized_files):
        severity = _coerce_severity(getattr(audit_finding, "severity", "warning"))
        if severity not in {"warning", "error"}:
            continue
        kind = str(getattr(audit_finding, "kind", "audit"))
        file = str(getattr(audit_finding, "file", ""))
        line = getattr(audit_finding, "line", None)
        findings.append(
            QualityFinding(
                kind=kind,
                severity=severity,
                file=file,
                line=line if isinstance(line, int) else None,
                message=str(getattr(audit_finding, "message", "")),
                suggested_action=_audit_suggested_action(kind, severity),
                evidence={
                    "source": "audit_changed_files",
                    "validation_passed": validation_passed,
                },
            )
        )

    diff_files = _parse_unified_diff(diff_text)
    findings.extend(_duplicate_changed_string_findings(diff_files))
    findings.extend(_large_diff_findings(diff_files))
    findings.extend(_protected_control_flow_findings(diff_files))

    hard_block = any(f.severity == "error" for f in findings)
    needs_cleanup = any(f.severity == "warning" for f in findings)
    instruction = ""
    if needs_cleanup and not hard_block:
        instruction = _cleanup_instruction(findings)
    return WorkerQualityDecision(
        ok=not hard_block and not needs_cleanup,
        hard_block=hard_block,
        needs_cleanup=needs_cleanup,
        findings=findings,
        instruction=instruction,
    )


def findings_to_receipt(findings: list[QualityFinding]) -> list[dict[str, Any]]:
    return [asdict(finding) for finding in findings]


def _normalize_changed_files(changed_files: list[str]) -> list[str]:
    return sorted({
        str(path).replace("\\", "/").lstrip("/")
        for path in changed_files
        if str(path).strip()
    })


def _coerce_severity(value: str) -> QualitySeverity:
    if value == "error":
        return "error"
    if value == "info":
        return "info"
    return "warning"


def _audit_suggested_action(kind: str, severity: QualitySeverity) -> str:
    if kind == "removed_export" and severity == "error":
        return "Restore the removed public symbol or update all importers before final release."
    if kind == "removed_export":
        return "Confirm the removal is intentional and update any same-file references."
    if kind == "stale_reference":
        return "Update the stale reference or restore the referenced symbol."
    if kind == "parse_failure":
        return "Fix the parse failure and rerun the focused validation command."
    if kind == "unresolved_dependency":
        return "Fix the import path or add the missing workspace dependency."
    return "Patch the reported audit finding and rerun the focused validation command."


def _cleanup_instruction(findings: list[QualityFinding]) -> str:
    lines = [
        "Do not redesign.",
        "Do not broaden scope.",
        "Patch only the listed findings.",
        "Preserve behavior.",
        "Rerun the smallest relevant validation.",
        "Finish only after it passes.",
        "",
        "Findings:",
    ]
    for finding in findings:
        if finding.severity != "warning":
            continue
        location = finding.file or "<workspace>"
        if finding.line is not None:
            location = f"{location}:{finding.line}"
        lines.append(
            f"- {location} - {finding.message} - {finding.suggested_action}"
        )
    return "\n".join(lines)


def _parse_unified_diff(diff_text: str) -> dict[str, _DiffFile]:
    files: dict[str, _DiffFile] = {}
    current: _DiffFile | None = None
    next_removed_line: int | None = None
    next_added_line: int | None = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            current = None
            next_removed_line = None
            next_added_line = None
            parts = raw_line.split()
            if len(parts) >= 4:
                path = parts[3]
                if path.startswith("b/"):
                    path = path[2:]
                current = files.setdefault(path, _DiffFile(path=path))
            continue
        if current is None:
            continue
        if raw_line == "new file mode" or raw_line.startswith("new file mode "):
            current.new_file = True
            continue
        if raw_line.startswith("--- /dev/null"):
            current.new_file = True
            continue
        if raw_line.startswith("+++ "):
            path = raw_line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            if path and path != "/dev/null" and path != current.path:
                files.pop(current.path, None)
                current.path = path
                files[path] = current
            continue
        if raw_line.startswith("@@"):
            next_removed_line = _parse_hunk_start(raw_line, "-")
            next_added_line = _parse_hunk_added_start(raw_line)
            continue
        if raw_line.startswith("+++") or raw_line.startswith("---"):
            continue
        if raw_line.startswith("+"):
            text = raw_line[1:]
            current.added.append((next_added_line, text))
            if next_added_line is not None:
                next_added_line += 1
            continue
        if raw_line.startswith("-"):
            text = raw_line[1:]
            current.removed.append((next_removed_line, text))
            if next_removed_line is not None:
                next_removed_line += 1
            continue
        if raw_line.startswith(" "):
            if next_removed_line is not None:
                next_removed_line += 1
            if next_added_line is not None:
                next_added_line += 1

    return files


def _parse_hunk_added_start(line: str) -> int | None:
    return _parse_hunk_start(line, "+")


def _parse_hunk_start(line: str, prefix: str) -> int | None:
    match = re.search(rf"\{prefix}(\d+)(?:,\d+)?", line)
    if not match:
        return None
    return int(match.group(1))


def _duplicate_changed_string_findings(diff_files: dict[str, _DiffFile]) -> list[QualityFinding]:
    by_literal: dict[str, dict[str, list[int | None]]] = {}
    for path, diff_file in diff_files.items():
        for line_number, text in diff_file.added:
            for literal in _string_literals(text):
                stripped = literal.strip()
                if len(stripped) < DUPLICATE_STRING_MIN_LENGTH:
                    continue
                by_literal.setdefault(stripped, {}).setdefault(path, []).append(line_number)

    findings: list[QualityFinding] = []
    for literal, file_lines in sorted(by_literal.items()):
        if len(file_lines) < 2:
            continue
        files = sorted(file_lines)
        preview = literal[:80]
        line = _first_line(file_lines)
        findings.append(
            QualityFinding(
                kind="duplicate_changed_string",
                severity="warning",
                file=", ".join(files),
                line=line,
                message=(
                    "Same newly added string literal appears in multiple changed files: "
                    + ", ".join(files)
                ),
                suggested_action=(
                    "Replace the duplicated literal with an existing shared constant or "
                    "leave one local copy only if the repetition is intentional."
                ),
                evidence={
                    "literal_preview": preview,
                    "files": files,
                    "line_numbers": file_lines,
                },
            )
        )
    return findings


def _string_literals(text: str) -> list[str]:
    literals: list[str] = []
    for regex in (_DOUBLE_QUOTED_RE, _SINGLE_QUOTED_RE):
        literals.extend(match.group(1) for match in regex.finditer(text))
    return literals


def _first_line(file_lines: dict[str, list[int | None]]) -> int | None:
    for line in sorted(
        (line for lines in file_lines.values() for line in lines if line is not None)
    ):
        return line
    return None


def _large_diff_findings(diff_files: dict[str, _DiffFile]) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    for path, diff_file in sorted(diff_files.items()):
        if diff_file.new_file:
            continue
        changed_count = diff_file.changed_line_count
        if changed_count <= LARGE_DIFF_LINE_THRESHOLD:
            continue
        findings.append(
            QualityFinding(
                kind="large_diff_whole_file_rewrite",
                severity="warning",
                file=path,
                line=None,
                message=(
                    f"Changed line count is {changed_count}, above the "
                    f"{LARGE_DIFF_LINE_THRESHOLD} line review threshold."
                ),
                suggested_action=(
                    "Narrow the patch or confirm the broad rewrite is required by the task."
                ),
                evidence={
                    "added_lines": len(diff_file.added),
                    "removed_lines": len(diff_file.removed),
                    "threshold": LARGE_DIFF_LINE_THRESHOLD,
                },
            )
        )
    return findings


def _protected_control_flow_findings(diff_files: dict[str, _DiffFile]) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    for path, diff_file in sorted(diff_files.items()):
        if Path(path).name not in PROTECTED_CONTROL_FLOW_FILES:
            continue
        touched = [
            (line_number, text)
            for line_number, text in [*diff_file.added, *diff_file.removed]
            if _CONTROL_FLOW_RE.search(text)
        ]
        if not touched:
            continue
        line, text = touched[0]
        findings.append(
            QualityFinding(
                kind="protected_file_controlflow",
                severity="warning",
                file=path,
                line=line,
                message=f"Control flow changed in protected file {path}.",
                suggested_action=(
                    "Review the branch change against the requested task and keep the smallest valid patch."
                ),
                evidence={
                    "protected_files": sorted(PROTECTED_CONTROL_FLOW_FILES),
                    "line_text": text.strip(),
                },
            )
        )
    return findings
