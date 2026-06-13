from __future__ import annotations

import json
from pathlib import Path

from aura.conversation.history import History
from aura.conversation.manager import ConversationManager
from aura.conversation.tools.registry import ToolRegistry


def test_failed_transaction_returns_typed_blocker_without_recovery_roulette(tmp_workspace):
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
        write_attempts_by_path={},
    )

    payload = json.loads(updated)
    assert payload["failure_class"] == "edit_transaction_symbol_not_found"
    assert payload["recoverable"] is False
    assert "edit_line_range" not in payload.get("suggested_next_action", "")


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
        write_attempts_by_path={},
    )

    payload = json.loads(updated)
    assert payload["recoverable"] is False
    assert "patch_file" in payload["suggested_next_action"]
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
        write_attempts_by_path={},
    )

    assert blocked is not None
    payload = json.loads(blocked["result_payload"])
    assert payload["failure_class"] == "edit_transaction_ambiguous_symbol"
    assert payload["recoverable"] is False
    assert payload["suggested_next_tool"] == "patch_file"
    assert "occurrence" in payload["suggested_next_action"]
    assert "allow_multiple" in payload["suggested_next_action"]
    assert "edit_line_range" not in payload["suggested_next_action"]


def test_syntax_repair_recovery_steers_to_patch_not_line_range(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    syntax_repair = {"broken.py": {"error": "SyntaxError"}}

    # read_file is always allowed during syntax repair
    blocked = manager._worker_recovery_block(
        tool_call_id="tc1",
        name="read_file",
        args={"path": "other.py"},
        edit_failed_shapes=set(),
        edit_fallback_required={},
        recovery_block_counts={},
        line_range_reread_required={},
        syntax_repair_required=syntax_repair,
        syntax_validation_required=set(),
        write_attempts_by_path={},
    )
    assert blocked is None

    # write_file with unrelated path is blocked during syntax repair
    blocked = manager._worker_recovery_block(
        tool_call_id="tc2",
        name="write_file",
        args={"path": "other.py"},
        edit_failed_shapes=set(),
        edit_fallback_required={},
        recovery_block_counts={},
        line_range_reread_required={},
        syntax_repair_required=syntax_repair,
        syntax_validation_required=set(),
        write_attempts_by_path={},
    )
    assert blocked is not None
    payload = json.loads(blocked["result_payload"])
    assert payload["failure_class"] == "syntax_invalid"
    assert payload["suggested_next_tool"] == "patch_file"
    assert payload["suggested_next_tool"] != "edit_line_range"
    assert "edit_line_range" not in payload["suggested_next_action"]
    assert "patch_file" in payload["suggested_next_action"]

    # non-py_compile run_terminal_command is blocked during syntax repair
    blocked = manager._worker_recovery_block(
        tool_call_id="tc3",
        name="run_terminal_command",
        args={"command": "echo hello"},
        edit_failed_shapes=set(),
        edit_fallback_required={},
        recovery_block_counts={},
        line_range_reread_required={},
        syntax_repair_required=syntax_repair,
        syntax_validation_required=set(),
        write_attempts_by_path={},
    )
    assert blocked is not None
    payload = json.loads(blocked["result_payload"])
    assert payload["failure_class"] == "syntax_invalid"


def test_syntax_repair_allows_targeted_py_compile(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))

    assert manager._syntax_repair_tool_allowed(
        "run_terminal_command",
        {"command": "python -m py_compile database.py"},
        {"database.py"},
    )


def test_syntax_repair_allows_python3_py_compile(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))

    assert manager._syntax_repair_tool_allowed(
        "run_terminal_command",
        {"command": "python3 -m py_compile ./pkg/database.py"},
        {"pkg/database.py"},
    )


def test_syntax_repair_blocks_unrelated_terminal_commands(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))

    # pytest with no specific file matching syntax_paths is still blocked
    assert not manager._syntax_repair_tool_allowed(
        "run_terminal_command",
        {"command": "python -m pytest tests"},
        {"database.py"},
    )
    # pytest referencing a file whose name matches a syntax_path IS now allowed
    assert manager._syntax_repair_tool_allowed(
        "run_terminal_command",
        {"command": "python -m pytest tests/test_database.py"},
        {"database.py"},
    )
    # echo is not an allowed terminal command
    assert not manager._syntax_repair_tool_allowed(
        "run_terminal_command",
        {"command": "echo py_compile database.py"},
        {"database.py"},
    )


