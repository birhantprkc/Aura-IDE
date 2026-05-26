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


def test_ambiguous_replace_text_once_is_nonrecoverable_with_specific_guidance(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    content = json.dumps(
        {
            "ok": False,
            "path": "sample.py",
            "failure_class": "edit_transaction_ambiguous_symbol",
            "error": "replace_text_once old text is ambiguous",
            "occurrence_count": 2,
        }
    )

    updated = manager._update_worker_recovery_state(
        name="apply_edit_transaction",
        args={
            "path": "sample.py",
            "operations": [
                {"op": "replace_text_once", "old": "value", "new": "changed"}
            ],
        },
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
    assert payload["recoverable"] is False
    assert "structured symbol operation" in payload["suggested_next_action"]
    assert "occurrence" in payload["suggested_next_action"]
    assert "allow_multiple" in payload["suggested_next_action"]
    assert "edit_line_range" not in payload["suggested_next_action"]


def test_repeated_ambiguous_replace_text_once_shape_is_blocked(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    args = {
        "path": "sample.py",
        "operations": [
            {"op": "replace_text_once", "old": "value", "new": "changed"}
        ],
    }
    shape = manager._edit_shape_signature("apply_edit_transaction", args)

    blocked = manager._worker_recovery_block(
        tool_call_id="tc1",
        name="apply_edit_transaction",
        args=args,
        edit_failed_shapes={shape, f"ambiguous-replace-text:{shape}"},
        edit_fallback_required={},
        recovery_block_counts={},
        line_range_reread_required={},
        syntax_repair_required={},
        syntax_validation_required=set(),
        compiler_repair_required={},
        write_attempts_by_path={},
    )

    assert blocked is not None
    payload = json.loads(blocked["result_payload"])
    assert payload["failure_class"] == "edit_transaction_ambiguous_symbol"
    assert payload["recoverable"] is False
    assert payload["suggested_next_tool"] == "apply_edit_transaction"
    assert "occurrence" in payload["suggested_next_action"]
    assert "allow_multiple" in payload["suggested_next_action"]
    assert "edit_line_range" not in payload["suggested_next_action"]


def test_syntax_repair_recovery_steers_to_transaction_not_line_range(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))

    blocked = manager._worker_recovery_block(
        tool_call_id="tc1",
        name="read_file",
        args={"path": "other.py"},
        edit_failed_shapes=set(),
        edit_fallback_required={},
        recovery_block_counts={},
        line_range_reread_required={},
        syntax_repair_required={"broken.py": {"error": "SyntaxError"}},
        syntax_validation_required=set(),
        compiler_repair_required={},
        write_attempts_by_path={},
    )

    assert blocked is not None
    payload = json.loads(blocked["result_payload"])
    assert payload["failure_class"] == "syntax_invalid"
    assert payload["suggested_next_tool"] == "apply_edit_transaction"
    assert payload["suggested_next_tool"] != "edit_line_range"
    assert "edit_line_range" not in payload["suggested_next_action"]
    assert "patch_file" not in payload["suggested_next_action"]
