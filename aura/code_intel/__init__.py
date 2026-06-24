# Import adapters to trigger registration
from aura.code_intel import python_adapter, text_adapter  # noqa: F401

from aura.code_intel.adapter import (  # isort: skip
    ADAPTER_REGISTRY,
    CodeIntelAdapter,
    get_adapter,
    register_adapter,
)
from aura.code_intel.audit import audit_changed_files
from aura.code_intel.index import CodeIntelIndex
from aura.code_intel.models import (
    AuditFinding,
    FileInfo,
    ParseDiagnostic,
    ReferenceEdge,
    SymbolInfo,
)

__all__ = [
    "ADAPTER_REGISTRY",
    "AuditFinding",
    "CodeIntelAdapter",
    "CodeIntelIndex",
    "FileInfo",
    "ParseDiagnostic",
    "ReferenceEdge",
    "SymbolInfo",
    "audit_changed_files",
    "get_adapter",
    "register_adapter",
]
