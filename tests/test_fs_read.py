from __future__ import annotations

import hashlib
from pathlib import Path

from aura.conversation.tools.fs_read import read_file


def test_read_file_returns_content_hash_and_file_size(tmp_workspace):
    f = tmp_workspace / "hello.py"
    f.write_text("print('hello')", encoding="utf-8")
    result = read_file(tmp_workspace, f)
    assert result["ok"] is True
    assert "content_hash" in result
    assert "file_size" in result
    assert result["content_hash"] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert result["file_size"] == f.stat().st_size
    assert result["truncated"] is False
