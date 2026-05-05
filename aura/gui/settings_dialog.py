"""Modal Settings dialog — exposes the persisted AppSettings + a few
read-only environment / workspace facts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from aura.config import (
    APP_NAME,
    AppSettings,
    ENV_API_KEY,
    MODELS,
    ModelId,
    ThinkingMode,
    has_api_key,
    save_settings,
)
from aura.gui.theme import DANGER, FG_DIM, SUCCESS, WARN


class SettingsDialog(QDialog):
    """Modal settings.

    `on_change_root` is fired when the user clicks "Change..." next to the
    workspace label so the host (MainWindow) can run the same picker it uses
    elsewhere; we don't fork that logic here.
    """

    def __init__(
        self,
        settings: AppSettings,
        workspace_root: Path | None,
        on_change_root: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Settings")
        self.setModal(True)
        self.resize(560, 0)

        self._settings = AppSettings(
            default_model=settings.default_model,
            default_thinking=settings.default_thinking,
            restore_last_conversation=settings.restore_last_conversation,
        )
        self._on_change_root = on_change_root

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 14)
        outer.setSpacing(14)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self._model_combo = QComboBox()
        for mid, info in MODELS.items():
            self._model_combo.addItem(info.label, mid)
        self._model_combo.setCurrentIndex(
            list(MODELS.keys()).index(self._settings.default_model)
        )
        form.addRow("Default model:", self._model_combo)

        self._thinking_combo = QComboBox()
        self._thinking_combo.addItem("Off", "off")
        self._thinking_combo.addItem("High", "high")
        self._thinking_combo.addItem("Max", "max")
        self._thinking_combo.setCurrentIndex(
            ["off", "high", "max"].index(self._settings.default_thinking)
        )
        form.addRow("Default thinking:", self._thinking_combo)

        self._restore_chk = QCheckBox("Restore most-recent conversation on launch")
        self._restore_chk.setChecked(self._settings.restore_last_conversation)
        form.addRow("", self._restore_chk)

        # Workspace
        ws_row = QHBoxLayout()
        ws_row.setSpacing(8)
        self._ws_label = QLabel(str(workspace_root) if workspace_root else "(none)")
        self._ws_label.setStyleSheet(f"color: {FG_DIM};")
        self._ws_label.setWordWrap(True)
        ws_row.addWidget(self._ws_label, 1)
        change_btn = QPushButton("Change...")
        change_btn.clicked.connect(self._on_change_root_clicked)
        ws_row.addWidget(change_btn)
        ws_widget = QWidget()
        ws_widget.setLayout(ws_row)
        form.addRow("Workspace root:", ws_widget)

        # API key status
        if has_api_key():
            api_label = QLabel(f"{ENV_API_KEY}: set")
            api_label.setStyleSheet(f"color: {SUCCESS};")
        else:
            api_label = QLabel(
                f"{ENV_API_KEY}: NOT SET — run `setx {ENV_API_KEY} <key>` and restart."
            )
            api_label.setStyleSheet(f"color: {DANGER};")
        api_label.setWordWrap(True)
        form.addRow("API key:", api_label)

        # Backups info
        if workspace_root is not None:
            backup_path = workspace_root / ".aura" / "backups"
            backup_text = (
                f"Stored in {backup_path}, never auto-deleted. Manage manually."
            )
        else:
            backup_text = "Stored under <workspace>/.aura/backups/, never auto-deleted."
        backup_label = QLabel(backup_text)
        backup_label.setStyleSheet(f"color: {FG_DIM};")
        backup_label.setWordWrap(True)
        form.addRow("Backups:", backup_label)

        outer.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _on_change_root_clicked(self) -> None:
        self._on_change_root()
        # Host updated the workspace root — refresh display from the host:
        host = self.parent()
        if host is not None and hasattr(host, "_workspace_root"):
            new_root = getattr(host, "_workspace_root")
            self._ws_label.setText(str(new_root) if new_root else "(none)")

    def result_settings(self) -> AppSettings:
        """Read the current widget values and return a fresh AppSettings."""
        return AppSettings(
            default_model=self._model_combo.currentData(),
            default_thinking=self._thinking_combo.currentData(),
            restore_last_conversation=self._restore_chk.isChecked(),
        )

    def accept(self) -> None:  # type: ignore[override]
        # Persist on OK.
        new_settings = self.result_settings()
        save_settings(new_settings)
        self._settings = new_settings
        super().accept()
