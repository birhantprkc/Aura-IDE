import json
import os
import subprocess
import sys


def run(payload: dict) -> dict:
    # Trial run / readiness check — no side effects
    if payload.get("trial_run") or payload.get("readiness"):
        return {"ok": True, "message": "Readiness check passed"}

    workspace_root = payload.get("workspace_root")
    if not workspace_root:
        return {"ok": False, "error": "Missing workspace_root in payload"}

    workspace_root = os.path.abspath(workspace_root)

    # 1. Verify this is a git repo
    result = _git(workspace_root, ["rev-parse", "--git-dir"])
    if result["returncode"] != 0:
        return {
            "ok": False,
            "error": "Not a git repository",
            "details": result["stderr"].strip(),
        }

    # 2. Check working tree status
    result = _git(workspace_root, ["status", "--porcelain"])
    if result["returncode"] != 0:
        return {
            "ok": False,
            "error": "Failed to check git status",
            "details": result["stderr"].strip(),
        }
    changed_files = _parse_status_output(result["stdout"])

    if not changed_files:
        return {"ok": True, "message": "Working tree clean, nothing to commit"}

    # 3. Build commit message
    commit_message = _build_commit_message(changed_files)

    # 4. Stage everything
    result = _git(workspace_root, ["add", "-A"])
    if result["returncode"] != 0:
        return {
            "ok": False,
            "error": "Failed to stage changes",
            "details": result["stderr"].strip(),
        }

    # 5. Commit
    result = _git(workspace_root, ["commit", "-m", commit_message])
    if result["returncode"] != 0:
        return {
            "ok": False,
            "error": "Commit failed",
            "details": result["stderr"].strip(),
        }
    commit_hash = _extract_commit_hash(result["stdout"])

    # 6. Check upstream and push
    branch = _get_current_branch(workspace_root)
    upstream_remote = _get_upstream_remote(workspace_root, branch)

    if upstream_remote is None:
        # Check if origin exists
        origin_result = _git(workspace_root, ["remote", "get-url", "origin"])
        if origin_result["returncode"] != 0:
            return {
                "ok": False,
                "error": "No remote 'origin' configured",
                "details": "No remote named 'origin' exists. Configure a remote first.",
            }
        # Set upstream and push
        result = _git(workspace_root, ["push", "-u", "origin", branch])
    else:
        result = _git(workspace_root, ["push"])

    if result["returncode"] != 0:
        return {
            "ok": False,
            "error": "Push failed",
            "details": result["stderr"].strip(),
        }

    return {
        "ok": True,
        "message": f"Pushed {len(changed_files)} changed file(s) to {branch}",
        "commit_hash": commit_hash,
        "branch": branch,
        "changed_files": changed_files,
        "push_output": result["stdout"].strip(),
    }


def _git(workspace_root: str, args: list[str]) -> dict:
    """Run a git command and return the result."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=workspace_root,
            timeout=30,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": -1,
            "stdout": exc.stdout if exc.stdout else "",
            "stderr": exc.stderr if exc.stderr else "Command timed out after 30s",
        }
    except FileNotFoundError:
        return {
            "returncode": -2,
            "stdout": "",
            "stderr": "git command not found. Is git installed?",
        }
    except Exception as exc:
        return {
            "returncode": -3,
            "stdout": "",
            "stderr": str(exc),
        }


def _parse_status_output(status_output: str) -> list[str]:
    """Parse git status --porcelain output into a list of file paths."""
    files: list[str] = []
    for line in status_output.splitlines():
        line = line.rstrip("\n")
        if not line:
            continue
        # Porcelain format: XY FILENAME or XY -> FILENAME for renames
        # The filename starts after the first two status chars + space
        entry = line[3:]
        # Handle renames: "R  old -> new"
        if " -> " in entry:
            entry = entry.split(" -> ")[-1]
        files.append(entry)
    return files


def _build_commit_message(changed_files: list[str]) -> str:
    """Generate a descriptive commit message from the changed file list."""
    lines: list[str] = []
    # First line: summary
    if len(changed_files) == 1:
        lines.append(f"Update {changed_files[0]}")
    else:
        lines.append(f"Update {len(changed_files)} files")
    # Blank line
    lines.append("")
    # Bullet list of changed files
    for path in changed_files:
        lines.append(f"- {path}")
    return "\n".join(lines)


def _extract_commit_hash(commit_output: str) -> str:
    """Extract the abbreviated commit hash from git commit output."""
    for line in commit_output.splitlines():
        if line.startswith("["):
            # Format: [branch hash] message
            parts = line.split()
            if len(parts) >= 2:
                hash_part = parts[1].rstrip("]")
                return hash_part
    return ""


def _get_current_branch(workspace_root: str) -> str:
    """Get the current branch name."""
    result = _git(workspace_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if result["returncode"] == 0:
        return result["stdout"].strip()
    return ""


def _get_upstream_remote(workspace_root: str, branch: str) -> str | None:
    """Get the upstream remote for the given branch, or None."""
    if not branch:
        return None
    result = _git(workspace_root, ["config", f"branch.{branch}.remote"])
    if result["returncode"] == 0:
        remote = result["stdout"].strip()
        return remote if remote else None
    return None


if __name__ == "__main__":
    payload_str = sys.stdin.readline()
    try:
        payload = json.loads(payload_str)
    except (json.JSONDecodeError, TypeError):
        print(json.dumps({"ok": False, "error": "Invalid JSON payload on stdin"}))
        sys.exit(0)

    result = run(payload)
    print(json.dumps(result))
