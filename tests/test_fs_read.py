from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

from aura.conversation.tools.fs_handler import FsReadHandler
from aura.conversation.tools.fs_read import read_file, read_file_range


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


def test_read_file_hash_does_not_use_read_bytes(tmp_workspace):
    f = tmp_workspace / "large.txt"
    content = (b"0123456789abcdef\n" * 20000)
    f.write_bytes(content)
    expected_hash = hashlib.sha256(content).hexdigest()

    with patch.object(Path, "read_bytes", side_effect=AssertionError("read_bytes should not be used")):
        result = read_file(tmp_workspace, f)

    assert result["ok"] is True
    assert result["content_hash"] == expected_hash
    assert result["file_size"] == len(content)
    assert result["truncated"] is True


def test_read_files_preserves_per_file_metadata(tmp_workspace):
    first = tmp_workspace / "one.py"
    second = tmp_workspace / "two.py"
    first.write_text("one = 1\n", encoding="utf-8", newline="\n")
    second.write_text("two = 2\n", encoding="utf-8", newline="\n")
    handler = FsReadHandler(tmp_workspace, lambda raw: (tmp_workspace / raw).resolve())

    result = handler.handle_read_files({"paths": ["one.py", "two.py"]})

    assert result["ok"] is True
    one = result["files"]["one.py"]
    two = result["files"]["two.py"]
    assert one["ok"] is True
    assert one["path"] == "one.py"
    assert one["content"] == "one = 1\n"
    assert one["content_hash"] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert one["file_size"] == first.stat().st_size
    assert one["truncated"] is False
    assert two["content_hash"] == hashlib.sha256(second.read_bytes()).hexdigest()
    assert two["file_size"] == second.stat().st_size
    assert two["truncated"] is False


def test_read_file_range_returns_whole_file_version_metadata(tmp_workspace):
    f = tmp_workspace / "range.py"
    f.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8", newline="\n")

    result = read_file_range(tmp_workspace, f, 2, 2)

    assert result["ok"] is True
    assert result["content"] == "b = 2\n"
    assert result["content_hash"] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert result["file_size"] == f.stat().st_size
