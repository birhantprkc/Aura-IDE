from aura.gui.cards.worker_summary_card import WorkerSummaryCard


def test_validation_failure_header_is_not_harness_error() -> None:
    label, _ = WorkerSummaryCard._status_label(
        False,
        True,
        "Validation failed \u2014 Validation command failed (exit code 1): python -m py_compile a.py",
    )

    assert label == "Validation failed"


def test_internal_failure_header_is_harness_error() -> None:
    label, _ = WorkerSummaryCard._status_label(
        False,
        False,
        "Harness error \u2014 Harness error due to an internal Worker exception.",
    )

    assert label == "Harness error"


def test_worker_followup_header_is_not_harness_error() -> None:
    label, _ = WorkerSummaryCard._status_label(
        False,
        True,
        "Worker needs follow-up \u2014 blocked by missing dependency (worker_blocked).",
    )

    assert label == "Worker needs follow-up"
