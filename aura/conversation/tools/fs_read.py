"""Read-only filesystem tools: read_file, list_directory, glob."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aura.config import MAX_GLOB_RESULTS, MAX_READ_BYTES, SKIP_DIRS, SKIP_FILE_SUFFIXES


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return True
    if path.name.startswith("."):
        return True
    if path.suffix in SKIP_FILE_SUFFIXES:
        return True
    return False


def read_file(workspace_root: Path, target: Path) -> dict[str, Any]:
    if not target.exists():
        return {"ok": False, "error": f"file not found: {target.relative_to(workspace_root)}"}
    if not target.is_file():
        return {"ok": False, "error": f"not a regular file: {target.relative_to(workspace_root)}"}
    raw = target.read_bytes()
    truncated = False
    if len(raw) > MAX_READ_BYTES:
        raw = raw[:MAX_READ_BYTES]
        truncated = True
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    if truncated:
        text += f"\n\n[... truncated at {MAX_READ_BYTES} bytes ...]"
    rel = target.relative_to(workspace_root).as_posix()
    return {"ok": True, "path": rel, "content": text, "truncated": truncated}


def list_directory(workspace_root: Path, target: Path) -> dict[str, Any]:
    if not target.exists():
        return {"ok": False, "error": f"not found: {target.relative_to(workspace_root)}"}
    if not target.is_dir():
        return {"ok": False, "error": f"not a directory: {target.relative_to(workspace_root)}"}
    files: list[str] = []
    dirs: list[str] = []
    for entry in sorted(target.iterdir()):
        if entry.name.startswith(".") or entry.name in SKIP_DIRS:
            continue
        if entry.is_dir():
            dirs.append(entry.name + "/")
        elif entry.suffix in SKIP_FILE_SUFFIXES:
            continue
        else:
            files.append(entry.name)
    rel = target.relative_to(workspace_root).as_posix() or "."
    return {"ok": True, "path": rel, "directories": dirs, "files": files}


def glob_files(workspace_root: Path, pattern: str) -> dict[str, Any]:
    matches: list[str] = []
    for p in workspace_root.rglob(pattern):
        if _should_skip(p.relative_to(workspace_root)):
            continue
        if p.is_file():
            matches.append(p.relative_to(workspace_root).as_posix())
        if len(matches) >= MAX_GLOB_RESULTS:
            break
    return {
        "ok": True,
        "pattern": pattern,
        "matches": matches,
        "truncated": len(matches) >= MAX_GLOB_RESULTS,
    }
