from __future__ import annotations

import hashlib
from pathlib import Path

from aura.conversation.tools._types import ApprovalDecision
from aura.conversation.tools.fs_edit_transaction import propose_edit_transaction
from aura.conversation.tools.registry import TOOL_HANDLERS, ToolRegistry


def _approve(_req):
    return ApprovalDecision(action="approve")


def test_multi_operation_one_file_python_edit_succeeds_through_one_transaction(tmp_workspace: Path):
    target = tmp_workspace / "sample.py"
    target.write_text(
        "def alpha():\n"
        "    return 1\n"
        "\n"
        "class Greeter:\n"
        "    def greet(self):\n"
        "        return 'hi'\n",
        encoding="utf-8",
    )
    registry = ToolRegistry(tmp_workspace, mode="worker")

    result = TOOL_HANDLERS["apply_edit_transaction"](
        registry,
        {
            "path": "sample.py",
            "operations": [
                {
                    "op": "replace_function",
                    "symbol_name": "alpha",
                    "new_definition": "def alpha():\n    return 2",
                },
                {
                    "op": "replace_method",
                    "class_name": "Greeter",
                    "symbol_name": "greet",
                    "new_definition": "def greet(self):\n    return 'hello'",
                },
                {
                    "op": "insert_after_symbol",
                    "symbol_type": "class",
                    "symbol_name": "Greeter",
                    "content": "\ndef omega():\n    return 3\n",
                },
            ],
        },
        _approve,
        False,
    )

    payload = result.payload
    assert result.ok is True
    assert payload["applied"] == "apply_edit_transaction"
    assert payload["operation_count"] == 3
    content = target.read_text(encoding="utf-8")
    assert "return 2" in content
    assert "return 'hello'" in content
    assert "def omega()" in content


def test_failed_method_replacement_does_not_write_and_returns_symbol_not_found(tmp_workspace: Path):
    target = tmp_workspace / "sample.py"
    original = "class Greeter:\n    def greet(self):\n        return 'hi'\n"
    target.write_text(original, encoding="utf-8")

    proposal = propose_edit_transaction(
        tmp_workspace,
        target,
        [
            {
                "op": "replace_method",
                "class_name": "Greeter",
                "symbol_name": "missing",
                "new_definition": "def missing(self):\n    return 'x'",
            }
        ],
    )

    assert proposal["ok"] is False
    assert proposal["failure_class"] == "edit_transaction_symbol_not_found"
    assert target.read_text(encoding="utf-8") == original


def test_invalid_generated_python_does_not_write_and_returns_invalid_syntax(tmp_workspace: Path):
    target = tmp_workspace / "sample.py"
    original = "def alpha():\n    return 1\n"
    target.write_text(original, encoding="utf-8")

    proposal = propose_edit_transaction(
        tmp_workspace,
        target,
        [{"op": "replace_function", "symbol_name": "alpha", "new_definition": "def alpha(:\n    return 2"}],
    )

    assert proposal["ok"] is False
    assert proposal["failure_class"] == "edit_transaction_invalid_syntax"
    assert target.read_text(encoding="utf-8") == original


def test_stale_expected_file_hash_rejects_without_write(tmp_workspace: Path):
    target = tmp_workspace / "sample.py"
    original = "def alpha():\n    return 1\n"
    target.write_text(original, encoding="utf-8")

    proposal = propose_edit_transaction(
        tmp_workspace,
        target,
        [{"op": "replace_function", "symbol_name": "alpha", "new_definition": "def alpha():\n    return 2"}],
        expected_file_hash=hashlib.sha256(b"stale").hexdigest(),
    )

    assert proposal["ok"] is False
    assert proposal["failure_class"] == "edit_transaction_hash_mismatch"
    assert target.read_text(encoding="utf-8") == original


def test_crlf_input_preserves_crlf_after_transaction(tmp_workspace: Path):
    target = tmp_workspace / "sample.py"
    original = "def alpha():\r\n    return 1\r\n\r\n"
    target.write_bytes(original.encode("utf-8"))
    registry = ToolRegistry(tmp_workspace, mode="worker")

    result = TOOL_HANDLERS["apply_edit_transaction"](
        registry,
        {
            "path": "sample.py",
            "operations": [
                {"op": "replace_function", "symbol_name": "alpha", "new_definition": "def alpha():\n    return 2"}
            ],
        },
        _approve,
        False,
    )

    assert result.ok is True
    written = target.read_bytes().decode("utf-8")
    assert "\r\n" in written
    assert "\n" not in written.replace("\r\n", "")
    assert "\r\r\n" not in written
