"""Vertex AI Gemini REST client for Aura's API backend."""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Iterator
from typing import Any

import httpx

try:
    import google.auth
    import google.auth.transport.requests

    HAS_GOOGLE_AUTH = True
except ImportError:
    HAS_GOOGLE_AUTH = False

from aura.client.events import (
    ApiError,
    ContentDelta,
    Done,
    Event,
    ReasoningDelta,
    ToolCallArgsDelta,
    ToolCallEnd,
    ToolCallStart,
    Usage,
)
from aura.config import ThinkingMode

logger = logging.getLogger(__name__)

_API_VERSION = "v1"
_MODEL_LIST_API_VERSION = "v1beta1"
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_DEFAULT_LOCATION = "us-central1"


class GeminiClient:
    """Client for Gemini models through the Vertex AI REST API.

    The client supports both full Vertex AI authentication with Application
    Default Credentials and Vertex AI express mode API keys.
    """

    def __init__(self, api_key: str | None = None) -> None:
        env_name, env_credential = _first_env_with_name(
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_CLOUD_PROJECT",
            "GCP_PROJECT",
        )
        credential = api_key if api_key is not None else env_credential
        if api_key is not None:
            credential_kind = _classify_google_credential(credential)
        elif env_name in {"GOOGLE_API_KEY", "GEMINI_API_KEY"}:
            credential_kind = "api_key"
        else:
            credential_kind = _classify_google_credential(credential)

        self._api_key = credential if credential_kind == "api_key" else None
        self.project = credential if credential_kind == "project" else None
        self.location = _first_env(
            "GOOGLE_CLOUD_LOCATION",
            "GCP_LOCATION",
            "GCP_REGION",
        ) or _DEFAULT_LOCATION

        if self.project and ":" in self.project:
            self.project, self.location = self.project.split(":", 1)

    @property
    def is_express_mode(self) -> bool:
        return self._api_key is not None

    def list_models(self) -> list[str]:
        """Fetch model IDs available from the publisher model catalogue."""
        return [m["id"] for m in self.fetch_raw_models() if m.get("id")]

    def fetch_raw_models(self) -> list[dict[str, Any]]:
        """Fetch raw publisher model metadata from Vertex AI Model Garden."""
        try:
            token = None if self.is_express_mode else self._get_access_token()
        except Exception as exc:
            logger.error("Vertex AI auth error during model discovery: %s", exc)
            return []

        params: dict[str, Any] = {
            "pageSize": 1000,
            "view": "PUBLISHER_MODEL_VIEW_BASIC",
        }
        if self._api_key:
            params["key"] = self._api_key

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = (
            f"https://{self._service_endpoint()}/{_MODEL_LIST_API_VERSION}/"
            "publishers/google/models"
        )

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.error("Vertex AI model discovery failed: %s", exc)
            return []

        models = data.get("publisherModels") or data.get("models") or []
        results: list[dict[str, Any]] = []
        for raw in models:
            if not isinstance(raw, dict):
                continue
            model_id = _model_id(raw)
            if not model_id or not model_id.startswith("gemini-"):
                continue
            item = dict(raw)
            item["id"] = model_id
            item.setdefault("name", raw.get("name") or f"publishers/google/models/{model_id}")
            results.append(item)
        results.sort(key=lambda item: item["id"])
        return results

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
        thinking: ThinkingMode,
        cancel_event: threading.Event | None = None,
        temperature: float = 0.7,
    ) -> Iterator[Event]:
        """Stream a Gemini response as Aura event objects."""
        if cancel_event is not None and cancel_event.is_set():
            yield ApiError(status_code=None, message="Cancelled.")
            return

        try:
            token = None if self.is_express_mode else self._get_access_token()
            url = self._method_url(model, "streamGenerateContent", alt_sse=True)
        except Exception as exc:
            yield ApiError(status_code=None, message=f"Vertex AI authentication error: {exc}")
            return

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload = _build_payload(messages, tools or [], thinking, temperature)
        logger.info(
            "Vertex AI Gemini request to %s using %s auth",
            url.split("?", 1)[0],
            "API key" if self.is_express_mode else "ADC",
        )

        content_buf: list[str] = []
        reasoning_buf: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage: dict[str, int] | None = None

        try:
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0, read=None)) as client:
                with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code >= 400:
                        yield ApiError(
                            status_code=response.status_code,
                            message=_redact_secret(response.read().decode("utf-8", "replace"), self._api_key),
                        )
                        return

                    for chunk in _iter_sse_json(response):
                        if cancel_event is not None and cancel_event.is_set():
                            break

                        if chunk.get("usageMetadata"):
                            usage = _usage_from_metadata(chunk["usageMetadata"])

                        candidates = chunk.get("candidates") or []
                        if not candidates:
                            block_reason = (chunk.get("promptFeedback") or {}).get("blockReason")
                            if block_reason:
                                yield ApiError(
                                    status_code=None,
                                    message=f"Gemini blocked the prompt: {block_reason}",
                                )
                                return
                            continue

                        candidate = candidates[0]
                        finish_reason = _map_finish_reason(
                            candidate.get("finishReason"),
                            finish_reason,
                        )
                        for part in (candidate.get("content") or {}).get("parts") or []:
                            if not isinstance(part, dict):
                                continue

                            text = part.get("text")
                            if isinstance(text, str) and text:
                                if part.get("thought"):
                                    reasoning_buf.append(text)
                                    yield ReasoningDelta(text)
                                else:
                                    content_buf.append(text)
                                    yield ContentDelta(text)

                            function_call = part.get("functionCall")
                            if isinstance(function_call, dict):
                                idx = len(tool_calls)
                                name = str(function_call.get("name") or "")
                                args = function_call.get("args") or {}
                                args_json = json.dumps(args, ensure_ascii=False)
                                tool_call = {
                                    "id": f"gemini_call_{idx}",
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": args_json,
                                    },
                                }
                                tool_calls[idx] = tool_call
                                yield ToolCallStart(index=idx, id=tool_call["id"], name=name)
                                yield ToolCallArgsDelta(index=idx, args_chunk=args_json)
        except httpx.HTTPStatusError as exc:
            yield ApiError(
                status_code=exc.response.status_code,
                message=_redact_secret(str(exc), self._api_key),
            )
            return
        except Exception as exc:
            yield ApiError(
                status_code=None,
                message=_redact_secret(f"{type(exc).__name__}: {exc}", self._api_key),
            )
            return

        for idx in sorted(tool_calls):
            yield ToolCallEnd(index=idx)

        if usage is not None:
            yield Usage(**usage)

        full_message: dict[str, Any] = {
            "role": "assistant",
            "content": "".join(content_buf),
        }
        if reasoning_buf:
            full_message["reasoning_content"] = "".join(reasoning_buf)
        if tool_calls:
            full_message["tool_calls"] = [tool_calls[idx] for idx in sorted(tool_calls)]
            finish_reason = "tool_calls"

        yield Done(finish_reason=finish_reason, full_message=full_message)

    def _get_access_token(self) -> str:
        if not HAS_GOOGLE_AUTH:
            raise RuntimeError("google-auth is required for Vertex AI ADC authentication.")

        credentials, project = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
        if not self.project:
            self.project = project
        if not self.project:
            raise RuntimeError(
                "No Google Cloud project configured. Set GOOGLE_CLOUD_PROJECT "
                "or store a project ID for the Google provider."
            )

        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        return credentials.token

    def _method_url(self, model: str, method: str, *, alt_sse: bool = False) -> str:
        model_path = self._model_path(model)
        url = f"https://{self._service_endpoint()}/{_API_VERSION}/{model_path}:{method}"
        params: list[str] = []
        if alt_sse:
            params.append("alt=sse")
        if self._api_key:
            params.append(f"key={self._api_key}")
        if params:
            url = f"{url}?{'&'.join(params)}"
        return url

    def _model_path(self, model: str) -> str:
        normalized = _normalize_model_name(model)
        if normalized.startswith("projects/"):
            return normalized

        publisher_model = (
            normalized
            if normalized.startswith("publishers/")
            else f"publishers/google/models/{normalized}"
        )
        if self.is_express_mode:
            return publisher_model
        if not self.project:
            raise RuntimeError("No Google Cloud project configured for Vertex AI.")
        return f"projects/{self.project}/locations/{self.location}/{publisher_model}"

    def _service_endpoint(self) -> str:
        if self.is_express_mode or self.location == "global":
            return "aiplatform.googleapis.com"
        return f"{self.location}-aiplatform.googleapis.com"


