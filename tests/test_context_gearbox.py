from __future__ import annotations

from aura.context_gearbox.models import ComposedContext, RuntimeRole
from aura.context_gearbox.runtime import compose_system_prompt
from aura.prompts import (
    PLANNER_SYSTEM_PROMPT,
    SINGLE_SYSTEM_PROMPT,
    WORKER_SYSTEM_PROMPT,
    build_tier1_context,
    inject_tier1_context,
)


def _entry_by_id(composed: ComposedContext, source_id: str):
    return next(entry for entry in composed.ledger if entry.source_id == source_id)


def test_prompt_compatibility_exports_work(tmp_path):
    assert PLANNER_SYSTEM_PROMPT
    assert WORKER_SYSTEM_PROMPT
    assert SINGLE_SYSTEM_PROMPT
    assert inject_tier1_context("A {TIER1_CONTEXT} B", "ctx") == "A ctx B"
    assert isinstance(build_tier1_context(tmp_path), str)


def test_composer_returns_composed_context_with_core_kernel(tmp_path):
    composed = compose_system_prompt(RuntimeRole.PLANNER, "", tmp_path)

    assert isinstance(composed, ComposedContext)
    assert composed.system_prompt
    assert composed.context_text
    core_entry = _entry_by_id(composed, "core_kernel")
    assert core_entry.included is True
    assert core_entry.char_count > 0


def test_project_rules_ledger_included_and_skipped(tmp_path):
    skipped = compose_system_prompt(RuntimeRole.PLANNER, "", tmp_path)
    skipped_entry = _entry_by_id(skipped, "project_rules")
    assert skipped_entry.included is False
    assert skipped_entry.char_count == 0

    (tmp_path / "project_rules.md").write_text("Use focused tests.", encoding="utf-8")
    included = compose_system_prompt(RuntimeRole.PLANNER, "", tmp_path)
    included_entry = _entry_by_id(included, "project_rules")
    assert included_entry.included is True
    assert included_entry.char_count > 0
    assert "Use focused tests." in included.context_text


def test_repo_map_ledger_included_or_skipped(tmp_path):
    skipped = compose_system_prompt(RuntimeRole.PLANNER, "", tmp_path)
    skipped_entry = _entry_by_id(skipped, "repo_map")
    assert skipped_entry.included is False
    assert skipped_entry.char_count == 0

    (tmp_path / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    included = compose_system_prompt(RuntimeRole.PLANNER, "", tmp_path, force=True)
    included_entry = _entry_by_id(included, "repo_map")
    assert included_entry.included is True
    assert included_entry.char_count > 0


def test_role_prompts_compose_without_old_doctrine(tmp_path):
    forbidden = [
        "Current-Info Research",
        "Worker doctrine",
        "Planner doctrine",
        "Recent Drone Run Activity",
        "Available Drones",
        "continuation_report",
        "private_style",
        ".aura/project_blueprint.md",
    ]
    for role in (RuntimeRole.PLANNER, RuntimeRole.WORKER, RuntimeRole.SINGLE):
        composed = compose_system_prompt(role, "", tmp_path)
        assert composed.system_prompt
        for text in forbidden:
            assert text not in composed.system_prompt
