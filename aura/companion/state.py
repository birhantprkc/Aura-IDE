"""CompanionState — plain dataclass for CompanionManager's non-Qt state."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CompanionState:
    """Mutable state for CompanionManager, extracted from the QObject.

    No PySide, no Qt, no methods beyond what @dataclass provides.
    """

    current_project_id: str = ""
    current_conversation_id: str = ""
    conversation_loaded: bool = False
    pending_select_msg: dict | None = None
    pending_chat_id: str = ""
    pending_chat_phone_id: str = ""
    current_pairing_code: str = ""
    paired_context: dict = field(default_factory=dict)
    paired_project_name: str = ""
    active_relay_url: str = ""
    workspace_root: str = ""