def _build_payload(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    thinking: ThinkingMode,
    temperature: float,
) -> dict[str, Any]:
    system_instruction, contents = _to_vertex_contents(messages)
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": _generation_config(thinking, temperature),
    }
    if system_instruction is not None:
        payload["systemInstruction"] = system_instruction

    vertex_tools = _to_vertex_tools(tools)
    if vertex_tools:
        payload["tools"] = vertex_tools
        payload["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
    return payload


def _to_vertex_contents(
    messages: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    system_parts: list[dict[str, Any]] = []
    contents: list[dict[str, Any]] = []
    tool_names_by_id: dict[str, str] = {}

    for msg in messages:
        role = msg.get("role")
        parts = _content_parts(msg.get("content"))

        if role == "system":
            system_parts.extend(part for part in parts if "text" in part)
            continue

        if role == "assistant":
            model_parts = list(parts)
            for tc in msg.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                if not isinstance(fn, dict):
                    continue
                name = str(fn.get("name") or "")
                call_id = str(tc.get("id") or "")
                if call_id and name:
                    tool_names_by_id[call_id] = name
                model_parts.append(
                    {
                        "functionCall": {
                            "name": name,
                            "args": _json_object(fn.get("arguments")),
                        }
                    }
                )
            contents.append({"role": "model", "parts": model_parts or [{"text": ""}]})
            continue

        if role == "tool":
            call_id = str(msg.get("tool_call_id") or "")
            name = str(msg.get("name") or tool_names_by_id.get(call_id) or "tool")
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": name,
                                "response": _tool_response(msg.get("content")),
                            }
                        }
                    ],
                }
            )
            continue

        if role == "user":
            contents.append({"role": "user", "parts": parts or [{"text": ""}]})

    system_instruction = (
        {"role": "system", "parts": system_parts} if system_parts else None
    )
    return system_instruction, contents


