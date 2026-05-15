"""Tests for the Nuitka build helper."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.build_nuitka import (
    FINAL_DIST_NAME,
    OUTPUT_DIR,
    normalize_version,
    read_current_version,
    zip_distribution,
)


def test_normalize_version_accepts_optional_v_prefix() -> None:
    assert normalize_version("v1.3.4") == "1.3.4"
    assert normalize_version("1.3.4") == "1.3.4"


@pytest.mark.parametrize("version", ["", "1.3", "1.3.4.5", "1.3.beta"])
def test_normalize_version_rejects_invalid_values(version: str) -> None:
    with pytest.raises(SystemExit, match="Invalid version"):
        normalize_version(version)


def test_read_current_version_extracts_string_literal(tmp_path: Path) -> None:
    version_file = tmp_path / "aura" / "version.py"
    version_file.parent.mkdir()
    version_file.write_text(
        '"""Version information."""\n__version__ = "1.3.4"\n',
        encoding="utf-8",
    )

    assert read_current_version(tmp_path) == "1.3.4"


def test_zip_distribution_flattens_dist_contents(tmp_path: Path) -> None:
    final_dist_dir = tmp_path / OUTPUT_DIR / FINAL_DIST_NAME
    media_dir = final_dist_dir / "media"
    media_dir.mkdir(parents=True)
    (final_dist_dir / "Aura.exe").write_text("exe", encoding="utf-8")
    (media_dir / "test.txt").write_text("media", encoding="utf-8")
    (final_dist_dir / "runtime.dll").write_text("dll", encoding="utf-8")

    zip_distribution(tmp_path, final_dist_dir)

    zip_path = tmp_path / OUTPUT_DIR / "Aura-Windows-x64.zip"
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())

    assert "Aura.exe" in names
    assert "media/test.txt" in names
    assert "runtime.dll" in names
    assert "Aura.dist/Aura.exe" not in names
