"""Structural audit API — cheap deterministic checks on changed files.

Detects parse failures in changed files.  Blast-radius context is computed
for future export/stale-reference checks (not yet implemented).
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

    1. Build/refresh a :class:`CodeIntelIndex` for the workspace (full
       refresh for blast-radius context, then re-parse changed files).
    2. For each changed file, check indexability and emit parse diagnostics.
    3. Compute blast-radius dependents (future use, not yet implemented).
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
        # Full refresh first to build whole-repo context for blast radius
        index.refresh()
        # Then re-parse changed files specifically
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

    # 1. Check parse failures and diagnostics for changed files
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
        else:
            # Report any parse diagnostics for this file
            for diag in index.get_diagnostics(path_str):
                findings.append(
                    AuditFinding(
                        file=diag.file or path_str,
                        line=diag.line,
                        message=diag.message,
                        severity=diag.severity or "warning",
                        kind="parse_failure",
                    )
                )

    # 2. Compute blast radius for future export/stale-reference checks
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

    return sorted(findings, key=lambda f: (f.file, f.line or 0))
