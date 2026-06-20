"""Safety caps — what the Gardener may touch, and how much."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


RUNTIME_SKIP: frozenset[str] = frozenset({
    "drones/folder_runner.py",
    "drones/background_runner.py",
    "drones/sync_runner.py",
    "drones/store.py",
    "drones/definition.py",
    "drones/receipt.py",
    "drones/run.py",
    "drones/runner.py",
    "drones/workshop_runner.py",
})


@dataclass(frozen=True)
class Appetite:
    max_files: int = 1
    max_changed_lines: int = 20
    allow_file_deletion: bool = False


def is_editable(rel_path: str) -> bool:
    """Return False if *rel_path* (forward-slash, relative to aura/) is protected."""
    normalised = rel_path.replace("\\", "/")
    return normalised not in RUNTIME_SKIP


def within_budget(
    diff_line_count: int,
    files_touched: int,
    appetite: Appetite,
) -> tuple[bool, str]:
    if files_touched > appetite.max_files:
        return False, f"files_touched {files_touched} > max_files {appetite.max_files}"
    if diff_line_count > appetite.max_changed_lines:
        return False, f"diff_lines {diff_line_count} > max_changed_lines {appetite.max_changed_lines}"
    return True, ""
