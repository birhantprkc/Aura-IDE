"""Tests for aura.conversation.tool_budget."""

from __future__ import annotations

import json

import pytest

from aura.conversation.tool_budget import (
    BUDGET_WARNING_TEXT,
    DEFAULT_UNKNOWN_COST,
    ROLE_BUDGETS,
    TOOL_COSTS,
    ToolBudgetConfig,
    ToolBudgetExceeded,
    ToolBudgetManager,
    ToolBudgetSnapshot,
    budget_exceeded_payload,
    category_for_tool,
)


# ---------------------------------------------------------------------------
# TestCategoryMapping
# ---------------------------------------------------------------------------


class TestCategoryMapping:
    def test_read_tools(self):
        for name in ("read_file", "read_files", "read_file_outline", "list_directory", "glob"):
            assert category_for_tool(name) == "read"

    def test_search_tools(self):
        for name in ("grep_search", "find_usages", "search_codebase"):
            assert category_for_tool(name) == "search"

    def test_write_tools(self):
        for name in ("write_file", "edit_file", "edit_symbol"):
            assert category_for_tool(name) == "write"

    def test_terminal_tool(self):
        assert category_for_tool("run_terminal_command") == "terminal"

    def test_git_tools(self):
        for name in (
            "git_status", "git_diff", "git_log", "git_show",
            "git_log_file", "git_branch_list", "git_stash_list", "git_stash_show",
        ):
            assert category_for_tool(name) == "git"

    def test_web_tools(self):
        for name in ("web_search", "web_fetch"):
            assert category_for_tool(name) == "web"

    def test_research_tool(self):
        assert category_for_tool("run_research") == "research"

    def test_dispatch_tool(self):
        assert category_for_tool("dispatch_to_worker") == "dispatch"

    def test_memory_tools(self):
        for name in ("search_project_memory", "save_to_project_memory"):
            assert category_for_tool(name) == "memory"

    def test_todo_tool(self):
        assert category_for_tool("update_todo_list") == "todo"

    def test_dynamic_mcp_tool(self):
        assert category_for_tool("mcp__some_server") == "dynamic"

    def test_unknown_tool(self):
        assert category_for_tool("some_random_tool") == "unknown"


# ---------------------------------------------------------------------------
# TestToolCosts
# ---------------------------------------------------------------------------


class TestToolCosts:
    def test_known_tool_costs(self):
        assert ToolBudgetManager.tool_cost("read_file") == 1
        assert ToolBudgetManager.tool_cost("read_files") == 2
        assert ToolBudgetManager.tool_cost("write_file") == 8
        assert ToolBudgetManager.tool_cost("edit_file") == 6
        assert ToolBudgetManager.tool_cost("edit_symbol") == 6
        assert ToolBudgetManager.tool_cost("run_terminal_command") == 12
        assert ToolBudgetManager.tool_cost("dispatch_to_worker") == 20
        assert ToolBudgetManager.tool_cost("run_research") == 25
        assert ToolBudgetManager.tool_cost("update_todo_list") == 1

    def test_unknown_tool_default_cost(self):
        assert ToolBudgetManager.tool_cost("some_unknown_tool") == DEFAULT_UNKNOWN_COST

    def test_cost_table_consistency(self):
        """Every key in TOOL_COSTS maps to a valid category."""
        for name in TOOL_COSTS:
            cat = category_for_tool(name)
            assert cat != "unknown", f"{name} should have a known category"


# ---------------------------------------------------------------------------
# TestBudgetReserveAndLimits
# ---------------------------------------------------------------------------


