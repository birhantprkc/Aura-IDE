from __future__ import annotations

_OBSERVATIONAL_VERBS = frozenset({
    "read", "get", "list", "search", "fetch", "check",
    "monitor", "show", "find", "status", "diff", "log",
})

_SIDE_EFFECTING_VERBS = frozenset({
    "send", "post", "publish", "submit", "create", "write",
    "edit", "delete", "remove", "update", "buy", "purchase",
    "transfer", "install", "connect", "deploy", "merge",
    "push", "exec",
})


def is_consequential(tool_name: str, schema: dict | None = None) -> bool:
    """Heuristic: return True if the tool is likely side-effecting.

    Observational verbs (read, get, list, search, ...) → not consequential.
    Side-effecting verbs (send, create, delete, ...) → consequential.
    Unrecognised first-word → consequential (fail-safe: ask rather than act).

    This is a heuristic floor; capability bindings may later carry explicit
    consequential tool names that override it.
    """
    first_word = tool_name.split("_")[0].lower()
    if first_word in _OBSERVATIONAL_VERBS:
        return False
    if first_word in _SIDE_EFFECTING_VERBS:
        return True
    # Unrecognised → fail-safe (consequential)
    return True
