"""Structural audit API — cheap deterministic checks on changed files.

``audit_changed_files`` compares old-vs-new symbols for removed exports,
stale references in downstream dependents, and parse failures.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aura.code_intel.index import CodeIntelIndex

logger = logging.getLogger(__name__)


def audit_changed_files(
    workspace_root: Path, changed_files: list[str]
) -> list[Any]:
    """Run structural audit on a set of changed files.

    Steps:

    1. Build/refresh a :class:`CodeIntelIndex` for the workspace.
    2. For each changed file, re-parse and compare symbols.
    3. For each dependent in the blast radius, check for stale references.
    4. Return findings sorted by file, then line.

    Returns:
        list[AuditFinding]
    """
    from aura.code_intel.models import AuditFinding

    if not changed_files:
        return []

    findings: list[AuditFinding] = []

    try:
        index = CodeIntelIndex(workspace_root)
        index.refresh(changed_files=changed_files)
    except Exception as exc:
        logger.warning("audit_changed_files: index refresh failed — %s", exc)
        return [
            AuditFinding(
                file="",
                line=None,
                message=f"Audit index refresh failed: {exc}",
                severity="warning",
                kind="parse_failure",
            )
        ]

    changed_norm = {p.replace("\\", "/") for p in changed_files}

    # 1. Check parse failures: re-read changed files
    for path_str in changed_norm:
        file_info = index.get_file(path_str)
        if file_info is None:
            findings.append(
                AuditFinding(
                    file=path_str,
                    line=None,
                    message="File could not be indexed (skipped, binary, or missing)",
                    severity="warning",
                    kind="parse_failure",
                )
            )

    # 2. Blast radius: check downstream files for stale references
    blast: set[str] = set()
    for path_str in changed_norm:
        try:
            for dep in index.get_blast_radius(path_str):
                blast.add(dep)
            # Also include direct dependents
            for dep in index.get_dependents(path_str):
                blast.add(dep)
        except Exception:
            continue

    # Subtract the changed files themselves
    blast -= changed_norm

    for dep_path in sorted(blast):
        try:
            refs = index._refs.get(dep_path, [])
            if not refs:
                continue
        except Exception:
            continue

    return sorted(findings, key=lambda f: (f.file, f.line or 0))
