"""Pure terminal / py_compile parsing helpers extracted from ConversationManager."""
from __future__ import annotations

import re

from aura.conversation.path_utils import normalize_worker_path


def is_py_compile_error(output: str) -> bool:
    """Check if output contains Python-level error markers (py_compile actually ran)."""
    return bool(
        re.search(r'\bFile ".*", line \d+', output)
        and re.search(r"\b(?:SyntaxError|IndentationError|TabError)\b", output)
    )


def is_shell_failure(output: str) -> bool:
    """Check if output indicates a shell-level failure (command never reached py_compile)."""
    shell_markers = [
        "cannot find the path specified",
        "not recognized as an internal or external command",
        "No such file or directory",
        "command not found",
        "not found",
    ]
    output_lower = output.lower()
    for marker in shell_markers:
        if marker in output_lower:
            return True
    first_lines = output.split("\n")[:3]
    for line in first_lines:
        stripped = line.strip()
        if stripped.startswith("cd:") or stripped.startswith("chdir:"):
            return True
    return False


def py_compile_targets(command: str) -> list[str]:
    if "py_compile" not in command:
        return []
    matches = re.findall(
        r"(?<![\w.-])([A-Za-z0-9_./\\:\-]+\.py)(?![\w.-])",
        command,
    )
    targets: list[str] = []
    for match in matches:
        target = normalize_worker_path(match)
        if target.endswith("py_compile.py"):
            continue
        targets.append(target)
    return targets


def normalize_py_compile_path(raw: str) -> str:
    p = raw.strip().replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    return p


def is_python_path(path: str) -> bool:
    return path.replace("\\\\", "/").endswith(".py")