def test_syntax_repair_py_compile_path_normalization(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))

    assert manager._syntax_repair_tool_allowed(
        "run_terminal_command",
        {"command": "python -m py_compile ./database.py"},
        {"database.py"},
    )
    assert manager._syntax_repair_tool_allowed(
        "run_terminal_command",
        {"command": r"python -m py_compile .\pkg\database.py"},
        {"pkg/database.py"},
    )


def test_successful_py_compile_clears_normalized_syntax_state(tmp_workspace):
    (tmp_workspace / "database.py").write_text("")
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    syntax_repair_required = {"./database.py": {"error": "SyntaxError"}}
    syntax_validation_required = {r".\database.py"}

    manager._update_syntax_state_from_terminal(
        args={"command": "python -m py_compile database.py"},
        loop_info={
            "_terminal_payload": {
                "ok": True,
                "command": "python -m py_compile database.py",
                "output": "",
            }
        },
        syntax_repair_required=syntax_repair_required,
        syntax_validation_required=syntax_validation_required,
    )

    assert syntax_repair_required == {}
    assert syntax_validation_required == set()


def test_failed_py_compile_records_normalized_syntax_path(tmp_workspace):
    (tmp_workspace / "database.py").write_text("")
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    syntax_repair_required = {}
    syntax_validation_required = set()

    manager._update_syntax_state_from_terminal(
        args={"command": "python -m py_compile ./database.py"},
        loop_info={
            "_terminal_payload": {
                "ok": False,
                "command": "python -m py_compile ./database.py",
                "output": "SyntaxError: invalid syntax",
            }
        },
        syntax_repair_required=syntax_repair_required,
        syntax_validation_required=syntax_validation_required,
    )

    assert set(syntax_repair_required) == {"database.py"}
    assert syntax_repair_required["database.py"]["error"] == "SyntaxError: invalid syntax"
    assert syntax_validation_required == set()


