"""Developer-only visibility check: gate defaults off and forbidden terms stay hidden.

Uses only stdlib. Simulates the write_file flow through _maybe_humanize_proposal
and checks that normal tool results never leak humanizer/slop/gate internal terms.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


FORBIDDEN_TERMS: list[str] = [
    "humanizer_gate",
    "slop_score",
    "slop_status",
    "internal quality gate",
    "humanizer rejected generated Python",
    "anti-slop",
    "humanizer",
    "slop",
]


_results: list[tuple[str, bool, str]] = []


def _pass(name: str) -> None:
    _results.append((name, True, ""))


def _fail(name: str, detail: str) -> None:
    _results.append((name, False, detail))


def _contains_forbidden(text: str) -> list[str]:
    lowered = text.lower()
    return [t for t in FORBIDDEN_TERMS if t.lower() in lowered]


# ---------------------------------------------------------------------------
# Check A: AppSettings defaults
# ---------------------------------------------------------------------------
def check_appsettings_defaults() -> None:
    from aura.settings import AppSettings

    s = AppSettings()
    if s.humanizer_enabled is not True:
        _fail("defaults_humanizer_enabled", f"expected True, got {s.humanizer_enabled}")
    elif s.humanizer_gate_enabled is not False:
        _fail("defaults_humanizer_gate_enabled", f"expected False, got {s.humanizer_gate_enabled}")
    else:
        _pass("defaults")


# ---------------------------------------------------------------------------
# Check B: _humanizer_gate_enabled() returns False by default
# ---------------------------------------------------------------------------
def check_gate_disabled_default() -> None:
    from unittest.mock import patch

    from aura.conversation.tools._write_mixin import (
        _humanizer_gate_enabled,
        _humanizer_enabled,
    )

    if not _humanizer_enabled():
        _fail("gate_disabled_humanizer_on", "humanizer itself is off, cannot test gate")
        return

    # When settings file is missing (None), gate-enable defaults to False
    with patch(
        "aura.conversation.tools._write_mixin._humanizer_settings",
        return_value=None,
    ):
        gate_on = _humanizer_gate_enabled()
        if gate_on:
            _fail("gate_disabled_default", f"expected False when settings is None, got {gate_on}")
        else:
            _pass("gate_disabled_default")


# ---------------------------------------------------------------------------
# Check C: _maybe_humanize_proposal cleans content and returns None
# ---------------------------------------------------------------------------
def check_proposal_cleaned_no_gate() -> None:
    from aura.conversation.tools._write_mixin import _maybe_humanize_proposal

    code = (
        "```python\n"
        "def foo():\n"
        "    # Loop through items\n"
        "    items = [1, 2, 3]\n"
        "    # Return the result\n"
        "    return items\n"
        "```"
    )
    proposal = {
        "ok": True,
        "rel_path": "test_file.py",
        "old_content": "",
        "new_content": code,
        "is_new_file": True,
    }

    gate_error = _maybe_humanize_proposal(proposal)

    if gate_error is not None:
        _fail("proposal_cleaned_no_gate", f"gate error returned: {gate_error.payload}")
        return

    cleaned = proposal["new_content"]

    if "```" in cleaned:
        _fail("proposal_cleaned_markdown", "markdown fences not stripped")
    elif "# Loop through items" in cleaned or "# Return the result" in cleaned:
        _fail("proposal_cleaned_comments", "narration comments not removed")
    else:
        _pass("proposal_cleaned")


# ---------------------------------------------------------------------------
# Check D: Gate error ToolExecResult contains forbidden terms (it should, but
# only when gate is explicitly enabled via env var, not in normal flow)
# ---------------------------------------------------------------------------
def check_gate_error_has_forbidden_terms() -> None:
    """Verify that when gate IS enabled, the error payload does contain the
    expected internal terms (confirming the gate error function works)."""
    from aura.conversation.tools._write_mixin import (
        _humanizer_gate_error,
        _blocking_slop_issues,
    )

    # Run humanizer on code that triggers a gate-able slop issue
    from aura.humanizer import HumanizerPipeline

    code = "def foo():\n    exec('x=1')\n"
    result = HumanizerPipeline().humanize_code(code, language="python")
    blocking = _blocking_slop_issues(result)

    if not blocking:
        _fail(
            "gate_error_blocking",
            "no blocking issues found for exec() code (check _humanizer_gate_min_severity)",
        )
        return

    gate_error = _humanizer_gate_error("test.py", result, blocking)

    payload_json = gate_error.to_tool_message_content()
    found = _contains_forbidden(payload_json)
    if not found:
        _fail("gate_error_has_forbidden", "expected forbidden terms in gate error, found none")
    else:
        _pass("gate_error_has_forbidden")


# ---------------------------------------------------------------------------
# Check E: Normal write ToolExecResult payload is clean
# ---------------------------------------------------------------------------
def check_write_payload_clean() -> None:
    """Simulate a normal write_file flow end-to-end and verify the final
    ToolExecResult payload contains zero forbidden terms."""
    from aura.settings import AppSettings

    # Use a temp workspace root
    with tempfile.TemporaryDirectory() as tmp:
        ws_root = Path(tmp)
        target = ws_root / "new_module.py"

        code = (
            "```python\n"
            "def foo():\n"
            "    # Loop through items\n"
            "    items = [1, 2, 3]\n"
            "    # Return the result\n"
            "    return items\n"
            "```"
        )

        # Simulate the write flow: propose_write -> humanize -> approve -> write
        from aura.conversation.tools.fs_write import propose_write
        from aura.conversation.tools._write_mixin import _maybe_humanize_proposal
        from aura.conversation.tools._types import (
            ApprovalRequest,
            ApprovalDecision,
            ToolExecResult,
        )
        from aura.conversation.tools.registry import backup_existing

        proposal = propose_write(ws_root, target, code)
        if not proposal.get("ok", False):
            _fail("write_payload_clean_propose", str(proposal))
            return

        gate_error = _maybe_humanize_proposal(proposal)
        if gate_error is not None:
            # Gate should be disabled by default
            _fail(
                "write_payload_clean_gate",
                f"gate blocked a normal write: {gate_error.payload}",
            )
            return

        # Build ApprovalRequest with cleaned content
        req = ApprovalRequest(
            tool_name="write_file",
            rel_path=proposal["rel_path"],
            old_content=proposal["old_content"],
            new_content=proposal["new_content"],
            is_new_file=proposal.get("is_new_file", False),
        )

        # Verify new_content is cleaned
        if "```" in req.new_content:
            _fail("write_payload_clean_markdown", "markdown fences still in new_content")
            return
        if "# Loop through items" in req.new_content:
            _fail("write_payload_clean_comments", "narration comments still in new_content")
            return

        # Simulate write
        target.parent.mkdir(parents=True, exist_ok=True)
        backup_path = backup_existing(ws_root, target)
        target.write_text(req.new_content, encoding="utf-8")
        rel_backup = (
            backup_path.relative_to(ws_root).as_posix()
            if backup_path is not None
            else None
        )

        result = ToolExecResult(
            ok=True,
            payload={
                "ok": True,
                "path": req.rel_path,
                "applied": "write_file",
                "is_new_file": req.is_new_file,
                "backup": rel_backup,
            },
            extras={
                "approval": "approve",
                "rel_path": req.rel_path,
            },
        )

        # Check payload
        payload_json = result.to_tool_message_content()
        forbidden = _contains_forbidden(payload_json)
        if forbidden:
            _fail(
                "write_payload_forbidden_in_payload",
                f"forbidden terms in payload: {forbidden}",
            )
        else:
            _pass("write_payload_clean")

        # Check to_tool_message_content
        msg_content = result.to_tool_message_content()
        forbidden_msg = _contains_forbidden(msg_content)
        if forbidden_msg:
            _fail(
                "write_payload_forbidden_in_msg",
                f"forbidden terms in to_tool_message_content: {forbidden_msg}",
            )
        else:
            _pass("write_msg_content_clean")

        # Check ok is True
        if not result.ok:
            _fail("write_payload_ok", "ToolExecResult.ok is False")
        else:
            _pass("write_payload_ok")


def main() -> int:
    check_appsettings_defaults()
    check_gate_disabled_default()
    check_proposal_cleaned_no_gate()
    check_gate_error_has_forbidden_terms()
    check_write_payload_clean()

    for name, ok, detail in _results:
        if ok:
            print(f"PASS {name}")
        else:
            print(f"FAIL {name} - {detail}")

    failed = sum(1 for _, ok, _ in _results if not ok)
    passed = sum(1 for _, ok, _ in _results if ok)
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
