"""Temporary rail pip indicating an active Drone run."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QToolButton, QWidget


class DroneRailPip(QToolButton):
    """Small colored dot on the edge rail indicating an active run.

    Green while running, red on error, hidden when idle.
    Clickable to focus the run card.
    """

    focused = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("edgeDroneRunPip")
        self.setToolTip("Drone running - click to view")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(10, 10)
        self.setCheckable(False)
        self.clicked.connect(self.focused.emit)
        self._set_idle()

    def _set_idle(self) -> None:
        self.setStyleSheet(
            "QToolButton#edgeDroneRunPip { background: transparent; border: none; }"
        )
        self.hide()

    def set_running(self) -> None:
        self.setStyleSheet(
            "QToolButton#edgeDroneRunPip { background: #4ec9b0; border: 1px solid #4ec9b0; "
            "border-radius: 5px; }"
            "QToolButton#edgeDroneRunPip:hover { background: #6ed9c0; }"
        )
        self.show()

    def set_error(self) -> None:
        self.setStyleSheet(
            "QToolButton#edgeDroneRunPip { background: #f44747; border: 1px solid #f44747; "
            "border-radius: 5px; }"
            "QToolButton#edgeDroneRunPip:hover { background: #f66767; }"
        )
        self.show()

    def set_idle(self) -> None:
        self._set_idle()
