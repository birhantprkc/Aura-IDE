"""Post-write verification — compile check without bytecode residue."""

from __future__ import annotations

import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


def py_compile_check(path: Path) -> tuple[bool, str]:
    """Compile *path* with ``py_compile``.  Returns ``(ok, error_message)``.

    Uses a temporary directory for bytecode output to avoid leaving ``.pyc``
    files behind.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            py_compile.compile(
                str(path),
                cfile=str(Path(tmpdir) / "check.pyc"),
                doraise=True,
            )
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def import_resolves(module_path: str, workspace_root: Path) -> tuple[bool, str]:
    """Verify *module_path* can be imported in a fresh subprocess.

    Spawns ``sys.executable -c "import <module_path>"`` with
    *workspace_root* on PYTHONPATH.  Returns ``(ok, error_message)``.
    """
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(workspace_root) + (os.pathsep + existing if existing else "")
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", f"import {module_path}"],
            cwd=str(workspace_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "import resolution timed out (30s)"
    except OSError as exc:
        return False, f"import resolution subprocess error: {exc}"

    if proc.returncode == 0:
        return True, ""

    # Last ~40 lines of stderr (traceback tail)
    stderr_lines = proc.stderr.splitlines()
    tail = stderr_lines[-40:] if len(stderr_lines) > 40 else stderr_lines
    return False, "\n".join(tail)
