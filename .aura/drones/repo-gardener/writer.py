"""Safe file writer with revert closure."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def write_with_revert(path: Path, new_content: str) -> Callable[[], None]:
    """Write *new_content* to *path*, keeping original in memory.

    Returns a ``revert()`` closure that restores the original content.
    Call ``revert()`` if verification fails.
    """
    original = path.read_text(encoding="utf-8")
    path.write_text(new_content, encoding="utf-8")

    def revert() -> None:
        path.write_text(original, encoding="utf-8")

    return revert
