from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from aura.config import ThinkingMode
from aura.drones.build_spec import DroneBuildBrief
from aura.gui.drones.drone_workshop_panel import DroneWorkshopPanel
from aura.gui.theme import BG_ALT


class DroneWorkshopDialog(QDialog):
    """Dialog wrapper around the Drone Workshop panel."""

    drone_build_requested = Signal(object)  # emits DroneBuildBrief

    def __init__(
        self,
        workspace_root: Path | None = None,
        provider_id: str = "deepseek",
        model: str = "",
        thinking: ThinkingMode = "disabled",
        temperature: float = 0.4,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Drone Workshop")
        self.resize(900, 720)
        self.setMinimumSize(680, 480)
        self.setStyleSheet(f"QDialog {{ background: {BG_ALT}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._panel = DroneWorkshopPanel(
            workspace_root=workspace_root,
            provider_id=provider_id,
            model=model,
            thinking=thinking,
            temperature=temperature,
            parent=self,
        )
        self._panel.drone_build_requested.connect(self.drone_build_requested.emit)
        self._panel.drone_build_requested.connect(self.accept)
        self._panel.cancelled.connect(self.reject)
        layout.addWidget(self._panel)

    def result_brief(self) -> DroneBuildBrief | None:
        return self._panel.result_brief()

    def reject(self) -> None:
        self._panel.cancel()
        super().reject()
