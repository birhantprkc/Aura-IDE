"""Worker recovery state bookkeeping helpers.

Extracted from ConversationManager to keep worker-recovery state
manipulation focused and testable without a manager instance.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aura.conversation.path_utils import normalize_worker_path as _normalize_worker_path


def record_reads_for_recovery(
    name: str,
    args: dict[str, Any],
    parsed: Any,
    line_range_reread_required: dict[str, dict[str, Any]],
    edit_fallback_required: dict[str, dict[str, Any]],
    worker_file_state: dict[str, dict[str, Any]] | None = None,
) -> None:
    if name == "read_file":
        path = str(args.get("path") or (parsed.get("path") if isinstance(parsed, dict) else ""))
        if (
            path
            and isinstance(parsed, dict)
            and parsed.get("ok") is True
            and parsed.get("truncated") is not True
        ):
            recorded = record_worker_file_state(
                worker_file_state,
                path,
                parsed,
                "read_file",
            )
            if recorded:
                pop_normalized_recovery_key(line_range_reread_required, path)
                pop_normalized_recovery_key(edit_fallback_required, path)
    elif name == "read_files":
        files = parsed.get("files") if isinstance(parsed, dict) else None
        if isinstance(files, dict):
            for path_key, result in files.items():
                if not isinstance(result, dict):
                    continue
                path = str(result.get("path") or path_key)
                if result.get("ok") is True and result.get("truncated") is not True:
                    recorded = record_worker_file_state(
                        worker_file_state,
                        path,
                        result,
                        "read_files",
                    )
                    if recorded:
                        pop_normalized_recovery_key(line_range_reread_required, path)
                        pop_normalized_recovery_key(edit_fallback_required, path)
    elif name == "read_file_range":
        path = str(args.get("path") or (parsed.get("path") if isinstance(parsed, dict) else ""))
        if path and isinstance(parsed, dict) and parsed.get("ok") is True:
            recorded = record_worker_file_state(
                worker_file_state,
                path,
                parsed,
                "read_file_range",
            )
            if recorded:
                prior = normalized_state_value(edit_fallback_required, path)
                if (
                    isinstance(prior, dict)
                    and prior.get("failure_class") == "patch_file_hash_mismatch"
                ):
                    pop_normalized_recovery_key(edit_fallback_required, path)


def record_worker_file_state(
    worker_file_state: dict[str, dict[str, Any]] | None,
    path: str,
    result: dict[str, Any],
    tool_name: str,
) -> bool:
    if worker_file_state is None:
        return False
    content_hash = result.get("content_hash")
    file_size = result.get("file_size")
    if not isinstance(content_hash, str) or not content_hash:
        return False
    if not isinstance(file_size, int):
        return False
    normalized = _normalize_worker_path(str(result.get("path") or path))
    worker_file_state[normalized] = {
        "content_hash": content_hash,
        "file_size": file_size,
        "truncated": bool(result.get("truncated", False)),
        "last_read_tool": tool_name,
        "fresh_for_patch": result.get("truncated") is not True,
    }
    return True


def pop_normalized_recovery_key(
    state: dict[str, dict[str, Any]],
    path: str,
) -> None:
    pop_normalized_key(state, path)


def normalized_state_value(
    state: dict[str, Any],
    path: str,
) -> Any:
    normalized = _normalize_worker_path(path)
    if normalized in state:
        return state[normalized]
    for existing_path, value in state.items():
        if _normalize_worker_path(existing_path) == normalized:
            return value
    return None


def pop_normalized_key(
    state: dict[str, Any],
    path: str,
) -> None:
    normalized = _normalize_worker_path(path)
    state.pop(normalized, None)
    for existing_path in list(state):
        if _normalize_worker_path(existing_path) == normalized:
            state.pop(existing_path, None)


def clear_patch_failed_shapes_for_path(
    patch_failed_cycles: dict[str, int],
    path: str,
    parse_patch_shape: Callable[[str], dict[str, Any]],
) -> None:
    normalized = _normalize_worker_path(path)
    for shape in list(patch_failed_cycles):
        parsed = parse_patch_shape(shape)
        shape_path = _normalize_worker_path(str(parsed.get("path") or ""))
        if shape_path == normalized:
            patch_failed_cycles.pop(shape, None)