class TestBudgetReserveAndLimits:
    def test_read_consumes_low_cost(self):
        mgr = ToolBudgetManager(ROLE_BUDGETS["worker"])
        for _ in range(50):
            mgr.reserve_tool("read_file")
        snap = mgr.snapshot
        assert snap.tool_calls_used == 50
        assert snap.total_cost_used == 50  # 1 each
        assert snap.calls_by_category.get("read", 0) == 50

    def test_terminal_hits_category_cap(self):
        mgr = ToolBudgetManager(ROLE_BUDGETS["worker"])
        # Worker max_terminal = 12
        for i in range(12):
            mgr.reserve_tool("run_terminal_command")
        with pytest.raises(ToolBudgetExceeded) as exc_info:
            mgr.reserve_tool("run_terminal_command")
        assert "terminal" in exc_info.value.reason.lower()
        assert exc_info.value.category == "terminal"

    def test_total_cost_cap(self):
        # Use a tiny config so total cost is hit quickly
        config = ToolBudgetConfig(
            max_rounds=100, max_total_cost=30, max_tool_calls=100,
            max_writes=100, max_terminal=100,
        )
        mgr = ToolBudgetManager(config)
        # write_file costs 8; 3 * 8 = 24, 4 * 8 = 32 > 30
        for _ in range(3):
            mgr.reserve_tool("write_file")
        with pytest.raises(ToolBudgetExceeded) as exc_info:
            mgr.reserve_tool("write_file")
        assert "total cost" in exc_info.value.reason.lower()

    def test_max_tool_calls_cap(self):
        config = ToolBudgetConfig(
            max_rounds=100, max_total_cost=1000, max_tool_calls=5,
        )
        mgr = ToolBudgetManager(config)
        for _ in range(5):
            mgr.reserve_tool("read_file")
        with pytest.raises(ToolBudgetExceeded) as exc_info:
            mgr.reserve_tool("read_file")
        assert "tool calls" in exc_info.value.reason.lower()

    def test_max_rounds_cap(self):
        config = ToolBudgetConfig(max_rounds=3)
        mgr = ToolBudgetManager(config)
        mgr.record_round()
        mgr.record_round()
        mgr.record_round()
        with pytest.raises(ToolBudgetExceeded) as exc_info:
            mgr.record_round()
        assert "rounds" in exc_info.value.reason.lower()


# ---------------------------------------------------------------------------
# TestPlannerBudget
# ---------------------------------------------------------------------------


class TestPlannerBudget:
    def test_planner_rejects_writes(self):
        mgr = ToolBudgetManager(ROLE_BUDGETS["planner"])
        with pytest.raises(ToolBudgetExceeded) as exc_info:
            mgr.reserve_tool("write_file")
        assert exc_info.value.category == "write"
        assert "write" in exc_info.value.reason.lower()

    def test_planner_allows_one_dispatch(self):
        mgr = ToolBudgetManager(ROLE_BUDGETS["planner"])
        mgr.reserve_tool("dispatch_to_worker")
        with pytest.raises(ToolBudgetExceeded) as exc_info:
            mgr.reserve_tool("dispatch_to_worker")
        assert exc_info.value.category == "dispatch"

    def test_planner_allows_reads_and_searches(self):
        mgr = ToolBudgetManager(ROLE_BUDGETS["planner"])
        for _ in range(10):
            mgr.reserve_tool("read_file")
        for _ in range(5):
            mgr.reserve_tool("grep_search")
        snap = mgr.snapshot
        assert snap.calls_by_category.get("read", 0) == 10
        assert snap.calls_by_category.get("search", 0) == 5


# ---------------------------------------------------------------------------
# TestWorkerBudget
# ---------------------------------------------------------------------------


class TestWorkerBudget:
    def test_worker_allows_writes(self):
        mgr = ToolBudgetManager(ROLE_BUDGETS["worker"])
        # Worker max_writes=30, but total_cost=220. write_file costs 8.
        # 27 * 8 = 216 (ok), 28 * 8 = 224 > 220 (total cost exceeded)
        for _ in range(27):
            mgr.reserve_tool("write_file")
        # 28th should fail on total cost, not write category
        with pytest.raises(ToolBudgetExceeded) as exc_info:
            mgr.reserve_tool("write_file")
        # Could be total cost or write limit — both are valid
        assert "total cost" in exc_info.value.reason.lower() or "write" in exc_info.value.reason.lower()

    def test_worker_allows_terminal(self):
        mgr = ToolBudgetManager(ROLE_BUDGETS["worker"])
        for _ in range(12):
            mgr.reserve_tool("run_terminal_command")
        with pytest.raises(ToolBudgetExceeded) as exc_info:
            mgr.reserve_tool("run_terminal_command")
        assert exc_info.value.category == "terminal"


