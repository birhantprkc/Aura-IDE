from __future__ import annotations

from aura.conversation.verification_progress import (
    VerificationProgressTracker,
    fingerprint_failures,
)


def test_tracker_trips_on_third_identical_product_failure():
    tracker = VerificationProgressTracker()
    output = "FAILED tests/test_widget.py::test_renders - AssertionError\n"

    assert tracker.observe(
        command="pytest tests/test_widget.py -q",
        classification="product_validation_failed",
        output=output,
    ) is None
    assert tracker.observe(
        command="pytest   tests/test_widget.py   -q",
        classification="product_validation_failed",
        output=output,
    ) is None

    stall = tracker.observe(
        command="pytest tests/test_widget.py -q",
        classification="product_validation_failed",
        output=output,
    )

    assert stall is not None
    assert stall["ok"] is False
    assert stall["recoverable"] is True
    assert stall["phase_boundary"] is True
    assert stall["reason"] == "verification_not_converging"
    assert stall["tool"] == "run_terminal_command"
    assert stall["verification_stall"] == {
        "fingerprint": ["tests/test_widget.py::test_renders"],
        "repeated": 3,
        "threshold": 3,
    }
    assert "tests/test_widget.py::test_renders" in stall["message"]


def test_passed_or_different_fingerprint_resets_tracker():
    tracker = VerificationProgressTracker()
    one_failure = "FAILED tests/test_widget.py::test_one - AssertionError\n"
    two_failures = (
        "FAILED tests/test_widget.py::test_one - AssertionError\n"
        "FAILED tests/test_widget.py::test_two - AssertionError\n"
    )

    assert tracker.observe(
        command="pytest tests/test_widget.py -q",
        classification="product_validation_failed",
        output=one_failure,
    ) is None
    assert tracker.observe(
        command="pytest tests/test_widget.py -q",
        classification="passed",
        output="1 passed in 0.01s\n",
    ) is None
    assert tracker.observe(
        command="pytest tests/test_widget.py -q",
        classification="product_validation_failed",
        output=one_failure,
    ) is None
    assert tracker.observe(
        command="pytest tests/test_widget.py -q",
        classification="product_validation_failed",
        output=two_failures,
    ) is None
    assert tracker.observe(
        command="pytest tests/test_widget.py -q",
        classification="product_validation_failed",
        output=two_failures,
    ) is None


def test_non_product_classifications_do_not_touch_state():
    tracker = VerificationProgressTracker()
    output = "FAILED tests/test_widget.py::test_one - AssertionError\n"

    assert tracker.observe(
        command="pytest tests/test_widget.py -q",
        classification="product_validation_failed",
        output=output,
    ) is None
    assert tracker.observe(
        command="pytest tests/test_widget.py -q",
        classification="timeout",
        output=output,
    ) is None
    assert tracker.observe(
        command="pytest tests/test_widget.py -q",
        classification="product_validation_failed",
        output=output,
    ) is None

    stall = tracker.observe(
        command="pytest tests/test_widget.py -q",
        classification="product_validation_failed",
        output=output,
    )
    assert stall is not None


def test_fingerprint_uses_pytest_node_ids_independent_of_order_and_duration():
    first = (
        "FAILED tests/test_alpha.py::test_one - AssertionError\n"
        "FAILED tests/test_alpha.py::test_two - AssertionError\n"
        "2 failed in 0.13s\n"
    )
    second = (
        "FAILED tests/test_alpha.py::test_two - AssertionError\n"
        "2 failed in 0.92s\n"
        "FAILED tests/test_alpha.py::test_one - AssertionError\n"
    )

    assert fingerprint_failures(first) == fingerprint_failures(second)


def test_fingerprint_shrinks_when_pytest_failure_is_fixed():
    three_failures = (
        "FAILED tests/test_alpha.py::test_one - AssertionError\n"
        "FAILED tests/test_alpha.py::test_two - AssertionError\n"
        "FAILED tests/test_alpha.py::test_three - AssertionError\n"
    )
    two_failures = (
        "FAILED tests/test_alpha.py::test_one - AssertionError\n"
        "FAILED tests/test_alpha.py::test_three - AssertionError\n"
    )

    before = fingerprint_failures(three_failures)
    after = fingerprint_failures(two_failures)

    assert len(after) < len(before)
    assert after < before


def test_fingerprint_falls_back_to_exception_types():
    output = (
        "Traceback (most recent call last):\n"
        "ValueError: bad value 1\n"
        "CustomFailure: failed custom check\n"
    )

    assert fingerprint_failures(output) == frozenset({"ValueError:", "CustomFailure:"})


def test_fingerprint_hash_strips_volatile_spans():
    first = (
        "Traceback (most recent call last):\n"
        "  File tests/test_alpha.py:12: in test_one\n"
        "object at 0xabc123 failed after 0.13s\n"
    )
    second = (
        "Traceback (most recent call last):\n"
        "  File tests/test_alpha.py:99: in test_one\n"
        "object at 0xdef456 failed after 0.91s\n"
    )

    assert fingerprint_failures(first) == fingerprint_failures(second)
