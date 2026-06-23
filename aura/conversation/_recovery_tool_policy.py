from __future__ import annotations

import re
from typing import Any

from aura.conversation.path_utils import normalize_worker_path as _normalize_worker_path
from aura.conversation.tool_limits import WRITE_TOOLS
from aura.conversation.terminal_syntax import py_compile_targets

WORKER_RECOVERY_ALWAYS_ALLOWED = {
    "read_file",
    "read_files",
    "read_file_range",
    "read_file_outline",
    "grep_search",
    "find_usages",
    "search_codebase",
    "list_directory",
    "glob",
    "git_status",
    "git_diff",
    "git_log",
    "git_show",
    "git_log_file",
    "run_diagnostic_command",
    "get_workspace_snapshot",
}

SYNTAX_REPAIR_ALWAYS_ALLOWED = WORKER_RECOVERY_ALWAYS_ALLOWED


def syntax_repair_tool_allowed(
    name: str,
    args: dict[str, Any],
    syntax_paths: set[str],
) -> bool:
    if name in SYNTAX_REPAIR_ALWAYS_ALLOWED:
        return True
    if name in WRITE_TOOLS:
        return _normalize_worker_path(str(args.get("path", ""))) in syntax_paths
    if name == "run_terminal_command":
        command = str(args.get("command", ""))
        # py_compile targeting a broken file
        if re.search(
            r"(?i)(?:^|[;&|]\s*)"
            r"(?:(?:\"[^\"]*python3?(?:\.exe)?\")|(?:'[^']*python3?(?:\.exe)?')|"
            r"(?:[A-Za-z]:)?[A-Za-z0-9_./\\\-]*python3?(?:\.exe)?|py)"
            r"\s+-m\s+py_compile\b",
            command,
        ):
            targets = py_compile_targets(command)
            return bool(targets) and any(target in syntax_paths for target in targets)
        # pytest targeting a broken file (substring check)
        if re.search(
            r"(?i)(?:^|[;&|]\s*)"
            r"(?:(?:\"[^\"]*python3?(?:\.exe)?\")|(?:'[^']*python3?(?:\.exe)?')|"
            r"(?:[A-Za-z]:)?[A-Za-z0-9_./\\\-]*python3?(?:\.exe)?|py)"
            r"\s+-m\s+pytest\b",
            command,
        ):
            return any(path in command for path in syntax_paths)
        return False
    return False
