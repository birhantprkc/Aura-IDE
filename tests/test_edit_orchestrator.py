from __future__ import annotations

from aura.conversation.edit_orchestrator import (
    EditMode,
    EditRetryLedger,
    FileEditProfile,
    select_edit_mode,
    strategy_decision_for_attempt,
)


def test_normal_file_uses_patch_mode() -> None:
    content = "def alpha():\n    return 1\n"

    assert select_edit_mode("aura/module.py", content) == EditMode.PATCH


def test_small_escape_heavy_file_can_switch_to_whole_file() -> None:
    content = (
        r'WINDOWS_PATH = "C:\\Users\\carps\\AppData\\Local\\Aura\\config.json"' "\n"
        r'PATTERN = r"^C:\\\\Users\\\\(?P<name>[^\\\\]+)\\\\Aura\\\\.*\\.json$"' "\n"
        r'JSON_LINE = "{\"path\":\"C:\\\\tmp\\\\aura\",\"ok\":true}"' "\n"
    )
    profile = FileEditProfile.from_content("aura/paths.py", content)
    ledger = EditRetryLedger()
    ledger.record_failure(
        mode=EditMode.PATCH,
        path="aura/paths.py",
        failure_class="patch_hunk_not_found",
    )
    ledger.record_failure(
        mode=EditMode.FOCUSED_REPAIR,
        path="aura/paths.py",
        failure_class="patch_hunk_not_found",
    )

    assert profile.escape_score >= 12
    assert profile.whole_file_allowed is True
    assert select_edit_mode("aura/paths.py", ledger=ledger, profile=profile) == EditMode.WHOLE_FILE


def test_failed_patch_switches_to_focused_repair() -> None:
    ledger = EditRetryLedger()
    ledger.record_failure(
        mode=EditMode.PATCH,
        path="./aura\\module.py",
        failure_class="patch_hunk_ambiguous",
    )

    assert ledger.failure_count(
        path="aura/module.py",
        mode=EditMode.PATCH,
        failure_class="patch_hunk_ambiguous",
    ) == 1
    assert select_edit_mode("aura/module.py", "VALUE = 1\n", ledger=ledger) == EditMode.FOCUSED_REPAIR


def test_repeated_failure_stops_cleanly_when_whole_file_is_not_allowed() -> None:
    content = "\n".join(f"VALUE_{index} = {index}" for index in range(800))
    profile = FileEditProfile.from_content("aura/large_module.py", content)
    ledger = EditRetryLedger()
    ledger.record_failure(
        mode=EditMode.PATCH,
        path="aura/large_module.py",
        failure_class="patch_hunk_not_found",
        error="old block missing",
    )
    ledger.record_failure(
        mode=EditMode.FOCUSED_REPAIR,
        path="aura/large_module.py",
        failure_class="patch_hunk_not_found",
        error="repair hunk missing",
    )

    decision = strategy_decision_for_attempt(
        ledger=ledger,
        name="patch_file",
        args={"path": "aura/large_module.py", "edits": []},
        path="aura/large_module.py",
        profile=profile,
    )

    assert profile.whole_file_allowed is False
    assert decision is not None
    assert decision.failure_class == "edit_strategy_exhausted"
    assert decision.recoverable is False
    assert decision.suggested_next_tool == "none"
