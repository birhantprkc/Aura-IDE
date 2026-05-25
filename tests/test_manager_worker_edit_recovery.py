from __future__ import annotations

import json

from aura.conversation.history import History
from aura.conversation.manager import ConversationManager
from aura.conversation.tools.registry import ToolRegistry


def test_failed_transaction_returns_typed_blocker_without_patch_steering(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    content = json.dumps(
        {
            "ok": False,
            "path": "sample.py",
            "failure_class": "edit_transaction_symbol_not_found",
            "error": "Function 'missing' not found",
        }
    )

    updated = manager._update_worker_recovery_state(
        name="apply_edit_transaction",
        args={"path": "sample.py", "operations": [{"op": "replace_function", "symbol_name": "missing"}]},
        ok=False,
        content=content,
        edit_failed_shapes=set(),
        edit_fallback_required={},
        line_range_reread_required={},
        syntax_repair_required={},
        syntax_validation_required=set(),
        compiler_repair_required={},
        write_attempts_by_path={},
    )

    payload = json.loads(updated)
    assert payload["failure_class"] == "edit_transaction_symbol_not_found"
    assert payload["recoverable"] is False
    assert payload.get("suggested_next_tool") != "patch_file"
    assert "patch_file" not in payload.get("suggested_next_action", "")
