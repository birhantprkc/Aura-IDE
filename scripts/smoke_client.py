"""Smoke 1: streaming hello-world with and without thinking.

Expected:
- thinking off: no reasoning text, content arrives.
- thinking high: non-empty reasoning text, then content arrives.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from aura.client import (
    ApiError,
    ContentDelta,
    DeepSeekClient,
    Done,
    ReasoningDelta,
    Usage,
)


def run_one(label: str, thinking: str) -> bool:
    print(f"\n=== {label} (thinking={thinking}) ===", flush=True)
    client = DeepSeekClient()
    messages = [
        {"role": "user", "content": "Reply with exactly: 'pong'. Nothing else."}
    ]
    reasoning_chars = 0
    content_chars = 0
    error: ApiError | None = None
    finish: str | None = None
    for ev in client.stream(
        messages=messages, tools=None, model="deepseek-v4-flash", thinking=thinking
    ):
        if isinstance(ev, ReasoningDelta):
            reasoning_chars += len(ev.text)
            sys.stdout.write(f"\033[90m{ev.text}\033[0m")
            sys.stdout.flush()
        elif isinstance(ev, ContentDelta):
            content_chars += len(ev.text)
            sys.stdout.write(ev.text)
            sys.stdout.flush()
        elif isinstance(ev, Usage):
            print(
                f"\n  usage: prompt={ev.prompt_tokens} completion={ev.completion_tokens} "
                f"cache_hit={ev.cache_hit_tokens} cache_miss={ev.cache_miss_tokens}"
            )
        elif isinstance(ev, Done):
            finish = ev.finish_reason
            print(
                f"\n  done: finish_reason={ev.finish_reason} "
                f"reasoning_chars={reasoning_chars} content_chars={content_chars}"
            )
        elif isinstance(ev, ApiError):
            error = ev
            print(f"\n  ERROR: status={ev.status_code} {ev.message}")

    if error is not None:
        return False
    if thinking == "off" and reasoning_chars > 0:
        print("  FAIL: thinking=off should produce no reasoning_content")
        return False
    if thinking != "off" and reasoning_chars == 0:
        print("  FAIL: thinking=high should produce reasoning_content")
        return False
    if content_chars == 0:
        print("  FAIL: empty content")
        return False
    print(f"  PASS ({finish})")
    return True


def main() -> int:
    ok1 = run_one("baseline", "off")
    ok2 = run_one("thinking-high", "high")
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())
