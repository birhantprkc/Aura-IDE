from __future__ import annotations

import hashlib
from pathlib import Path

from aura.conversation.path_utils import normalize_worker_path


def fingerprint_paths(paths: set[str], workspace_root) -> str:
    if not paths:
        return ""

    root = Path(workspace_root)
    try:
        resolved_root = root.resolve()
    except OSError:
        resolved_root = root
    entries: list[tuple[str, str]] = []
    for raw_path in paths:
        normalized = normalize_worker_path(raw_path)
        candidate = Path(normalized)
        full_path = candidate if candidate.is_absolute() else root / normalized
        if not full_path.exists():
            continue
        try:
            content_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
        except OSError:
            continue
        try:
            relative_path = full_path.resolve().relative_to(resolved_root).as_posix()
        except (OSError, ValueError):
            relative_path = normalized
        entries.append((relative_path, content_hash))

    if not entries:
        return ""

    digest = hashlib.sha256()
    for relative_path, content_hash in sorted(entries):
        digest.update(relative_path.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()
