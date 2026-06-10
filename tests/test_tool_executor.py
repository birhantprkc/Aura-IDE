"""Tests for ToolExecutor dispatch logic."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aura.conversation.tools._types import ApprovalDecision, ToolExecResult
from aura.conversation.tools.dynamic_registry import DynamicToolRegistry
from aura.conversation.tools.executor import ToolExecutor
from aura.conversation.tools.mcp_registry import MCPToolRegistry
from aura.sandbox import SandboxResult


class FakeOwner:
    """Minimal owner for ToolExecutor with a workspace_root attribute."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root


class TestToolExecutor:
    """Tests for ToolExecutor dispatch priority and error handling."""

    @pytest.fixture
    def owner(self, tmp_workspace: Path) -> FakeOwner:
        return FakeOwner(tmp_workspace)

    @pytest.fixture
    def dynamic_tools(self, tmp_workspace: Path) -> DynamicToolRegistry:
        return DynamicToolRegistry(tmp_workspace)

    @pytest.fixture
    def mcp_tools(self) -> MCPToolRegistry:
        return MCPToolRegistry()

    @pytest.fixture
    def executor(self, owner, dynamic_tools, mcp_tools) -> ToolExecutor:
        return ToolExecutor(
            owner=owner,
            dynamic_tools=dynamic_tools,
            mcp_tools=mcp_tools,
        )

    @pytest.fixture(autouse=True)
    def _cleanup_handlers(self):
        """Clean up TOOL_HANDLERS keys added during this test."""
        from aura.conversation.tools.registry import TOOL_HANDLERS
        before = set(TOOL_HANDLERS.keys())
        yield
        after = set(TOOL_HANDLERS.keys())
        for key in after - before:
            del TOOL_HANDLERS[key]

    def test_dispatches_to_static_handler(self, executor):
        """Static TOOL_HANDLERS take priority over MCP and dynamic tools."""
        from aura.conversation.tools.registry import TOOL_HANDLERS

        called = []

        def handler(self, args, approval_cb, reject_all):
            called.append(args)
            return ToolExecResult(ok=True, payload={"ok": True})

        TOOL_HANDLERS["test_static"] = handler

        result = executor.execute("test_static", {"x": 1}, None)
        assert result.ok is True
        assert called == [{"x": 1}]

    def test_dispatches_to_mcp_when_no_static_handler(self, executor, mcp_tools):
        """When no static handler exists, MCP tools are tried next."""
        with patch("aura.conversation.tools.mcp_registry.MCPClient") as mock_cls:
            from tests.test_mcp_tool_registry import FakeMCPClient

            fake_tools = [
                {"name": "test_mcp_tool", "description": "A test MCP tool",
                 "inputSchema": {"type": "object", "properties": {}}},
            ]
            mock_client = FakeMCPClient(fake_tools)
            mock_cls.return_value = mock_client

            mcp_tools.connect_server("python fake_server.py")

        result = executor.execute("test_mcp_tool", {"a": 1}, None)
        assert result.ok is True
        assert "called test_mcp_tool" in str(result.payload)

    def test_dispatches_to_dynamic_tool(self, executor, tmp_workspace: Path):
        """When no static or MCP handler exists, dynamic tools are tried."""
        tools_dir = tmp_workspace / ".aura" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "test_dynamic.py").write_text(
            "def test_dynamic(x: int) -> dict:\n"
            '    """A dynamic tool.\n\n'
            "    Args:\n"
            "        x: A number.\n"
            '    """\n'
            '    return {"ok": True, "result": x * 2}\n'
        )

        mock_res = SandboxResult(ok=True, stdout='{"ok": true, "result": 10}', stderr="", exit_code=0)
        with patch("aura.sandbox.SandboxExecutor.run_dynamic_tool", return_value=mock_res):
            result = executor.execute("test_dynamic", {"x": 5}, None)

        assert result.ok is True
        assert result.payload["result"] == 10


    def test_unknown_tool_returns_error(self, executor):
        """Unknown tool names return ok=False with an error message."""
        result = executor.execute("nonexistent_tool", {}, None)
        assert result.ok is False
        assert "unknown tool" in result.payload.get("error", "")

    def test_value_error_from_handler_returns_error(self, executor):
        """ValueError from a handler is caught and returned as ok=False."""
        from aura.conversation.tools.registry import TOOL_HANDLERS

        def handler(self, args, approval_cb, reject_all):
            raise ValueError("bad input")

        TOOL_HANDLERS["test_bad"] = handler

        result = executor.execute("test_bad", {}, None)
        assert result.ok is False
        assert "bad input" in result.payload.get("error", "")

    def test_os_error_from_handler_returns_error(self, executor):
        """OSError from a handler is caught and returned as ok=False."""
        from aura.conversation.tools.registry import TOOL_HANDLERS

        def handler(self, args, approval_cb, reject_all):
            raise OSError("file not found")

        TOOL_HANDLERS["test_oserr"] = handler

        result = executor.execute("test_oserr", {}, None)
        assert result.ok is False
        assert "file not found" in result.payload.get("error", "")


