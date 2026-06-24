"""Generic text / fallback code-intelligence adapter.

Uses regex patterns for structural outlines.  Registered last so it serves as
the catch-all for files no other adapter claims.
"""

from __future__ import annotations

import re
from typing import Any

from aura.code_intel.adapter import CodeIntelAdapter, register_adapter

_GENERIC_CLASS_RE = re.compile(
    r"^(class|struct|interface|trait|enum)\s+\w+", re.IGNORECASE
)
_GENERIC_FUNC_RE = re.compile(
    r"^(def|func|function|fn|sub|void|public|private|protected|static)\s+\w+\s*\(",
    re.IGNORECASE,
)
_GENERIC_IMPORT_RE = re.compile(
    r"^(import|use|include|require|from)\s", re.IGNORECASE
)


class TextAdapter(CodeIntelAdapter):
    """Catch-all adapter for any UTF-8 text file.

    Provides conservative regex-based outlines.  Cross-file reference
    resolution is not attempted.
    """

    @property
    def language_id(self) -> str:
        return "text"

    @staticmethod
    def detect(file_path: str, content: str | None = None) -> bool:
        """Accept any file that has no more specific adapter."""
        return True

    def parse(
        self, file_path: str, content: str
    ) -> tuple[list[Any], list[Any], list[Any]]:
        symbols = self.symbols(file_path, content)
        return (symbols, [], [])

    def outline(self, file_path: str, content: str) -> dict[str, Any]:
        lines = content.splitlines()
        return _outline_lines(lines)

    def symbols(self, file_path: str, content: str) -> list[Any]:
        # Avoid circular import at module level
        from aura.code_intel.models import SymbolInfo

        lines = content.splitlines()
        result: list[SymbolInfo] = []

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if _GENERIC_CLASS_RE.match(stripped):
                parts = stripped.split()
                name = parts[1] if len(parts) > 1 else stripped
                result.append(SymbolInfo(name=name, kind="class", file=file_path, line=i))
            elif _GENERIC_FUNC_RE.match(stripped):
                name = (
                    stripped.split("(")[0].split()[-1]
                    if "(" in stripped
                    else stripped.split()[-1]
                )
                result.append(
                    SymbolInfo(name=name, kind="function", file=file_path, line=i)
                )

        return result

    def references(self, file_path: str, content: str) -> list[Any]:
        return []

    def dependencies(self, file_path: str, content: str) -> list[str]:
        return []


def _outline_lines(lines: list[str]) -> dict[str, Any]:
    """Regex-based outline shared with fs_read.py's generic outline."""
    imports: list[str] = []
    classes: list[dict[str, Any]] = []
    functions: list[dict[str, Any]] = []

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue

        if _GENERIC_IMPORT_RE.match(stripped):
            imports.append(stripped)
        elif _GENERIC_CLASS_RE.match(stripped):
            parts = stripped.split()
            name = parts[1] if len(parts) > 1 else stripped
            classes.append({"name": name, "line": i, "bases": [], "methods": []})
        elif _GENERIC_FUNC_RE.match(stripped):
            sig = stripped.rstrip("{").strip()
            name = (
                stripped.split("(")[0].split()[-1]
                if "(" in stripped
                else stripped.split()[-1]
            )
            functions.append({"name": name, "line": i, "signature": sig})

    return {
        "language": "unknown",
        "imports": imports,
        "classes": classes,
        "functions": functions,
    }


# Register last so it acts as the fallback
register_adapter(TextAdapter())