# ---------------------------------------------------------------------------
# TestUnknownDynamicTools
# ---------------------------------------------------------------------------


class TestUnknownDynamicTools:
    def test_unknown_tool_default_cost(self):
        mgr = ToolBudgetManager(ROLE_BUDGETS["worker"])
        mgr.reserve_tool("some_unknown_tool")
        snap = mgr.snapshot
        assert snap.total_cost_used == DEFAULT_UNKNOWN_COST
        assert snap.calls_by_category.get("unknown", 0) == 1

    def test_dynamic_mcp_tool(self):
        mgr = ToolBudgetManager(ROLE_BUDGETS["worker"])
        mgr.reserve_tool("mcp__something")
        snap = mgr.snapshot
        assert snap.calls_by_category.get("dynamic", 0) == 1
        # Dynamic tools have no category cap, so many should be allowed
        # But total cost (220) limits: 27 * 8 = 216, 28 * 8 = 224 > 220
        for _ in range(26):
            mgr.reserve_tool("mcp__something")
        assert mgr.snapshot.calls_by_category.get("dynamic", 0) == 27


# ---------------------------------------------------------------------------
# TestWarning
# ---------------------------------------------------------------------------


class TestWarning:
    def test_warning_fires_after_75_percent(self):
        config = ToolBudgetConfig(
            max_rounds=100, max_total_cost=100, max_tool_calls=100,
            max_writes=100, warn_at_ratio=0.75,
        )
        mgr = ToolBudgetManager(config)
        # write_file costs 8; 9 * 8 = 72 (< 75), 10 * 8 = 80 (>= 75)
        for _ in range(9):
            mgr.reserve_tool("write_file")
        result = mgr.check_warning('{"ok":true,"output":"hello"}')
        assert BUDGET_WARNING_TEXT not in result

        mgr.reserve_tool("write_file")  # now at 80/100
        result = mgr.check_warning('{"ok":true,"output":"hello"}')
        parsed = json.loads(result)
        assert BUDGET_WARNING_TEXT in parsed.get("output", "")

    def test_warning_only_fires_once(self):
        config = ToolBudgetConfig(
            max_rounds=100, max_total_cost=100, max_tool_calls=100,
            max_writes=100, warn_at_ratio=0.75,
        )
        mgr = ToolBudgetManager(config)
        for _ in range(10):
            mgr.reserve_tool("write_file")
        result1 = mgr.check_warning('{"ok":true,"output":"hello"}')
        # Second call with same input — warned already True, so returned unchanged
        result2 = mgr.check_warning('{"ok":true,"output":"hello"}')
        # result1 has the warning (parse JSON to check), result2 does not
        parsed1 = json.loads(result1)
        assert BUDGET_WARNING_TEXT in parsed1.get("output", "")
        assert BUDGET_WARNING_TEXT not in result2
        # But the snapshot warned flag is True
        assert mgr.snapshot.warned is True

    def test_warning_rounds_ratio(self):
        config = ToolBudgetConfig(
            max_rounds=4, max_total_cost=1000, max_tool_calls=100,
            warn_at_ratio=0.75,
        )
        mgr = ToolBudgetManager(config)
        mgr.record_round()
        mgr.record_round()
        mgr.record_round()  # 3/4 = 0.75
        result = mgr.check_warning('{"ok":true}')
        parsed = json.loads(result)
        assert BUDGET_WARNING_TEXT in parsed.get("budget_warning", "")

    def test_warning_non_json_payload(self):
        config = ToolBudgetConfig(
            max_rounds=100, max_total_cost=100, max_tool_calls=100,
            max_writes=100, warn_at_ratio=0.75,
        )
        mgr = ToolBudgetManager(config)
        for _ in range(10):
            mgr.reserve_tool("write_file")
        result = mgr.check_warning("plain text result")
        assert BUDGET_WARNING_TEXT in result
        assert result.startswith("plain text result")

    def test_warning_adds_budget_warning_key_when_no_output(self):
        config = ToolBudgetConfig(
            max_rounds=100, max_total_cost=100, max_tool_calls=100,
            max_writes=100, warn_at_ratio=0.75,
        )
        mgr = ToolBudgetManager(config)
        for _ in range(10):
            mgr.reserve_tool("write_file")
        result = mgr.check_warning('{"ok":true}')
        parsed = json.loads(result)
        assert "budget_warning" in parsed
        assert BUDGET_WARNING_TEXT in parsed["budget_warning"]