class TestIsConsequential:
    """Tests for the is_consequential heuristic."""

    def test_observational_returns_false(self):
        from aura.conversation.tools.consequential import is_consequential
        assert is_consequential("read_file") is False
        assert is_consequential("list_directory") is False
        assert is_consequential("get_status") is False
        assert is_consequential("search_codebase") is False
        assert is_consequential("find_usages") is False
        assert is_consequential("check_health") is False
        assert is_consequential("show_config") is False
        assert is_consequential("diff_working_tree") is False
        assert is_consequential("log_events") is False

    def test_side_effecting_returns_true(self):
        from aura.conversation.tools.consequential import is_consequential
        assert is_consequential("send_message") is True
        assert is_consequential("delete_record") is True
        assert is_consequential("create_user") is True
        assert is_consequential("write_data") is True
        assert is_consequential("update_config") is True
        assert is_consequential("remove_item") is True
        assert is_consequential("exec_command") is True
        assert is_consequential("push_changes") is True
        assert is_consequential("deploy_app") is True

    def test_unrecognized_verb_defaults_to_consequential(self):
        from aura.conversation.tools.consequential import is_consequential
        assert is_consequential("bizarre_unknown_verb") is True
        assert is_consequential("custom_action") is True
        assert is_consequential("run_my_script") is True


class TestMCPApproval:
    """Tests for MCP tool approval via executor dispatch."""

    @pytest.fixture
    def owner(self, tmp_workspace: Path) -> FakeOwner:
        return FakeOwner(tmp_workspace)

    @pytest.fixture
    def dynamic_tools(self, tmp_workspace: Path) -> DynamicToolRegistry:
        return DynamicToolRegistry(tmp_workspace)

    @pytest.fixture
    def mcp_tools(self) -> MCPToolRegistry:
        return MCPToolRegistry()

    @pytest.fixture
    def executor(self, owner, dynamic_tools, mcp_tools) -> ToolExecutor:
        return ToolExecutor(
            owner=owner,
            dynamic_tools=dynamic_tools,
            mcp_tools=mcp_tools,
        )

    @pytest.fixture(autouse=True)
    def _cleanup_handlers(self):
        """Clean up TOOL_HANDLERS keys added during this test."""
        from aura.conversation.tools.registry import TOOL_HANDLERS
        before = set(TOOL_HANDLERS.keys())
        yield
        after = set(TOOL_HANDLERS.keys())
        for key in after - before:
            del TOOL_HANDLERS[key]

    def _register_mcp_tool(self, mcp_tools, name: str):
        """Helper to register a single MCP tool."""
        with patch("aura.conversation.tools.mcp_registry.MCPClient") as mock_cls:
            from tests.test_mcp_tool_registry import FakeMCPClient
            fake_tools = [
                {"name": name, "description": f"MCP tool for {name}",
                 "inputSchema": {"type": "object", "properties": {}}},
            ]
            mock_client = FakeMCPClient(fake_tools)
            mock_cls.return_value = mock_client
            mcp_tools.connect_server("python fake_server.py")
            return mock_client

    def test_consequential_mcp_triggers_approval_and_approve_executes(self, executor, mcp_tools):
        """MCP tool with consequential name triggers approval_cb; approve executes."""
        self._register_mcp_tool(mcp_tools, "send_message")

        calls = []
        def approval_cb(req):
            calls.append(req)
            return ApprovalDecision(action="approve")

        result = executor.execute("send_message", {"text": "hello"}, approval_cb)
        assert result.ok is True
        assert len(calls) == 1
        assert calls[0].tool_name == "send_message"
        assert calls[0].rel_path == "mcp:send_message"

    def test_consequential_mcp_rejected_does_not_execute(self, executor, mcp_tools):
        """MCP consequential tool with approval_cb returning reject does NOT call_tool."""
        mock_client = self._register_mcp_tool(mcp_tools, "delete_record")

        calls = []
        call_tool_calls = 0
        original = mock_client.call_tool
        def tracking_call_tool(name, args):
            nonlocal call_tool_calls
            call_tool_calls += 1
            return original(name, args)
        mock_client.call_tool = tracking_call_tool

        def approval_cb(req):
            calls.append(req)
            return ApprovalDecision(action="reject")

        result = executor.execute("delete_record", {"id": 1}, approval_cb)
        assert result.ok is False
        assert result.payload.get("rejected") is True
        assert len(calls) == 1
        assert call_tool_calls == 0

    def test_consequential_mcp_reject_all_returns_rejected(self, executor, mcp_tools):
        """MCP consequential tool with reject_all=True returns rejected without executing."""
        self._register_mcp_tool(mcp_tools, "delete_record")

        result = executor.execute("delete_record", {}, None, reject_all=True)
        assert result.ok is False
        assert result.payload.get("rejected") is True

    def test_observational_mcp_bypasses_approval(self, executor, mcp_tools):
        """MCP tool with observational name bypasses approval and executes directly."""
        self._register_mcp_tool(mcp_tools, "read_data")

        calls = []
        def approval_cb(req):
            calls.append(req)
            return ApprovalDecision(action="approve")

        result = executor.execute("read_data", {}, approval_cb)
        assert result.ok is True
        assert len(calls) == 0

    def test_unknown_mcp_defaults_to_consequential(self, executor, mcp_tools):
        """MCP tool with unrecognised verb defaults to consequential (fail-safe)."""
        self._register_mcp_tool(mcp_tools, "run_my_script")

        calls = []
        def approval_cb(req):
            calls.append(req)
            return ApprovalDecision(action="approve")

        result = executor.execute("run_my_script", {}, approval_cb)
        assert result.ok is True
        assert len(calls) == 1


