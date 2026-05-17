"""Tests for the Vertex AI Gemini REST client."""

from __future__ import annotations

import json
from typing import Any

import pytest

from aura.backends.api import APIAgentBackend
from aura.client.events import ContentDelta, Done, ToolCallArgsDelta, ToolCallStart, Usage
from aura.client.gemini import (
    GeminiClient,
    _build_payload,
    _to_vertex_contents,
    _to_vertex_tools,
)


def test_api_backend_uses_vertex_gemini_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-key")

    backend = APIAgentBackend(provider="google")

    assert isinstance(backend.client, GeminiClient)


def test_google_api_key_env_does_not_depend_on_aiza_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "AQ-test-key")

    client = GeminiClient()

    assert client.is_express_mode
    assert client._method_url("gemini-2.5-flash", "generateContent").endswith(
        "/v1/publishers/google/models/gemini-2.5-flash:generateContent?key=AQ-test-key"
    )


def test_to_vertex_contents_translates_history_and_tool_results() -> None:
    messages = [
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "Use the tool."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"a.py"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"ok":true}'},
    ]

    system, contents = _to_vertex_contents(messages)

    assert system == {"role": "system", "parts": [{"text": "You are concise."}]}
    assert contents == [
        {"role": "user", "parts": [{"text": "Use the tool."}]},
        {
            "role": "model",
            "parts": [
                {
                    "functionCall": {
                        "name": "read_file",
                        "args": {"path": "a.py"},
                    }
                }
            ],
        },
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "read_file",
                        "response": {"ok": True},
                    }
                }
            ],
        },
    ]


def test_to_vertex_tools_uses_rest_camel_case_schema() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]

    assert _to_vertex_tools(tools) == [
        {
            "functionDeclarations": [
                {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                }
            ]
        }
    ]


def test_build_payload_uses_vertex_rest_field_names() -> None:
    payload = _build_payload(
        messages=[
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "hello"},
        ],
        tools=[
            {
                "type": "function",
                "function": {"name": "read_file", "parameters": {"type": "object"}},
            }
        ],
        thinking="high",
        temperature=0.25,
    )

    assert payload["systemInstruction"] == {
        "role": "system",
        "parts": [{"text": "Be brief."}],
    }
    assert payload["generationConfig"] == {
        "temperature": 0.25,
        "candidateCount": 1,
        "thinkingConfig": {"thinkingLevel": "HIGH"},
    }
    assert payload["toolConfig"] == {"functionCallingConfig": {"mode": "AUTO"}}
    assert "system_instruction" not in payload
    assert "tool_config" not in payload


def test_gemini_stream_yields_text_tool_calls_usage_and_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-key")
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def iter_lines(self) -> list[str]:
            chunks = [
                {
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "Hi"}]},
                        }
                    ]
                },
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "functionCall": {
                                            "name": "read_file",
                                            "args": {"path": "a.py"},
                                        }
                                    }
                                ]
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 10,
                        "cachedContentTokenCount": 4,
                        "candidatesTokenCount": 3,
                    },
                },
            ]
            lines: list[str] = []
            for chunk in chunks:
                lines.extend([f"data: {json.dumps(chunk)}", ""])
            return lines

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> FakeResponse:
            captured["method"] = method
            captured["url"] = url
            captured["kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr("aura.client.gemini.httpx.Client", FakeClient)

    events = list(
        GeminiClient().stream(
            messages=[{"role": "user", "content": "hello"}],
            tools=[
                {
                    "type": "function",
                    "function": {"name": "read_file", "parameters": {"type": "object"}},
                }
            ],
            model="gemini-2.0-flash",
            thinking="off",
            temperature=0.25,
        )
    )

    assert captured["method"] == "POST"
    assert captured["url"].endswith(
        "/v1/publishers/google/models/gemini-2.0-flash:"
        "streamGenerateContent?alt=sse&key=AIza-test-key"
    )
    assert "Authorization" not in captured["kwargs"]["headers"]
    body = captured["kwargs"]["json"]
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]
    assert body["generationConfig"] == {"temperature": 0.25, "candidateCount": 1}
    assert body["toolConfig"] == {"functionCallingConfig": {"mode": "AUTO"}}

    assert any(isinstance(ev, ContentDelta) and ev.text == "Hi" for ev in events)
    assert any(isinstance(ev, ToolCallStart) and ev.name == "read_file" for ev in events)
    assert any(
        isinstance(ev, ToolCallArgsDelta) and ev.args_chunk == '{"path": "a.py"}'
        for ev in events
    )
    assert any(
        isinstance(ev, Usage)
        and ev.prompt_tokens == 10
        and ev.cache_hit_tokens == 4
        and ev.cache_miss_tokens == 6
        and ev.completion_tokens == 3
        for ev in events
    )
    done = next(ev for ev in events if isinstance(ev, Done))
    assert done.finish_reason == "tool_calls"
    assert done.full_message["content"] == "Hi"
    assert done.full_message["tool_calls"][0]["function"] == {
        "name": "read_file",
        "arguments": '{"path": "a.py"}',
    }


def test_standard_vertex_url_uses_project_location_and_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = GeminiClient(api_key="test-project")
    client.location = "europe-west4"
    monkeypatch.setattr(client, "_get_access_token", lambda: "token-123")

    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def iter_lines(self) -> list[str]:
            return []

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> FakeResponse:
            captured["url"] = url
            captured["headers"] = kwargs["headers"]
            return FakeResponse()

    monkeypatch.setattr("aura.client.gemini.httpx.Client", FakeClient)

    list(client.stream([], None, "models/gemini-2.5-flash", "off"))

    assert captured["url"].endswith(
        "/v1/projects/test-project/locations/europe-west4/"
        "publishers/google/models/gemini-2.5-flash:streamGenerateContent?alt=sse"
    )
    assert captured["headers"]["Authorization"] == "Bearer token-123"
