from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_UNKNOWN_BUILD_ERROR_PLACEHOLDER = "Unknown " + "build error"
_BUILD_FAILURE_WITHOUT_WORKER_DETAIL = (
    "Build failed without an error message from the Worker."
)


def build_failure_error_text(
    *,
    summary: str | None = None,
    status: str | None = None,
    metadata: Any = None,
    exception_text: str | None = None,
    worker_result_detail: Any = None,
    stored_build_result: Any = None,
) -> str:
    """Return the best available user-facing build failure detail."""
    candidates: list[str] = []
    candidates.extend(_failure_candidates_from_any(exception_text))
    candidates.extend(_failure_candidates_from_any(worker_result_detail))
    candidates.extend(_failure_candidates_from_any(metadata))
    candidates.extend(_failure_candidates_from_any(stored_build_result))
    candidates.extend(_failure_candidates_from_any(summary))
    if status_text := _clean_failure_text(status):
        candidates.append(f"Worker status: {status_text}")

    seen: set[str] = set()
    for candidate in candidates:
        text = _clean_failure_text(candidate)
        if not text or text.casefold() == _UNKNOWN_BUILD_ERROR_PLACEHOLDER.casefold():
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        return text
    return _BUILD_FAILURE_WITHOUT_WORKER_DETAIL


def _failure_candidates_from_any(value: Any) -> list[str]:
    if value is None or value is False:
        return []
    if isinstance(value, str):
        text = _clean_failure_text(value)
        return [text] if text else []
    if hasattr(value, "to_tool_payload") and callable(value.to_tool_payload):
        try:
            return _failure_candidates_from_any(value.to_tool_payload())
        except Exception:
            logger.debug("to_tool_payload inspection failed", exc_info=True)
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _failure_candidates_from_any(vars(value))
    if isinstance(value, dict):
        return _failure_candidates_from_mapping(value)
    if isinstance(value, (list, tuple, set)):
        candidates: list[str] = []
        for item in value:
            candidates.extend(_failure_candidates_from_any(item))
        return candidates
    text = _clean_failure_text(value)
    return [text] if text else []


def _failure_candidates_from_mapping(data: dict[str, Any]) -> list[str]:
    candidates: list[str] = []

    extras = data.get("extras")
    if isinstance(extras, dict):
        candidates.extend(_failure_candidates_from_mapping(extras))

    for nested_key in (
        "metadata",
        "worker_result",
        "worker_result_detail",
        "dispatch_result",
        "stored_build_result",
        "build_result",
    ):
        nested = data.get(nested_key)
        if nested is not data:
            candidates.extend(_failure_candidates_from_any(nested))

    for key in (
        "internal_error",
        "exception_text",
        "exception",
        "error",
        "message",
        "detail",
        "reason",
        "validation",
        "summary",
        "result_summary",
    ):
        candidates.extend(_failure_candidates_from_any(data.get(key)))

    for key in ("errors", "api_errors", "caveats"):
        candidates.extend(_failure_candidates_from_any(data.get(key)))

    for key in ("validation_results", "terminal_results"):
        records = data.get(key)
        if isinstance(records, list):
            for record in records:
                formatted = _format_validation_failure(record)
                if formatted:
                    candidates.append(formatted)

    for key in (
        "failed_tool_results",
        "failed_write_tools",
        "not_applied_writes",
        "unrecovered_not_applied_writes",
        "source_inspection_blockers",
        "terminal_policy_blockers",
        "environment_setup_blockers",
    ):
        candidates.extend(_format_tool_failures(data.get(key)))

    phase_boundary = data.get("phase_boundary")
    if isinstance(phase_boundary, dict):
        candidates.extend(_failure_candidates_from_mapping(phase_boundary))

    if status_text := _clean_failure_text(data.get("status")):
        candidates.append(f"Worker status: {status_text}")

    if not candidates and data:
        compact = _compact_json(data)
        if compact:
            candidates.append(f"Worker result detail: {compact}")

    return candidates


def _format_validation_failure(record: Any) -> str:
    if not isinstance(record, dict):
        return ""
    if record.get("ok") is not False:
        return ""
    command = _clean_failure_text(record.get("command"))
    exit_code = record.get("exit_code")
    output = _clean_failure_text(
        record.get("output")
        or record.get("output_preview")
        or record.get("error")
        or record.get("result_preview")
    )
    parts = ["Validation failed"]
    if command:
        parts.append(command)
    if exit_code is not None:
        parts.append(f"exit code {exit_code}")
    if output:
        parts.append(output.splitlines()[0])
    return ": ".join(parts)


def _format_tool_failures(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    formatted: list[str] = []
    for record in value:
        if not isinstance(record, dict):
            formatted.extend(_failure_candidates_from_any(record))
            continue
        name = _clean_failure_text(record.get("name") or record.get("tool"))
        path = _clean_failure_text(record.get("path") or record.get("rel_path"))
        failure_class = _clean_failure_text(record.get("failure_class"))
        error = _clean_failure_text(
            record.get("error")
            or record.get("reason")
            or record.get("result_preview")
        )
        parts: list[str] = []
        if name:
            parts.append(name)
        if path:
            parts.append(path)
        if failure_class:
            parts.append(failure_class)
        if error:
            parts.append(error)
        if parts:
            formatted.append("Tool failure: " + ": ".join(parts))
    return formatted


def _clean_failure_text(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return _compact_json(value)
    text = str(value).strip()
    return " ".join(text.split())


def _compact_json(value: Any) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return text.strip()[:500]
