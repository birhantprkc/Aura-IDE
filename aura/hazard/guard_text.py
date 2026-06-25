from __future__ import annotations

import logging
from pathlib import Path

from aura.hazard.reader import GraduatedHazard, read_graduated

logger = logging.getLogger(__name__)


def format_guards(hazards: list[GraduatedHazard]) -> str:
    if not hazards:
        return ""
    top = hazards[:5]
    lines = ["### Learned Hazard Guards"]
    for h in top:
        error = h.representative_error or ""
        if len(error) > 200:
            error = error[:200] + "..."
        files = (
            ", ".join(h.sample_target_files[:5])
            if h.sample_target_files
            else "(various files)"
        )
        kind = h.task_kind if h.task_kind else "unknown"
        lines.append(
            f"{h.model} has burned {h.distinct_dispatch_count}\u00d7 on {kind} terrain "
            f"with: {error}. "
            f"This terrain is a known biter; verify the relevant behavior actually runs "
            f"before calling it done. Surfaces in: {files}."
        )
    return "\n".join(lines)


def build_hazard_guard_context(workspace_root: str | Path) -> str:
    """Build optional hazard guard context block.

    Returns empty string on any failure — this is optional context
    that must never propagate into the caller.
    """
    try:
        hazards = read_graduated(workspace_root)
        return format_guards(hazards)
    except Exception:
        logger.debug("Hazard guard context unavailable", exc_info=True)
        return ""
