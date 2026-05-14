"""Tests for the Nuitka build helper."""

from __future__ import annotations

import zipfile
from pathlib import Path

from scripts.build_nuitka import FINAL_DIST_NAME, OUTPUT_DIR, zip_distribution


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
