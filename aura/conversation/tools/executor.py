"""Tool execution dispatcher — routes tool calls to static, MCP, or dynamic handlers."""
from __future__ import annotations

import json
from typing import Any

from aura.conversation.tools._types import ApprovalCallback, ApprovalRequest, ToolExecResult
from aura.conversation.tools.consequential import is_consequential
from aura.conversation.tools.dynamic import execute_dynamic_tool


class ToolExecutor:
    """Dispatches tool execution across static handlers, MCP, and dynamic tools."""

    def __init__(
        self,
        *,
        owner: Any,
        dynamic_tools: Any,  # DynamicToolRegistry
        mcp_tools: Any,      # MCPToolRegistry
    ) -> None:
        self._owner = owner
        self._dynamic_tools = dynamic_tools
        self._mcp_tools = mcp_tools

    def execute(
        self,
        name: str,
        args: dict[str, Any],
        approval_cb: ApprovalCallback,
        reject_all: bool = False,
    ) -> ToolExecResult:
        """Dispatch a tool call to the appropriate handler.

        Priority:
        1. Static handlers (TOOL_HANDLERS)
        2. MCP tools
        3. Dynamic tools
        4. Unknown tool error
        """
        try:
            from aura.conversation.tools.registry import TOOL_HANDLERS

            # 1. Static dispatch via TOOL_HANDLERS
            handler = TOOL_HANDLERS.get(name)
            if handler is not None:
                return handler(self._owner, args, approval_cb, reject_all)

            # 2. MCP tools
            if self._mcp_tools.can_execute(name):
                if is_consequential(name):
                    if reject_all:
                        return ToolExecResult(
                            ok=False,
                            payload={"ok": False, "rejected": True, "error": f"rejected: {name}"},
                        )
                    if approval_cb is not None:
                        request = ApprovalRequest(
                            tool_name=name,
                            rel_path=f"mcp:{name}",
                            old_content="",
                            new_content=json.dumps(args),
                            is_new_file=True,
                        )
                        decision = approval_cb(request)
                        if decision.action in ("reject", "reject_all"):
                            return ToolExecResult(
                                ok=False,
                                payload={
                                    "ok": False,
                                    "rejected": True,
                                    "error": f"rejected: {name}",
                                    "decision": decision.action,
                                },
                            )
                return self._mcp_tools.execute(name, args)

            # 3. Dynamic tools
            dynamic_path = self._dynamic_tools.get(name)
            if dynamic_path is not None:
                if is_consequential(name):
                    if reject_all:
                        return ToolExecResult(
                            ok=False,
                            payload={"ok": False, "rejected": True, "error": f"rejected: {name}"},
                        )
                    if approval_cb is not None:
                        request = ApprovalRequest(
                            tool_name=name,
                            rel_path=f"dynamic:{name}",
                            old_content="",
                            new_content=json.dumps(args),
                            is_new_file=True,
                        )
                        decision = approval_cb(request)
                        if decision.action in ("reject", "reject_all"):
                            return ToolExecResult(
                                ok=False,
                                payload={
                                    "ok": False,
                                    "rejected": True,
                                    "error": f"rejected: {name}",
                                    "decision": decision.action,
                                },
                            )
                result = execute_dynamic_tool(
                    dynamic_path, name, args, self._owner.workspace_root
                )
                return ToolExecResult(ok=result.get("ok", False), payload=result)

            # 4. Unknown
            return ToolExecResult(
                ok=False, payload={"ok": False, "error": f"unknown tool: {name}"}
            )
        except ValueError as exc:
            return ToolExecResult(
                ok=False,
                payload={"ok": False, "error": str(exc), "failure_class": "path_error"},
            )
        except OSError as exc:
            return ToolExecResult(
                ok=False,
                payload={"ok": False, "error": str(exc), "failure_class": "internal_error"},
            )
