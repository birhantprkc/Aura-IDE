"""APIAgentBackend for native and OpenAI-compatible API providers."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

from aura.backends.base import AgentBackend
from aura.client.events import Event
from aura.client.deepseek import DeepSeekClient
from aura.client.gemini import GeminiClient
from aura.config import ProviderId, ThinkingMode


class APIAgentBackend(AgentBackend):
    """Agent backend for API providers.

    Google Gemini uses the native Gemini REST API. The other API providers use
    the existing OpenAI-compatible DeepSeekClient wrapper.
    """

    def __init__(self, provider: ProviderId = "deepseek") -> None:
        self._client = (
            GeminiClient()
            if provider == "google"
            else DeepSeekClient(provider=provider)
        )

    @property
    def client(self) -> DeepSeekClient | GeminiClient:
        """Access the underlying provider client."""
        return self._client

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        thinking: ThinkingMode,
        cancel_event: threading.Event | None = None,
        temperature: float = 0.7,
    ) -> Iterator[Event]:
        return self._client.stream(
            messages=messages,
            tools=tools,
            model=model,
            thinking=thinking,
            cancel_event=cancel_event,
            temperature=temperature,
        )
