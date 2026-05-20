import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
from aura.craft.formatter import CodeFormatter

@pytest.fixture
def formatter():
    return CodeFormatter()

def test_chameleon_rule_no_workspace(formatter):
    code = "x=1"
    res = formatter.format_code(code, None)
    assert res == "x=1"

def test_chameleon_rule_no_ruff_config(formatter, tmp_path):
    # tmp_path has no ruff config
    code = "x=1"
    res = formatter.format_code(code, tmp_path)
    assert res == "x=1"

def test_chameleon_rule_ruff_config_found(formatter, tmp_path):
    (tmp_path / "ruff.toml").touch()
    
    code = "x=1"
    
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("x = 1\n", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        
        res = formatter.format_code(code, tmp_path)
        assert res == "x = 1\n"
        assert mock_popen.call_count == 2 # one for check, one for format

def test_invalid_syntax_falls_back(formatter, tmp_path):
    (tmp_path / "ruff.toml").touch()
    
    code = "x = " # invalid
    res = formatter.format_code(code, tmp_path)
    assert res == "x = "

def test_ruff_not_installed_falls_back(formatter, tmp_path):
    (tmp_path / "ruff.toml").touch()
    
    code = "x=1"
    with patch("subprocess.Popen", side_effect=FileNotFoundError):
        res = formatter.format_code(code, tmp_path)
        assert res == "x=1"


def test_chameleon_rule_dot_ruff_toml_preferred(formatter, tmp_path):
    """When both .ruff.toml and ruff.toml exist, .ruff.toml is preferred"""
    (tmp_path / ".ruff.toml").write_text("line-length = 120")
    (tmp_path / "ruff.toml").write_text("line-length = 80")
    
    with patch("aura.craft.formatter.CodeFormatter._find_ruff_config", return_value=tmp_path / ".ruff.toml"):
        res = formatter._find_ruff_config(tmp_path)
        assert res == tmp_path / ".ruff.toml"

def test_chameleon_rule_pyproject_toml_with_ruff_section(formatter, tmp_path):
    """pyproject.toml with [tool.ruff] is detected"""
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
    
    res = formatter._find_ruff_config(tmp_path)
    assert res == tmp_path / "pyproject.toml"

def test_chameleon_rule_pyproject_toml_without_ruff_ignored(formatter, tmp_path):
    """pyproject.toml without [tool.ruff] is NOT detected"""
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires = ['setuptools']\n")
    
    res = formatter._find_ruff_config(tmp_path)
    assert res is None
