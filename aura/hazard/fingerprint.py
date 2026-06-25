from __future__ import annotations

import re


def normalize_error(text: str) -> str:
    t = text.lower()
    # 2. Replace double-quoted substrings
    t = re.sub(r'"[^"]*"', "<str>", t)
    # 3. Replace single-quoted substrings
    t = re.sub(r"'[^']*'", "<str>", t)
    # 4. Replace file paths
    t = re.sub(
        r"(?:[a-z]:[\\/]|[\\/]|\.{1,2}[\\/])[^\s]*\.[a-z]\w*",
        "<path>",
        t,
    )
    # 5. Replace hex literals
    t = re.sub(r"\b0x[0-9a-f]+\b", "<hex>", t)
    # 6. Replace integer/float runs
    t = re.sub(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", "<n>", t)
    # 7. Collapse whitespace and strip
    t = re.sub(r"\s+", " ", t).strip()
    return t


def fingerprint_fields(
    model: str,
    task_kind: str | None,
    failure_class: str | None,
    error_signature: str | None,
) -> str:
    return f"{model}|{task_kind}|{failure_class}|{normalize_error(error_signature or '')}"
