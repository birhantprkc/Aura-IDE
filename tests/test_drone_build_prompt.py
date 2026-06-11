"""Tests for aura.drones.build_prompt.build_drone_creation_prompt."""

from __future__ import annotations

from aura.drones.build_prompt import build_drone_creation_prompt
from aura.drones.build_spec import DroneBuildBrief


def test_buildable_brief_prompt_includes_build_brief_text() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Plan ready.",
        ready_to_build=True,
        build_brief="Build a bug scout that investigates bugs.",
    )
    prompt = build_drone_creation_prompt(brief)

    assert brief.build_brief in prompt
    assert "Build a bug scout" in prompt


def test_prompt_includes_approved_language() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a nightly reporter.",
    )
    prompt = build_drone_creation_prompt(brief)

    assert "approved" in prompt.lower()


def test_prompt_mentions_design_and_create() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)

    assert "design and create" in prompt.lower() or "build the drone" in prompt.lower()


def test_prompt_includes_access_setup_safety_notes() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Monitor logs. Needs filesystem read access. Run every hour.",
    )
    prompt = build_drone_creation_prompt(brief)

    # The build_brief content should appear verbatim
    assert "Monitor logs" in prompt
    assert "Needs filesystem read access" in prompt
    assert "Run every hour" in prompt


def test_prompt_includes_store_no_secrets_instruction() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)

    assert "store no secrets" in prompt.lower()


def test_prompt_includes_access_setup_harness_guidance() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)

    assert "access, setup, safety, and harness" in prompt.lower()
    assert "runtime access" in prompt.lower() or "connector" in prompt.lower()


def test_prompt_references_definition_and_store() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)

    assert "DroneDefinition" in prompt
    assert "DroneStore" in prompt
    assert ".aura/drones" in prompt


def test_prompt_does_not_contain_spec_fields() -> None:
    """No references to old spec fields like kind, job, capabilities_needed, etc."""
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)

    assert "capabilities_needed" not in prompt
    assert "missing_capabilities" not in prompt
    assert "build_status" not in prompt
    assert "output_contract" not in prompt
    assert "Do not add external browser" not in prompt
    assert "Gmail" not in prompt
    assert "scheduler capabilities" not in prompt


def test_prompt_mentions_resolve_capability() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)
    assert "resolve_capability" in prompt


def test_prompt_mentions_capability_requirements() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)
    assert "capability_requirements" in prompt


def test_prompt_mentions_capability_bindings() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)
    assert "capability_bindings" in prompt


def test_prompt_mentions_setup_steps() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)
    assert "setup_steps" in prompt


def test_prompt_mentions_first_run_test() -> None:
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)
    assert "first_run_test" in prompt


def test_prompt_does_not_frame_routes_as_closed_list() -> None:
    """Route options must be open-ended, not a closed list of MCP/browser/code."""
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)
    # Must not present a fixed menu of 2-3 route types
    assert "MCP, browser" not in prompt
    assert "three routes" not in prompt.lower()
    assert "choose between" not in prompt.lower()
    # Must use open-ended language about harness or external capabilities
    assert "existing harness" in prompt.lower()


def test_prompt_old_bad_fields_stay_absent() -> None:
    """No old spec fields leak into the prompt."""
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)
    assert "capabilities_needed" not in prompt
    assert "missing_capabilities" not in prompt
    assert "build_status" not in prompt
    assert "output_contract" not in prompt
    assert "Do not add external browser" not in prompt
    assert "Gmail" not in prompt
    assert "scheduler capabilities" not in prompt


def test_save_drone_definition_remains_required() -> None:
    """save_drone_definition must be mentioned as the required persistence step."""
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)
    assert "save_drone_definition" in prompt


def test_resolve_capability_no_longer_mandatory_for_every_drone() -> None:
    """Prompt must NOT say "Call resolve_capability for each" or similar universal phrasing."""
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)
    # Must not force resolve_capability for every drone
    assert "resolve_capability for each" not in prompt.lower()
    assert "resolve_capability for every" not in prompt.lower()
    assert "resolve_capability for all" not in prompt.lower()


def test_existing_harness_tools_can_be_used_directly() -> None:
    """Prompt must mention that existing harness tools can go directly into allowed_tools."""
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)
    assert (
        "existing harness" in prompt.lower()
        or "choose allowed_tools directly" in prompt.lower()
        or "default_tools_for_policy" in prompt.lower()
    )


def test_external_capabilities_can_still_use_resolve_capability() -> None:
    """Prompt must still mention resolve_capability for external/unknown capabilities."""
    brief = DroneBuildBrief(
        response_type="brief",
        message="Ready.",
        ready_to_build=True,
        build_brief="Build a drone.",
    )
    prompt = build_drone_creation_prompt(brief)
    assert "resolve_capability" in prompt
