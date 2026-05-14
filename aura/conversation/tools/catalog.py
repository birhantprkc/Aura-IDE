"""Tool catalog — builds the list of tool schemas for the current mode/read-only state."""

from __future__ import annotations

from typing import Any

from aura.conversation.tools._types import RegistryMode
from aura.conversation.tools._schemas import (
    DISPATCH_TOOL_DEF,
    GIT_TOOL_DEFS,
    PROJECT_MEMORY_TOOL_DEFS,
    READ_TOOL_DEFS,
    RESEARCH_TOOL_DEFS,
    TERMINAL_TOOL_DEF,
    WEB_TOOL_DEFS,
    WORKER_TODO_TOOL_DEF,
    WRITE_TOOL_DEFS,
)


class ToolCatalog:
    """Builds the list of available tool schemas for the current mode/read-only state.

    Given mode, read-only state, dynamic schemas, and MCP schemas,
    returns the complete list of tool definitions for the API.
    """

    def build_tool_defs(
        self,
        *,
        mode: RegistryMode,
        read_only: bool,
        dynamic_schemas: list[dict[str, Any]] | None = None,
        mcp_schemas: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Build tool definitions for the given mode and state.

        Args:
            mode: The current registry mode.
            read_only: If True, only read and git tools are returned.
            dynamic_schemas: Schemas from dynamic (user) tools.
            mcp_schemas: Schemas from connected MCP servers.

        Returns:
            A list of OpenAI-compatible tool definition dicts.
        """
        # Read-only is the safety floor — strips writes AND dispatch (since
        # there's nothing for a worker to do without writes).
        if read_only:
            tools: list[dict[str, Any]] = list(READ_TOOL_DEFS) + list(GIT_TOOL_DEFS)
        elif mode == "researcher":
            tools = list(WEB_TOOL_DEFS)
        elif mode == "planner":
            tools = (
                list(READ_TOOL_DEFS)
                + [dict(DISPATCH_TOOL_DEF)]
                + list(RESEARCH_TOOL_DEFS)
                + list(PROJECT_MEMORY_TOOL_DEFS)
                + list(GIT_TOOL_DEFS)
            )
        elif mode == "worker":
            tools = (
                list(READ_TOOL_DEFS)
                + list(WRITE_TOOL_DEFS)
                + [dict(WORKER_TODO_TOOL_DEF)]
                + [dict(TERMINAL_TOOL_DEF)]
                + list(GIT_TOOL_DEFS)
            )
        else:  # "single" or any unknown mode
            tools = (
                list(READ_TOOL_DEFS)
                + list(WRITE_TOOL_DEFS)
                + [dict(TERMINAL_TOOL_DEF)]
                + list(GIT_TOOL_DEFS)
            )

        # Append dynamic tools (only when not read-only)
        if not read_only and dynamic_schemas:
            tools.extend(dynamic_schemas)

        # Append MCP tool schemas (available in all modes)
        if mcp_schemas:
            tools.extend(mcp_schemas)

        return tools