class TestDynamicToolApproval:
    """Tests for dynamic tool consequential approval."""

    @pytest.fixture
    def owner(self, tmp_workspace: Path) -> FakeOwner:
        return FakeOwner(tmp_workspace)

    @pytest.fixture
    def dynamic_tools(self, tmp_workspace: Path) -> DynamicToolRegistry:
        return DynamicToolRegistry(tmp_workspace)

    @pytest.fixture
    def mcp_tools(self) -> MCPToolRegistry:
        return MCPToolRegistry()

    @pytest.fixture
    def executor(self, owner, dynamic_tools, mcp_tools) -> ToolExecutor:
        return ToolExecutor(
            owner=owner,
            dynamic_tools=dynamic_tools,
            mcp_tools=mcp_tools,
        )

    def _create_dynamic_tool(self, tmp_workspace: Path, name: str, code: str):
        """Create a dynamic tool file."""
        tools_dir = tmp_workspace / ".aura" / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        (tools_dir / f"{name}.py").write_text(code)

    def test_consequential_dynamic_triggers_approval(self, executor, tmp_workspace: Path):
        """Dynamic tool with consequential name triggers approval_cb."""
        self._create_dynamic_tool(tmp_workspace, "send_notification",
            "def send_notification(msg: str) -> dict:\n"
            '    """Send notification.\n\n'
            "    Args:\n"
            "        msg: The message.\n"
            '    """\n'
            '    return {"ok": True, "result": f"sent: {msg}"}\n'
        )

        calls = []
        def approval_cb(req):
            calls.append(req)
            return ApprovalDecision(action="approve")

        mock_res = SandboxResult(ok=True, stdout='{"ok": true, "result": "sent: hello"}', stderr="", exit_code=0)
        with patch("aura.sandbox.SandboxExecutor.run_dynamic_tool", return_value=mock_res):
            result = executor.execute("send_notification", {"msg": "hello"}, approval_cb)

        assert result.ok is True
        assert len(calls) == 1
        assert calls[0].tool_name == "send_notification"
        assert calls[0].rel_path == "dynamic:send_notification"

    def test_observational_dynamic_bypasses_approval(self, executor, tmp_workspace: Path):
        """Dynamic tool with observational name bypasses approval."""
        self._create_dynamic_tool(tmp_workspace, "get_status",
            "def get_status() -> dict:\n"
            '    """Get status."""\n'
            '    return {"ok": True, "status": "healthy"}\n'
        )

        calls = []
        def approval_cb(req):
            calls.append(req)
            return ApprovalDecision(action="approve")

        mock_res = SandboxResult(ok=True, stdout='{"ok": true, "status": "healthy"}', stderr="", exit_code=0)
        with patch("aura.sandbox.SandboxExecutor.run_dynamic_tool", return_value=mock_res):
            result = executor.execute("get_status", {}, approval_cb)

        assert result.ok is True
        assert len(calls) == 0

    def test_consequential_dynamic_reject_all_returns_rejected(self, executor, tmp_workspace: Path):
        """Dynamic consequential tool with reject_all returns rejected."""
        self._create_dynamic_tool(tmp_workspace, "delete_item",
            "def delete_item(item_id: int) -> dict:\n"
            '    """Delete item.\n\n'
            "    Args:\n"
            "        item_id: The item id.\n"
            '    """\n'
            '    return {"ok": True}\n'
        )

        result = executor.execute("delete_item", {"item_id": 1}, None, reject_all=True)
        assert result.ok is False
        assert result.payload.get("rejected") is True

    def test_static_write_file_unchanged(self, executor):
        """Existing static tool behavior (write_file with approval) is unchanged."""
        from aura.conversation.tools.registry import TOOL_HANDLERS

        calls = []
        def handler(self, args, approval_cb, reject_all):
            calls.append((args, approval_cb is not None, reject_all))
            return ToolExecResult(ok=True, payload={"ok": True})

        TOOL_HANDLERS["write_file"] = handler

        result = executor.execute("write_file", {"path": "a.py"}, lambda req: ApprovalDecision(action="approve"))
        assert result.ok is True
        assert len(calls) == 1
        assert calls[0] == ({"path": "a.py"}, True, False)
