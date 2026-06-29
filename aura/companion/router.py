"""CompanionCommandRouter — plain-Python command dispatch with no Qt."""
from __future__ import annotations

from typing import Callable


class CompanionCommandRouter:
    """Simple registry-based router for companion protocol commands.

    Usage::
        router = CompanionCommandRouter()
        router.register("project.list_recent", handler)
        if router.dispatch(msg):
            return  # handled
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict], None]] = {}

    def register(self, msg_type: str, handler: Callable[[dict], None]) -> None:
        """Register a handler for the given message type.

        If a handler was already registered for this type, it is overwritten.
        """
        self._handlers[msg_type] = handler

    def dispatch(self, msg: dict) -> bool:
        """Look up *msg*'s type and call the registered handler.

        Returns True if a handler was found and called, False otherwise.
        """
        handler = self._handlers.get(msg.get("type", ""))
        if handler is None:
            return False
        handler(msg)
        return True
