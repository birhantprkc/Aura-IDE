import ast
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class CodeFormatter:
    """Formatter utilizing Ruff + Chameleon Rule.
    Only formats if a ruff configuration exists in the workspace.
    Verifies valid Python before returning.
    """

    def format_code(self, code: str, workspace_root: Path | None = None) -> str:
        if workspace_root is None:
            return code

        config_path = self._find_ruff_config(workspace_root)
        if not config_path:
            return code

        try:
            ast.parse(code)
        except SyntaxError:
            return code

        current_code = code

        # Run ruff check --fix for F401, F841
        try:
            cmd_check = [
                "ruff", "check", "--fix", f"--config={config_path}",
                "--select=F401,F841", "--ignore=F811", "-"
            ]
            proc_check = subprocess.Popen(
                cmd_check, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=workspace_root
            )
            stdout_check, _ = proc_check.communicate(current_code, timeout=30)
            if proc_check.returncode == 0 and stdout_check:
                ast.parse(stdout_check)
                current_code = stdout_check
        except Exception:
            logger.warning("Ruff check failed or produced invalid code")

        # Run ruff format
        try:
            cmd_format = [
                "ruff", "format", f"--config={config_path}", "-"
            ]
            proc_format = subprocess.Popen(
                cmd_format, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=workspace_root
            )
            stdout_format, _ = proc_format.communicate(current_code, timeout=30)
            if proc_format.returncode == 0 and stdout_format:
                ast.parse(stdout_format)
                current_code = stdout_format
        except Exception:
            logger.warning("Ruff format failed or produced invalid code")

        return current_code

    def _find_ruff_config(self, workspace_root: Path) -> Path | None:
        p_dot_ruff = workspace_root / ".ruff.toml"
        if p_dot_ruff.is_file():
            return p_dot_ruff
            
        p_ruff = workspace_root / "ruff.toml"
        if p_ruff.is_file():
            return p_ruff
            
        p_pyproject = workspace_root / "pyproject.toml"
        if p_pyproject.is_file():
            try:
                content = p_pyproject.read_text(encoding="utf-8")
                if "[tool.ruff]" in content:
                    return p_pyproject
            except Exception:
                logger.warning("Failed to read pyproject.toml")
                
        return None
