from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from aura.config import AppSettings
from aura.gui.left_pane import LeftPane
from aura.gui.settings_dialog import SettingsDialog


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_settings_dialog_preserves_max_tool_rounds(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(SettingsDialog, "_start_auth_status_check", lambda self: None)
    settings = AppSettings(max_tool_rounds=123)

    dlg = SettingsDialog(
        settings=settings,
        workspace_root=tmp_path,
        on_change_root=lambda: None,
    )

    assert dlg._settings.max_tool_rounds == 123
    assert dlg._max_rounds_spin.value() == 123
    assert dlg.result_settings().max_tool_rounds == 123
    dlg.close()


def test_settings_dialog_closes_with_auth_status_thread(
    qapp: QApplication, tmp_path: Path
) -> None:
    dlg = SettingsDialog(
        settings=AppSettings(),
        workspace_root=tmp_path,
        on_change_root=lambda: None,
    )

    dlg.close()
    qapp.processEvents()


def test_settings_dialog_can_assign_google_ai_to_planner_and_worker(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(SettingsDialog, "_start_auth_status_check", lambda self: None)
    settings = AppSettings(
        provider="deepseek",
        planner_provider="google_ai",
        worker_provider="google_ai",
        default_planner_model="gemini-2.0-flash",
        default_worker_model="gemini-2.0-flash",
    )

    dlg = SettingsDialog(
        settings=settings,
        workspace_root=tmp_path,
        on_change_root=lambda: None,
    )

    result = dlg.result_settings()

    assert result.planner_provider == "google_ai"
    assert result.worker_provider == "google_ai"
    assert result.default_planner_model == "gemini-2.0-flash"
    assert result.default_worker_model == "gemini-2.0-flash"
    dlg.close()


def test_left_pane_shows_google_ai_default_model_without_discovery(
    qapp: QApplication, tmp_path: Path
) -> None:
    pane = LeftPane(tmp_path)

    pane.populate_models("google_ai", "google_ai")

    assert pane._planner_model_combo.findData("gemini-2.0-flash") >= 0
    assert pane._worker_model_combo.findData("gemini-2.0-flash") >= 0
    pane.close()
