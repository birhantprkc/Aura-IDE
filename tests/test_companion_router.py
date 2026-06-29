"""Tests for CompanionCommandRouter."""
from __future__ import annotations

from aura.companion.router import CompanionCommandRouter


class TestCompanionCommandRouter:
    """Dispatch logic for companion protocol commands."""

    def test_dispatch_returns_true_for_registered_type(self) -> None:
        router = CompanionCommandRouter()
        handled: list[str] = []

        def handler(msg: dict) -> None:
            handled.append(msg.get("type", ""))

        router.register("test.type", handler)
        result = router.dispatch({"type": "test.type", "payload": {}})

        assert result is True
        assert handled == ["test.type"]

    def test_dispatch_returns_false_for_unknown_type(self) -> None:
        router = CompanionCommandRouter()
        result = router.dispatch({"type": "unknown.type", "payload": {}})
        assert result is False

    def test_handler_receives_correct_message(self) -> None:
        router = CompanionCommandRouter()
        received: list[dict] = []

        def handler(msg: dict) -> None:
            received.append(msg)

        router.register("echo", handler)
        msg = {"type": "echo", "payload": {"value": 42}}
        router.dispatch(msg)

        assert len(received) == 1
        assert received[0] is msg

    def test_register_overwrites_existing_handler(self) -> None:
        router = CompanionCommandRouter()
        calls: list[str] = []

        def first(msg: dict) -> None:
            calls.append("first")

        def second(msg: dict) -> None:
            calls.append("second")

        router.register("dup", first)
        router.register("dup", second)
        router.dispatch({"type": "dup", "payload": {}})

        assert calls == ["second"]

    def test_dispatch_on_empty_router_returns_false(self) -> None:
        router = CompanionCommandRouter()
        assert router.dispatch({"type": "anything", "payload": {}}) is False

    def test_dispatch_handles_empty_type_string(self) -> None:
        router = CompanionCommandRouter()
        assert router.dispatch({"type": "", "payload": {}}) is False