def test_patch_file_failure_requires_reread_before_retry(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    fallback_required = {
        "sample.py": {
            "failure_class": "patch_hunk_not_found",
            "error": "patch_file hunk old block was not found.",
        }
    }

    blocked = manager._worker_recovery_block(
        tool_call_id="tc1",
        name="patch_file",
        args={"path": "sample.py", "edits": [{"old": "missing", "new": "value"}]},
        edit_failed_shapes=set(),
        edit_fallback_required=fallback_required,
        recovery_block_counts={},
        line_range_reread_required={},
        syntax_repair_required={},
        syntax_validation_required=set(),
        write_attempts_by_path={},
    )

    assert blocked is not None
    payload = json.loads(blocked["result_payload"])
    assert payload["suggested_next_tool"] == "read_file"
    assert "retry patch_file once" in payload["suggested_next_action"]

    manager._record_reads_for_recovery(
        "read_file",
        {"path": "sample.py"},
        {"ok": True, "path": "sample.py", "truncated": False},
        {},
        fallback_required,
    )

    assert fallback_required == {}
    unblocked = manager._worker_recovery_block(
        tool_call_id="tc2",
        name="patch_file",
        args={"path": "sample.py", "edits": [{"old": "current", "new": "value"}]},
        edit_failed_shapes=set(),
        edit_fallback_required=fallback_required,
        recovery_block_counts={},
        line_range_reread_required={},
        syntax_repair_required={},
        syntax_validation_required=set(),
        write_attempts_by_path={},
    )
    assert unblocked is None


def test_patch_file_failure_reread_clears_normalized_path(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    fallback_required = {
        "pkg/sample.py": {
            "failure_class": "patch_hunk_not_found",
            "error": "patch_file hunk old block was not found.",
        }
    }
    line_range_required = {
        "pkg/lines.py": {
            "failure_class": "edit_mechanics_stale_line_range",
            "error": "stale range",
        }
    }

    manager._record_reads_for_recovery(
        "read_file",
        {"path": r".\pkg\sample.py"},
        {"ok": True, "path": r".\pkg\sample.py", "truncated": False},
        line_range_required,
        fallback_required,
    )
    manager._record_reads_for_recovery(
        "read_file",
        {"path": "./pkg/lines.py"},
        {"ok": True, "path": "./pkg/lines.py", "truncated": False},
        line_range_required,
        fallback_required,
    )

    assert fallback_required == {}
    assert line_range_required == {}


def test_shell_failure_with_cd_prefix_does_not_trigger_syntax_repair(tmp_workspace):
    """Shell-level failures (cd /workspace not found) should NOT set syntax_repair_required."""
    (tmp_workspace / "database.py").write_text("dummy content")
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    syntax_repair_required = {}
    syntax_validation_required = set()

    manager._update_syntax_state_from_terminal(
        args={"command": "cd /workspace && python -m py_compile database.py"},
        loop_info={
            "_terminal_payload": {
                "ok": False,
                "command": "cd /workspace && python -m py_compile database.py",
                "output": "The system cannot find the path specified.",
            }
        },
        syntax_repair_required=syntax_repair_required,
        syntax_validation_required=syntax_validation_required,
    )

    assert syntax_repair_required == {}


def test_real_py_compile_syntax_error_still_triggers_syntax_repair(tmp_workspace):
    """Real Python syntax errors should still set syntax_repair_required."""
    (tmp_workspace / "database.py").write_text("invalid syntax here")
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    syntax_repair_required = {}
    syntax_validation_required = set()

    manager._update_syntax_state_from_terminal(
        args={"command": "python -m py_compile database.py"},
        loop_info={
            "_terminal_payload": {
                "ok": False,
                "command": "python -m py_compile database.py",
                "output": 'File "database.py", line 1\n    invalid syntax here\n         ^^^^^\nSyntaxError: invalid syntax',
            }
        },
        syntax_repair_required=syntax_repair_required,
        syntax_validation_required=syntax_validation_required,
    )

    assert "database.py" in syntax_repair_required
    assert syntax_repair_required["database.py"]["error"] is not None


def test_cd_wrapper_is_stripped_from_terminal_command(tmp_workspace):
    """The _CD_WRAPPER_RE regex correctly strips cd/chdir prefixes from commands."""
    from aura.conversation.tool_runner import _CD_WRAPPER_RE

    cases = [
        ("cd /workspace && python -m py_compile database.py",
         "python -m py_compile database.py"),
        ("cd /workspace ; python -m py_compile database.py",
         "python -m py_compile database.py"),
        ("chdir /workspace && python -m py_compile database.py",
         "python -m py_compile database.py"),
        ("cd frontend && npm test",
         "cd frontend && npm test"),
    ]
    for raw, expected in cases:
        result = _CD_WRAPPER_RE.sub('', raw, count=1).lstrip()
        assert result == expected, f"Failed on {raw!r}: got {result!r}"


def test_syntax_repair_allows_focused_pytest(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))

    assert manager._syntax_repair_tool_allowed(
        "run_terminal_command",
        {"command": "python -m pytest tests/test_database.py"},
        {"database.py"},
    )


def test_syntax_repair_blocks_broad_pytest(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))

    assert not manager._syntax_repair_tool_allowed(
        "run_terminal_command",
        {"command": "python -m pytest tests"},
        {"database.py"},
    )


def test_stale_validation_note_on_passing_py_compile(tmp_workspace):
    (tmp_workspace / "database.py").write_text("x = 1")
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    syntax_repair_required = {
        "database.py": {"awaiting_validation": False, "failed_repairs": 1}
    }
    syntax_validation_required = set()
    stale_notes: list[str] = []

    manager._update_syntax_state_from_terminal(
        args={"command": "python -m py_compile database.py"},
        loop_info={
            "_terminal_payload": {
                "ok": True,
                "command": "python -m py_compile database.py",
                "output": "",
            }
        },
        syntax_repair_required=syntax_repair_required,
        syntax_validation_required=syntax_validation_required,
        stale_validation_notes=stale_notes,
    )

    assert len(stale_notes) == 1
    assert "Stale validation cleared" in stale_notes[0]
    assert "database.py" in stale_notes[0]
    assert syntax_repair_required == {}


def test_read_only_tools_available_after_syntax_failure(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))

    for tool in (
        "read_file",
        "read_files",
        "grep_search",
        "read_file_outline",
        "search_codebase",
        "find_usages",
        "glob",
        "list_directory",
    ):
        assert manager._syntax_repair_tool_allowed(
            tool,
            {"path": "any.py"},
            {"broken.py"},
        ), f"{tool} should be allowed during syntax repair"


