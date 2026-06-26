"""Focused tests for worker_recovery_messages constants."""

from __future__ import annotations

from aura.conversation.worker_recovery_messages import (
    PATCH_CANDIDATE_INVALID_SYNTAX_ACTION,
    WORKER_AUTO_PY_COMPILE_INSTRUCTION,
    WORKER_DEPENDENT_CONTRACT_INSTRUCTION,
    WORKER_EDIT_RECOVERY_INSTRUCTION,
    WORKER_IMPORT_FAILURE_INSTRUCTION,
    WORKER_LAUNCH_FAILURE_INSTRUCTION,
)


def test_all_constants_are_non_empty() -> None:
    """Every exported constant is a non-empty string."""
    assert isinstance(PATCH_CANDIDATE_INVALID_SYNTAX_ACTION, str) and len(PATCH_CANDIDATE_INVALID_SYNTAX_ACTION) > 0
    assert isinstance(WORKER_EDIT_RECOVERY_INSTRUCTION, str) and len(WORKER_EDIT_RECOVERY_INSTRUCTION) > 0
    assert isinstance(WORKER_AUTO_PY_COMPILE_INSTRUCTION, str) and len(WORKER_AUTO_PY_COMPILE_INSTRUCTION) > 0
    assert isinstance(WORKER_IMPORT_FAILURE_INSTRUCTION, str) and len(WORKER_IMPORT_FAILURE_INSTRUCTION) > 0
    assert isinstance(WORKER_DEPENDENT_CONTRACT_INSTRUCTION, str) and len(WORKER_DEPENDENT_CONTRACT_INSTRUCTION) > 0
    assert isinstance(WORKER_LAUNCH_FAILURE_INSTRUCTION, str) and len(WORKER_LAUNCH_FAILURE_INSTRUCTION) > 0


def test_format_placeholders_present() -> None:
    """Templates that use .format() have the correct placeholders."""
    # Auto-py-compile uses {diagnostics}
    WORKER_AUTO_PY_COMPILE_INSTRUCTION.format(diagnostics="test diag")
    # Import failure uses {diagnostics}
    WORKER_IMPORT_FAILURE_INSTRUCTION.format(diagnostics="test diag")
    # Dependent contract uses all three
    WORKER_DEPENDENT_CONTRACT_INSTRUCTION.format(
        edited_files="a.py",
        dependent_files="b.py",
        diagnostics="test diag",
    )
    # Launch failure uses {command} and {output}
    WORKER_LAUNCH_FAILURE_INSTRUCTION.format(
        command="python -m test",
        output="test output",
    )
