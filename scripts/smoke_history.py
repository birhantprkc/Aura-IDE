"""Smoke 3: unit test for History.for_api() — the multi-turn replay rule.

Required behavior:
- Assistant message with tool_calls keeps reasoning_content on the way out.
- Assistant message without tool_calls strips reasoning_content.
- User/tool/system messages pass through.
"""
from __future__ import annotations

import sys

from aura.conversation.history import History

FAILURES: list[str] = []


def expect(label: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}{(' — ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(label)


def main() -> int:
    h = History()
    h.set_system("you are aura")

    # Turn 1: user asks something that triggers a tool call.
    h.append_user_text("read README.md")
    h.append_assistant(
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "I should call read_file.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"README.md"}'},
                }
            ],
        }
    )
    h.append_tool_result("call_1", '{"ok": true, "content": "hi"}')

    # Turn 2 (still same logical user turn): assistant answers with no tool_calls.
    h.append_assistant(
        {
            "role": "assistant",
            "content": "It says 'hi'.",
            "reasoning_content": "the file says hi",
        }
    )

    # New user turn — no tool call this time.
    h.append_user_text("thanks")
    h.append_assistant(
        {
            "role": "assistant",
            "content": "you're welcome",
            "reasoning_content": "polite reply",
        }
    )

    api_msgs = h.for_api()

    # System present.
    expect("system first", api_msgs[0]["role"] == "system" and api_msgs[0]["content"] == "you are aura")

    # Locate the tool_calls assistant message.
    tool_call_msgs = [m for m in api_msgs if m["role"] == "assistant" and m.get("tool_calls")]
    expect("one tool_calls assistant msg", len(tool_call_msgs) == 1)
    if tool_call_msgs:
        tcm = tool_call_msgs[0]
        expect(
            "tool_calls msg keeps reasoning_content",
            tcm.get("reasoning_content") == "I should call read_file.",
            detail=str(tcm),
        )

    # Locate the no-tool-call assistant messages.
    plain_msgs = [m for m in api_msgs if m["role"] == "assistant" and not m.get("tool_calls")]
    expect("two plain assistant msgs", len(plain_msgs) == 2)
    for pm in plain_msgs:
        expect(
            f"plain assistant strips reasoning_content (content={pm.get('content')!r})",
            "reasoning_content" not in pm,
            detail=str(pm),
        )

    # Tool message preserved.
    tool_msgs = [m for m in api_msgs if m["role"] == "tool"]
    expect(
        "tool result preserved",
        len(tool_msgs) == 1 and tool_msgs[0]["tool_call_id"] == "call_1",
    )

    # Round-trip: storage still has reasoning_content for the plain assistant
    # (we never lose it from local history).
    stored_plain = [m for m in h.messages if m["role"] == "assistant" and not m.get("tool_calls")]
    expect(
        "storage retains reasoning_content for plain assistants",
        all(m.get("reasoning_content") for m in stored_plain),
    )

    print("\n-- summary --")
    if FAILURES:
        print(f"FAIL ({len(FAILURES)}): {FAILURES}")
        return 1
    print("All history tests PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
