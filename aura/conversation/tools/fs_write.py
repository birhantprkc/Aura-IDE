"""Approval-gated write tools: write_file, edit_file."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def propose_write(workspace_root: Path, target: Path, content: str) -> dict[str, Any]:
    rel = target.relative_to(workspace_root).as_posix() if target.is_relative_to(workspace_root) else str(target)
    if target.exists() and target.is_file():
        try:
            old_content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            old_content = target.read_bytes().decode("utf-8", errors="replace")
    else:
        old_content = ""
    return {
        "rel_path": rel,
        "old_content": old_content,
        "new_content": content,
        "is_new_file": not target.exists(),
    }


def propose_edit(
    workspace_root: Path, target: Path, old_str: str, new_str: str
) -> dict[str, Any]:
    if not target.exists():
        return {"ok": False, "error": f"file not found: {target.relative_to(workspace_root)}"}
    if not target.is_file():
        return {"ok": False, "error": f"not a regular file: {target.relative_to(workspace_root)}"}
    try:
        original = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"ok": False, "error": "file is not valid UTF-8 text"}
    occurrences = original.count(old_str)
    if occurrences == 0:
        return {
            "ok": False,
            "error": "old_str not found in file. The match must be exact (whitespace included).",
        }
    if occurrences > 1:
        return {
            "ok": False,
            "error": (
                f"old_str matches {occurrences} places in the file. Make it unique by "
                "including more surrounding context."
            ),
        }
    proposed = original.replace(old_str, new_str, 1)
    rel = target.relative_to(workspace_root).as_posix()
    return {
        "ok": True,
        "rel_path": rel,
        "old_content": original,
        "new_content": proposed,
        "is_new_file": False,
    }
