"""Focused tests for role capsule reader and release hardening."""
from __future__ import annotations

from pathlib import Path

import pytest

from aura.context_gearbox.models import RuntimeRole
from aura.roles import load_bundled_named_role_capsule, load_bundled_role_capsule
from aura.roles.reader import _read_bundled_markdown


# --- Capsule loading ---


def test_all_runtime_roles_load_bundled_capsule() -> None:
    for role in (RuntimeRole.PLANNER, RuntimeRole.WORKER, RuntimeRole.SINGLE):
        capsule = load_bundled_role_capsule(role)
        assert capsule is not None, f"capsule missing for {role.value}"
        assert capsule.content
        assert len(capsule.checksum) == 64


def test_critic_named_capsule_loads() -> None:
    capsule = load_bundled_named_role_capsule("critic", allowed={"critic"})
    assert capsule is not None
    assert capsule.name == "critic"
    assert capsule.content


def test_reader_returns_none_when_both_paths_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """When local dev path and resource fallback both miss, reader returns None."""
    monkeypatch.setattr(
        "aura.roles.reader._try_read_markdown",
        lambda _path: None,
    )

    result = _read_bundled_markdown("planner")
    assert result is None


def test_capsules_use_possessive_aura() -> None:
    """Capsule wording should say "Aura's", not "Auras"."""
    for role in (RuntimeRole.PLANNER, RuntimeRole.WORKER, RuntimeRole.SINGLE):
        capsule = load_bundled_role_capsule(role)
        assert capsule is not None
        assert "Auras " not in capsule.content, f"{role.value} capsule has 'Auras' typo"

    critic = load_bundled_named_role_capsule("critic", allowed={"critic"})
    assert critic is not None
    assert "Auras " not in critic.content, "critic capsule has 'Auras' typo"


# --- Package metadata ---


def test_pyproject_declares_role_capsule_package_data() -> None:
    root = Path(__file__).resolve().parents[1]
    content = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert 'aura.roles' in content
    assert 'bundled/*.md' in content


# --- Build script ---


def test_nuitka_command_includes_role_capsule_data_dir() -> None:
    from scripts.build_nuitka import (
        ROLE_CAPSULES_DEST_REL,
        ROLE_CAPSULES_SOURCE_REL,
        create_nuitka_command,
    )

    cmd = create_nuitka_command()
    expected = f"--include-data-dir={ROLE_CAPSULES_SOURCE_REL}={ROLE_CAPSULES_DEST_REL}"

    assert expected in cmd


def test_validate_project_paths_fails_on_missing_role_capsule(tmp_path: Path) -> None:
    from scripts.build_nuitka import (
        REQUIRED_MEDIA_FILES,
        UPDATER_HELPER_SOURCE,
        validate_project_paths,
    )

    # Set up all non-capsule requirements
    (tmp_path / "aura").mkdir()
    (tmp_path / "aura" / "__main__.py").write_text("", encoding="utf-8")
    (tmp_path / UPDATER_HELPER_SOURCE).write_text("helper", encoding="utf-8")
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    for filename in REQUIRED_MEDIA_FILES:
        (media_dir / filename).write_text("media", encoding="utf-8")

    # Create all capsules except critic
    capsule_dir = tmp_path / "aura" / "roles" / "bundled"
    capsule_dir.mkdir(parents=True)
    for name in ("planner", "worker", "single"):
        (capsule_dir / f"{name}.md").write_text(f"# {name}", encoding="utf-8")

    with pytest.raises(SystemExit, match="critic.md"):
        validate_project_paths(tmp_path)