# ---------------------------------------------------------------------------
# TestBudgetExceededPayload
# ---------------------------------------------------------------------------


class TestBudgetExceededPayload:
    def test_payload_is_valid_json(self):
        exc = ToolBudgetExceeded(
            reason="Exceeded write tool limit (0).",
            tool_name="write_file",
            category="write",
        )
        payload = budget_exceeded_payload(exc)
        parsed = json.loads(payload)
        assert parsed["ok"] is False
        assert parsed["budget_exceeded"] is True
        assert parsed["tool"] == "write_file"
        assert parsed["category"] == "write"
        assert "error" in parsed
        assert "snapshot" in parsed

    def test_payload_includes_snapshot(self):
        exc = ToolBudgetExceeded(
            reason="test",
            tool_name="t",
            category="unknown",
            snapshot=ToolBudgetSnapshot(rounds_used=3, tool_calls_used=10),
        )
        payload = budget_exceeded_payload(exc)
        parsed = json.loads(payload)
        assert parsed["snapshot"]["rounds_used"] == 3
        assert parsed["snapshot"]["tool_calls_used"] == 10


# ---------------------------------------------------------------------------
# TestSnapshotDict
# ---------------------------------------------------------------------------


class TestSnapshotDict:
    def test_to_dict(self):
        snap = ToolBudgetSnapshot(
            rounds_used=5,
            tool_calls_used=12,
            total_cost_used=42,
            calls_by_category={"read": 10, "write": 2},
            calls_by_tool={"read_file": 10, "write_file": 2},
            warned=True,
        )
        d = snap.to_dict()
        assert d["rounds_used"] == 5
        assert d["tool_calls_used"] == 12
        assert d["total_cost_used"] == 42
        assert d["calls_by_category"] == {"read": 10, "write": 2}
        assert d["calls_by_tool"] == {"read_file": 10, "write_file": 2}
        assert d["warned"] is True

    def test_to_dict_defaults(self):
        snap = ToolBudgetSnapshot()
        d = snap.to_dict()
        assert d["rounds_used"] == 0
        assert d["tool_calls_used"] == 0
        assert d["total_cost_used"] == 0
        assert d["calls_by_category"] == {}
        assert d["calls_by_tool"] == {}
        assert d["warned"] is False


# ---------------------------------------------------------------------------
# TestCustomMaxRounds
# ---------------------------------------------------------------------------


class TestCustomMaxRounds:
    def test_custom_max_rounds_override(self):
        config = ToolBudgetConfig(max_rounds=5)
        assert config.max_rounds == 5
        mgr = ToolBudgetManager(config)
        for _ in range(5):
            mgr.record_round()
        with pytest.raises(ToolBudgetExceeded):
            mgr.record_round()

    def test_check_tool_does_not_modify_snapshot(self):
        mgr = ToolBudgetManager(ROLE_BUDGETS["worker"])
        mgr.check_tool("read_file")
        assert mgr.snapshot.tool_calls_used == 0
        assert mgr.snapshot.total_cost_used == 0

    def test_reserve_tool_modifies_snapshot(self):
        mgr = ToolBudgetManager(ROLE_BUDGETS["worker"])
        mgr.reserve_tool("read_file")
        assert mgr.snapshot.tool_calls_used == 1
        assert mgr.snapshot.total_cost_used == 1
