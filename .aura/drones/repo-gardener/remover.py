"""Pure import-removal logic. No disk I/O."""

from __future__ import annotations

import re
from pathlib import Path


def _bound_name(name_str: str) -> str:
    """Extract the bound name from an import name entry.

    ``"os"`` → ``"os"``,  ``"os as operating_system"`` → ``"operating_system"``.
    """
    if " as " in name_str:
        return name_str.split(" as ", 1)[1].strip()
    return name_str.strip()


def strip_import(source: str, binding: str, line: int) -> str:
    """Remove exactly ONE imported *binding* from *source* at *line* (1-based).

    Handles::

        import x                     → line removed
        import x as y                → line removed
        from x import a              → line removed
        from x import a, b, c        → ``b`` removed → ``from x import a, c``
        from x import a as y, b      → ``a as y`` removed → ``from x import b``
        from x import (              → multi-line paren form; the line with the
            a,                           binding is removed, commas cleaned up
            b,
        )

    Preserves all other lines byte-for-byte.  Never removes more than one binding.
    If *binding* is not found at *line*, returns source unchanged.
    """
    lines = source.splitlines(keepends=True)
    lineno = line - 1  # 0-based

    if lineno < 0 or lineno >= len(lines):
        return source

    raw = lines[lineno].rstrip("\r\n")

    # -- Detect multi-line parenthesized import ------------------------------
    if "(" in raw and ")" not in raw:
        return _strip_multi_import(lines, lineno, binding)

    # -- Single-line import ---------------------------------------------------
    return _strip_single_import(lines, lineno, binding)


def _strip_single_import(
    lines: list[str], lineno: int, binding: str,
) -> str:
    raw = lines[lineno]
    stripped = raw.strip()

    # --- case: ``import foo`` or ``import foo as bar`` -----------------------
    m = re.match(r"^import\s+", stripped)
    if m and not stripped.startswith("from "):
        after = stripped[m.end():]
        names = [n.strip() for n in after.split(",")]

        bound_names = [_bound_name(n) for n in names]
        if binding not in bound_names:
            return "".join(lines)

        idx = bound_names.index(binding)
        names.pop(idx)

        if not names:
            del lines[lineno]
            return "".join(lines)

        leading = raw[: len(raw) - len(raw.lstrip())]
        new_line = leading + "import " + ", ".join(names)
        if raw.endswith("\r\n"):
            new_line += "\r\n"
        elif raw.endswith("\n"):
            new_line += "\n"
        lines[lineno] = new_line
        return "".join(lines)

    # --- case: ``from x import a, b, c`` or ``from x import a as y`` ---------
    if stripped.startswith("from ") and " import " in stripped:
        before, after = stripped.split(" import ", 1)
        from_module = before.split("from ", 1)[1].strip()

        # Handle single-line parenthesised:  from x import (a, b)
        after = after.strip()
        if after.startswith("(") and after.endswith(")"):
            after = after[1:-1].strip()

        names = [n.strip() for n in after.split(",")]

        bound_names = [_bound_name(n) for n in names]
        if binding not in bound_names:
            return "".join(lines)

        idx = bound_names.index(binding)
        names.pop(idx)

        if not names:
            del lines[lineno]
            return "".join(lines)

        leading = raw[: len(raw) - len(raw.lstrip())]
        new_line = leading + f"from {from_module} import {', '.join(names)}"
        if raw.endswith("\r\n"):
            new_line += "\r\n"
        elif raw.endswith("\n"):
            new_line += "\n"
        lines[lineno] = new_line
        return "".join(lines)

    return "".join(lines)


def _strip_multi_import(
    lines: list[str], lineno: int, binding: str,
) -> str:
    """Handle parenthesised multi-line ``from x import ( ... )``."""

    # --- find closing paren --------------------------------------------------
    depth = 0
    end_idx = lineno
    for i in range(lineno, len(lines)):
        for ch in lines[i]:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
        if depth == 0:
            end_idx = i
            break
    else:
        return "".join(lines)  # unbalanced — leave alone

    first_raw = lines[lineno].rstrip("\r\n")
    stripped = first_raw.strip()

    if not (stripped.startswith("from ") and " import " in stripped):
        return "".join(lines)

    before, after = stripped.split(" import ", 1)
    from_module = before.split("from ", 1)[1].strip()

    # --- collect name lines --------------------------------------------------
    name_lines: list[str] = []
    for i in range(lineno, end_idx + 1):
        content = lines[i].rstrip("\r\n").strip()
        if content == "(" or content == ")":
            continue
        # first line may have ``from x import (`` → grab text after ``(``
        if content.startswith("from ") and " import " in content:
            paren_idx = content.find("(")
            if paren_idx >= 0:
                rest = content[paren_idx + 1:].strip()
                if rest:
                    name_lines.append(rest)
            continue
        if content:
            name_lines.append(content)

    # --- flatten names (each line may have comma-separated items) ------------
    all_entries: list[str] = []
    for nl in name_lines:
        # Remove trailing comma then split
        nl = nl.rstrip(",").strip()
        if nl:
            for part in nl.split(","):
                part = part.strip()
                if part:
                    all_entries.append(part)

    bound_names = [_bound_name(e) for e in all_entries]
    if binding not in bound_names:
        return "".join(lines)

    idx = bound_names.index(binding)
    all_entries.pop(idx)

    if not all_entries:
        del lines[lineno:end_idx + 1]
        return "".join(lines)

    # --- reconstruct ---------------------------------------------------------
    leading = first_raw[: len(first_raw) - len(first_raw.lstrip())]
    inner = leading + "    "

    new_block = [leading + f"from {from_module} import (\n"]
    for entry in all_entries:
        new_block.append(f"{inner}{entry},\n")
    new_block.append(leading + ")\n")

    lines[lineno:end_idx + 1] = new_block
    return "".join(lines)
