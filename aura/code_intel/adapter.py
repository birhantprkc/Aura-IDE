from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CodeIntelAdapter(ABC):
    """Language-neutral adapter for code intelligence.

    Subclasses implement per-language parsing, outlining, and reference
    extraction.  New adapters register themselves via `register_adapter()`
    and must be imported at least once for the registry to know about them.
    """

    @property
    @abstractmethod
    def language_id(self) -> str:
        """Return the language id this adapter handles, e.g. 'python', 'typescript', 'text'."""
        ...

    @staticmethod
    @abstractmethod
    def detect(file_path: str, content: str | None = None) -> bool:
        """Return True if this adapter claims the file.

        Use path suffix first, content as fallback.
        """
        ...

    @abstractmethod
    def parse(
        self, file_path: str, content: str
    ) -> tuple[list[Any], list[Any], list[Any]]:
        """Full parse: symbols, references, diagnostics.

        Returns (list[SymbolInfo], list[ReferenceEdge], list[ParseDiagnostic]).
        """
        ...

    @abstractmethod
    def outline(self, file_path: str, content: str) -> dict[str, Any]:
        """Return a structural outline of the file.

        Dict shape::
            {language: str, imports: list[str], classes: list[dict],
             functions: list[dict]}
        """
        ...

    @abstractmethod
    def symbols(self, file_path: str, content: str) -> list[Any]:
        """Return top-level and nested SymbolInfo objects."""
        ...

    @abstractmethod
    def references(self, file_path: str, content: str) -> list[Any]:
        """Return ReferenceEdge objects originating from this file."""
        ...

    @abstractmethod
    def dependencies(self, file_path: str, content: str) -> list[str]:
        """Return list of workspace-relative paths this file depends on (best-effort)."""
        ...


# Module-level registry
ADAPTER_REGISTRY: list[CodeIntelAdapter] = []


def register_adapter(adapter: CodeIntelAdapter) -> None:
    """Register a code-intelligence adapter.

    Adapters are checked in registration order; the *last* registered adapter
    that matches a file wins.  The generic ``text`` adapter should be
    registered last so that it acts as the fallback.
    """
    ADAPTER_REGISTRY.append(adapter)


def get_adapter(file_path: str, content: str | None = None) -> CodeIntelAdapter | None:
    """Return the first adapter that claims the given file, or None."""
    for adapter in ADAPTER_REGISTRY:
        if adapter.detect(file_path, content=content):
            return adapter
    return None
