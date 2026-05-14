"""Weighted, role-aware tool budget manager for Aura.

Replaces the blunt ``MAX_TOOL_ROUNDS`` cap with per-category limits,
cost tracking, and budget-exceeded signalling that integrates cleanly
into the tool-call loop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

ToolCategory = Literal[
    "read", "search", "write", "terminal", "git",
    "web", "research", "dispatch", "memory", "todo",
    "dynamic", "unknown",
]

RegistryMode = Literal["single", "planner", "worker", "researcher"]

# ---------------------------------------------------------------------------
# Cost table — higher cost = more expensive / slower / riskier
# ---------------------------------------------------------------------------

TOOL_COSTS: dict[str, int] = {
    "read_file": 1,
    "read_files": 2,
    "read_file_outline": 1,
    "list_directory": 1,
    "glob": 1,
    "grep_search": 2,
    "find_usages": 3,
    "search_codebase": 3,
    "git_status": 1,
    "git_diff": 3,
    "git_log": 2,
    "git_show": 3,
    "git_log_file": 2,
    "git_branch_list": 1,
    "git_stash_list": 1,
    "git_stash_show": 3,
    "write_file": 8,
    "edit_file": 6,
    "edit_symbol": 6,
    "run_terminal_command": 12,
    "web_search": 8,
    "web_fetch": 8,
    "run_research": 25,
    "dispatch_to_worker": 20,
    "search_project_memory": 2,
    "save_to_project_memory": 2,
    "update_todo_list": 1,
}

DEFAULT_UNKNOWN_COST = 8

# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------


def category_for_tool(name: str) -> ToolCategory:
    """Map a tool name to its budget category."""
    if name in {
        "read_file", "read_files", "read_file_outline",
        "list_directory", "glob",
    }:
        return "read"
    if name in {"grep_search", "find_usages", "search_codebase"}:
        return "search"
    if name in {"write_file", "edit_file", "edit_symbol"}:
        return "write"
    if name == "run_terminal_command":
        return "terminal"
    if name in {
        "git_status", "git_diff", "git_log", "git_show",
        "git_log_file", "git_branch_list", "git_stash_list",
        "git_stash_show",
    }:
        return "git"
    if name in {"web_search", "web_fetch"}:
        return "web"
    if name == "run_research":
        return "research"
    if name == "dispatch_to_worker":
        return "dispatch"
    if name in {"search_project_memory", "save_to_project_memory"}:
        return "memory"
    if name == "update_todo_list":
        return "todo"
    if name.startswith("mcp__"):
        return "dynamic"
    return "unknown"


# ---------------------------------------------------------------------------
# Config & snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolBudgetConfig:
    """Immutable budget limits for a single turn."""

    max_rounds: int = 60
    max_total_cost: int = 180
    max_tool_calls: int = 100
    max_reads: int = 60
    max_searches: int = 30
    max_writes: int = 20
    max_terminal: int = 8
    max_git: int = 20
    max_web: int = 4
    max_research: int = 0
    max_dispatches: int = 0
    max_memory: int = 0
    max_todo: int = 0
    warn_at_ratio: float = 0.75


@dataclass
class ToolBudgetSnapshot:
    """Mutable snapshot of current budget consumption."""

    rounds_used: int = 0
    tool_calls_used: int = 0
    total_cost_used: int = 0
    calls_by_category: dict[str, int] = field(default_factory=dict)
    calls_by_tool: dict[str, int] = field(default_factory=dict)
    warned: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        return {
            "rounds_used": self.rounds_used,
            "tool_calls_used": self.tool_calls_used,
            "total_cost_used": self.total_cost_used,
            "calls_by_category": dict(self.calls_by_category),
            "calls_by_tool": dict(self.calls_by_tool),
            "warned": self.warned,
        }


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class ToolBudgetExceeded(Exception):
    """Raised when a tool call would exceed the budget."""

    def __init__(
        self,
        reason: str,
        tool_name: str = "",
        category: ToolCategory = "unknown",
        snapshot: ToolBudgetSnapshot | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.tool_name = tool_name
        self.category: ToolCategory = category
        self.snapshot = snapshot or ToolBudgetSnapshot()


# ---------------------------------------------------------------------------
# Role budget presets
# ---------------------------------------------------------------------------

ROLE_BUDGETS: dict[RegistryMode, ToolBudgetConfig] = {
    "planner": ToolBudgetConfig(
        max_rounds=20,
        max_total_cost=80,
        max_tool_calls=50,
        max_reads=30,
        max_searches=20,
        max_writes=0,
        max_terminal=0,
        max_git=10,
        max_web=4,
        max_research=1,
        max_dispatches=1,
        max_memory=10,
        max_todo=0,
    ),
    "worker": ToolBudgetConfig(
        max_rounds=80,
        max_total_cost=220,
        max_tool_calls=120,
        max_reads=80,
        max_searches=40,
        max_writes=30,
        max_terminal=12,
        max_git=25,
        max_web=0,
        max_research=0,
        max_dispatches=0,
        max_memory=0,
        max_todo=40,
    ),
    "single": ToolBudgetConfig(
        max_rounds=60,
        max_total_cost=180,
        max_tool_calls=100,
        max_reads=60,
        max_searches=30,
        max_writes=20,
        max_terminal=8,
        max_git=20,
        max_web=4,
        max_research=0,
        max_dispatches=0,
        max_memory=0,
        max_todo=0,
    ),
    "researcher": ToolBudgetConfig(
        max_rounds=8,
        max_total_cost=70,
        max_tool_calls=20,
        max_reads=0,
        max_searches=0,
        max_writes=0,
        max_terminal=0,
        max_git=0,
        max_web=15,
        max_research=0,
        max_dispatches=0,
        max_memory=0,
        max_todo=0,
    ),
}

# ---------------------------------------------------------------------------
# Warning text
# ---------------------------------------------------------------------------

BUDGET_WARNING_TEXT = (
    "[TOOL BUDGET WARNING]\n"
    "You have used more than 75% of this turn's tool budget.\n"
    "Stop broad exploration. Prefer batched reads, targeted edits, and only necessary validation.\n"
    "If blocked, summarize the current state instead of looping."
)

# ---------------------------------------------------------------------------
# Payload helper
# ---------------------------------------------------------------------------


def budget_exceeded_payload(exc: ToolBudgetExceeded) -> str:
    """Build a JSON tool-result payload for a budget-exceeded error."""
    return json.dumps(
        {
            "ok": False,
            "error": exc.reason,
            "budget_exceeded": True,
            "tool": exc.tool_name,
            "category": exc.category,
            "snapshot": exc.snapshot.to_dict(),
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class ToolBudgetManager:
    """Tracks and enforces per-turn tool budget limits."""

    def __init__(self, config: ToolBudgetConfig) -> None:
        self._config = config
        self._snapshot = ToolBudgetSnapshot()

    @property
    def snapshot(self) -> ToolBudgetSnapshot:
        return self._snapshot

    # -- round tracking ------------------------------------------------------

    def record_round(self) -> None:
        """Increment the round counter; raise if max rounds exceeded."""
        self._snapshot.rounds_used += 1
        if self._snapshot.rounds_used > self._config.max_rounds:
            raise ToolBudgetExceeded(
                reason=f"Exceeded max tool rounds ({self._config.max_rounds}).",
                tool_name="",
                category="unknown",
                snapshot=self._snapshot,
            )

    # -- tool checks ---------------------------------------------------------

    def check_tool(self, name: str) -> None:
        """Dry-run check: raise ToolBudgetExceeded if *name* would exceed budget.

        Does **not** modify the snapshot.
        """
        category = category_for_tool(name)
        cost = self.tool_cost(name)

        if self._snapshot.tool_calls_used + 1 > self._config.max_tool_calls:
            raise ToolBudgetExceeded(
                reason=f"Exceeded max tool calls ({self._config.max_tool_calls}).",
                tool_name=name,
                category=category,
                snapshot=self._snapshot,
            )

        if self._snapshot.total_cost_used + cost > self._config.max_total_cost:
            raise ToolBudgetExceeded(
                reason=f"Exceeded max total cost ({self._config.max_total_cost}).",
                tool_name=name,
                category=category,
                snapshot=self._snapshot,
            )

        self._check_category(name, category)

    def reserve_tool(self, name: str) -> None:
        """Check budget, then record the tool call in the snapshot.

        Raises ToolBudgetExceeded if the budget would be exceeded.
        """
        self.check_tool(name)
        category = category_for_tool(name)
        cost = self.tool_cost(name)

        self._snapshot.tool_calls_used += 1
        self._snapshot.total_cost_used += cost
        self._snapshot.calls_by_category[category] = (
            self._snapshot.calls_by_category.get(category, 0) + 1
        )
        self._snapshot.calls_by_tool[name] = (
            self._snapshot.calls_by_tool.get(name, 0) + 1
        )

    def _check_category(self, name: str, category: ToolCategory) -> None:
        """Check category-specific limits."""
        limit_map: dict[ToolCategory, int] = {
            "read": self._config.max_reads,
            "search": self._config.max_searches,
            "write": self._config.max_writes,
            "terminal": self._config.max_terminal,
            "git": self._config.max_git,
            "web": self._config.max_web,
            "research": self._config.max_research,
            "dispatch": self._config.max_dispatches,
            "memory": self._config.max_memory,
            "todo": self._config.max_todo,
        }

        limit = limit_map.get(category)
        if limit is None:
            # dynamic / unknown — no category cap
            return

        current = self._snapshot.calls_by_category.get(category, 0)
        if current + 1 > limit:
            raise ToolBudgetExceeded(
                reason=f"Exceeded {category} tool limit ({limit}).",
                tool_name=name,
                category=category,
                snapshot=self._snapshot,
            )

    @staticmethod
    def tool_cost(name: str) -> int:
        """Return the cost of a tool by name."""
        return TOOL_COSTS.get(name, DEFAULT_UNKNOWN_COST)

    # -- warning -------------------------------------------------------------

    def check_warning(self, result_payload: str) -> str:
        """Inject a budget warning into *result_payload* if usage >= warn_at_ratio.

        Only fires once per turn (``warned`` flag on the snapshot).
        """
        if self._snapshot.warned:
            return result_payload

        total_ratio = (
            self._snapshot.total_cost_used / self._config.max_total_cost
            if self._config.max_total_cost > 0
            else 0.0
        )
        round_ratio = (
            self._snapshot.rounds_used / self._config.max_rounds
            if self._config.max_rounds > 0
            else 0.0
        )

        if total_ratio < self._config.warn_at_ratio and round_ratio < self._config.warn_at_ratio:
            return result_payload

        self._snapshot.warned = True

        try:
            parsed = json.loads(result_payload)
            if isinstance(parsed, dict):
                if "output" in parsed and isinstance(parsed["output"], str):
                    parsed["output"] += "\n\n" + BUDGET_WARNING_TEXT
                else:
                    parsed["budget_warning"] = BUDGET_WARNING_TEXT
                return json.dumps(parsed, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass

        return result_payload + "\n\n" + BUDGET_WARNING_TEXT