def _content_parts(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"text": content}] if content else []
    if not isinstance(content, list):
        return []

    parts: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str) and text:
                parts.append({"text": text})
            continue
        if item.get("type") == "image_url":
            image_url = item.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if isinstance(url, str):
                image_part = _image_url_part(url)
                if image_part:
                    parts.append(image_part)
    return parts


def _image_url_part(url: str) -> dict[str, Any] | None:
    if url.startswith("data:") and "," in url:
        header, data = url.split(",", 1)
        mime_type = header.split(":", 1)[1].split(";", 1)[0]
        return {"inlineData": {"mimeType": mime_type, "data": data}}
    if url.startswith(("gs://", "http://", "https://")):
        return {"fileData": {"mimeType": "image/jpeg", "fileUri": url}}
    return None


def _to_vertex_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") or {}
        if not isinstance(fn, dict) or not fn.get("name"):
            continue
        declaration = {
            "name": str(fn["name"]),
            "description": str(fn.get("description") or ""),
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
        }
        declarations.append(declaration)
    return [{"functionDeclarations": declarations}] if declarations else []


def _generation_config(thinking: ThinkingMode, temperature: float) -> dict[str, Any]:
    config: dict[str, Any] = {
        "temperature": temperature,
        "candidateCount": 1,
    }
    if thinking == "high":
        config["thinkingConfig"] = {"thinkingLevel": "HIGH"}
    elif thinking == "max":
        config["thinkingConfig"] = {"thinkingBudget": 8192}
    return config


def _iter_sse_json(response: httpx.Response) -> Iterator[dict[str, Any]]:
    data_lines: list[str] = []
    for line in response.iter_lines():
        if not line:
            yield from _flush_sse_json(data_lines)
            continue
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
    yield from _flush_sse_json(data_lines)


def _flush_sse_json(data_lines: list[str]) -> Iterator[dict[str, Any]]:
    if not data_lines:
        return
    data = "\n".join(data_lines)
    data_lines.clear()
    if data == "[DONE]":
        return
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return
    if isinstance(parsed, dict):
        yield parsed


def _usage_from_metadata(raw: dict[str, Any]) -> dict[str, int]:
    prompt_tokens = int(raw.get("promptTokenCount") or 0)
    cache_hit_tokens = int(raw.get("cachedContentTokenCount") or 0)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": int(raw.get("candidatesTokenCount") or 0),
        "cache_hit_tokens": cache_hit_tokens,
        "cache_miss_tokens": max(0, prompt_tokens - cache_hit_tokens),
    }


def _map_finish_reason(raw: Any, current: str | None) -> str | None:
    if not raw:
        return current
    mapping = {
        "STOP": "stop",
        "MAX_TOKENS": "length",
        "SAFETY": "content_filter",
        "BLOCKLIST": "content_filter",
        "PROHIBITED_CONTENT": "content_filter",
        "MALFORMED_FUNCTION_CALL": "tool_calls",
        "UNEXPECTED_TOOL_CALL": "tool_calls",
        "TOO_MANY_TOOL_CALLS": "tool_calls",
    }
    return mapping.get(str(raw).upper(), str(raw).lower())


def _normalize_model_name(model: str) -> str:
    name = model.strip()
    return name.removeprefix("models/")


def _model_id(raw: dict[str, Any]) -> str:
    name = str(raw.get("name") or raw.get("baseModelId") or "")
    if "/models/" in name:
        return name.rsplit("/models/", 1)[1]
    return name.removeprefix("models/")


def _json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _tool_response(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {"result": content}
        return parsed if isinstance(parsed, dict) else {"result": parsed}
    return {"result": content}


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _first_env_with_name(*names: str) -> tuple[str | None, str | None]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return name, value
    return None, None


def _classify_google_credential(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("AIza"):
        return "api_key"
    project = value.split(":", 1)[0]
    if _looks_like_google_project_id(project):
        return "project"
    return "api_key"


def _looks_like_google_project_id(value: str) -> bool:
    if len(value) < 6 or len(value) > 30:
        return False
    if not value[0].islower():
        return False
    if value.endswith("-"):
        return False
    return all(ch.islower() or ch.isdigit() or ch == "-" for ch in value)


def _redact_secret(message: str, secret: str | None) -> str:
    if not secret:
        return message
    return message.replace(secret, "[REDACTED]")
