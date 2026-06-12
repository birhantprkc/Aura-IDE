"""Standalone modeless Drone Workbay window wrapping ChainEditor."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QWidget,
)

from aura.gui.drones.chain_editor import ChainEditor

logger = logging.getLogger(__name__)


class DroneWorkbayWindow(QDialog):
    """Non-modal window that hosts a ChainEditor for workflow editing.

    Hiding this window preserves the ChainEditor state.  WA_DeleteOnClose
    is False so closing via the WM close button only hides the window.
    """

    geometry_saved = Signal(str)

    def __init__(
        self,
        workspace_root: Path,
        chain_id: str | None = None,
        provider_id: str = "deepseek",
        model: str = "",
        thinking: str = "disabled",
        temperature: float = 0.4,
        initial_geometry: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Drone Workbay")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)

        self._geometry_restore_done = False
        self._initial_geometry = initial_geometry.strip()

        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(250)
        self._geometry_save_timer.timeout.connect(self._save_geometry)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._chain_editor = ChainEditor(
            workspace_root=workspace_root,
            chain_id=chain_id,
            provider_id=provider_id,
            model=model,
            thinking=thinking,
            temperature=temperature,
            parent=self,
        )
        layout.addWidget(self._chain_editor)

        self._restore_geometry(self._initial_geometry)
        self._geometry_restore_done = True

    # -- public API ---------------------------------------------------------

    @property
    def chain_editor(self) -> ChainEditor:
        return self._chain_editor

    def show_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def is_open(self) -> bool:
        return self.isVisible()

    # -- geometry save/restore ----------------------------------------------

    def _restore_geometry(self, geometry: str) -> None:
        if not geometry:
            return
        try:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        except Exception:
            logger.debug("Failed to restore Drone Workbay geometry", exc_info=True)

    def _schedule_geometry_save(self) -> None:
        if not self._geometry_restore_done:
            return
        self._geometry_save_timer.start()

    def _save_geometry(self) -> None:
        if not self._geometry_restore_done:
            return
        geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.geometry_saved.emit(geometry)

    # -- events -------------------------------------------------------------

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._schedule_geometry_save()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._schedule_geometry_save()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_geometry_save()

    def closeEvent(self, event: QCloseEvent) -> None:
        event.accept()