def test_patch_file_allowed_for_broken_file_after_syntax_failure(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))

    assert manager._syntax_repair_tool_allowed(
        "patch_file",
        {"path": "broken.py"},
        {"broken.py"},
    )
    # Unrelated path is still blocked
    assert not manager._syntax_repair_tool_allowed(
        "patch_file",
        {"path": "other.py"},
        {"broken.py"},
    )


def test_py_compile_allowed_for_broken_file_after_syntax_failure(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))

    assert manager._syntax_repair_tool_allowed(
        "run_terminal_command",
        {"command": "python -m py_compile broken.py"},
        {"broken.py"},
    )
    # Non-py_compile terminal command is still blocked
    assert not manager._syntax_repair_tool_allowed(
        "run_terminal_command",
        {"command": "echo hello"},
        {"broken.py"},
    )


def test_workspace_root_updates_propagate_to_tool_runner(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    assert manager._tool_runner._workspace_root == tmp_workspace

    new_root = Path("/different/path")
    manager.set_workspace_root(new_root)
    assert manager._tool_runner._workspace_root == new_root


def test_patch_file_hash_mismatch_is_recoverable_fallback(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    edit_fallback_required: dict = {}
    line_range_reread_required: dict = {}
    content = json.dumps({
        "ok": False,
        "path": "sample.py",
        "failure_class": "patch_file_hash_mismatch",
        "error": "patch_file hash mismatch — re-read and retry",
    })

    updated = manager._update_worker_recovery_state(
        name="patch_file",
        args={"path": "sample.py", "edits": [{"old": "x", "new": "y"}]},
        ok=False,
        content=content,
        edit_failed_shapes=set(),
        edit_fallback_required=edit_fallback_required,
        line_range_reread_required=line_range_reread_required,
        syntax_repair_required={},
        syntax_validation_required=set(),
        write_attempts_by_path={},
    )

    payload = json.loads(updated)
    assert payload["failure_class"] == "patch_file_hash_mismatch"
    assert payload["recoverable"] is True
    assert payload["suggested_next_tool"] == "patch_file"
    assert "sample.py" in edit_fallback_required
    assert "sample.py" not in line_range_reread_required


def test_recovery_state_not_cleared_by_failed_or_truncated_read(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    edit_fallback_required = {"x.py": {"failure_class": "patch_hunk_not_found"}}

    # Failed read — state NOT cleared
    manager._record_reads_for_recovery(
        "read_file",
        {"path": "x.py"},
        {"ok": False, "path": "x.py", "truncated": False},
        {},
        edit_fallback_required,
    )
    assert edit_fallback_required != {}

    # Truncated read — state NOT cleared
    manager._record_reads_for_recovery(
        "read_file",
        {"path": "x.py"},
        {"ok": True, "path": "x.py", "truncated": True},
        {},
        edit_fallback_required,
    )
    assert edit_fallback_required != {}

    # Successful non-truncated read — state IS cleared
    manager._record_reads_for_recovery(
        "read_file",
        {"path": "x.py"},
        {"ok": True, "path": "x.py", "truncated": False},
        {},
        edit_fallback_required,
    )
    assert edit_fallback_required == {}


def test_successful_read_clears_patch_recovery_state(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    edit_fallback_required = {"sample.py": {"failure_class": "patch_hunk_not_found"}}

    manager._record_reads_for_recovery(
        "read_file",
        {"path": "sample.py"},
        {"ok": True, "path": "sample.py", "truncated": False},
        {},
        edit_fallback_required,
    )

    assert edit_fallback_required == {}


def test_repeated_patch_file_block_becomes_nonrecoverable(tmp_workspace):
    manager = ConversationManager(History(), ToolRegistry(tmp_workspace, mode="worker"))
    edit_fallback_required = {
        "f.py": {
            "failure_class": "patch_hunk_not_found",
            "error": "patch_file hunk old block was not found.",
        }
    }
    recovery_block_counts = {"patch-reread:f.py": 2}

    blocked = manager._worker_recovery_block(
        tool_call_id="tc1",
        name="patch_file",
        args={"path": "f.py", "edits": [{"old": "x", "new": "y"}]},
        edit_failed_shapes=set(),
        edit_fallback_required=edit_fallback_required,
        recovery_block_counts=recovery_block_counts,
        line_range_reread_required={},
        syntax_repair_required={},
        syntax_validation_required=set(),
        write_attempts_by_path={},
    )

    assert blocked is not None
    payload = json.loads(blocked["result_payload"])
    assert payload["recoverable"] is False