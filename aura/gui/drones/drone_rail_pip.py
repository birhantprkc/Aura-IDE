"""Temporary rail pip indicating an active Drone run."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QGraphicsOpacityEffect, QToolButton, QWidget

from aura.config import media_path
from aura.gui.theme import DANGER, FG_DIM, SUCCESS, WARN


class DroneRailPip(QToolButton):
    """Small bot pip on the edge rail indicating a Drone run.

    The pip stays small enough to read as a rail indicator, but carries the
    run lifecycle through color and a restrained opacity pulse.
    """

    focused = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("edgeDroneRunPip")
        self.setToolTip("Drone running - click to view")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(18, 18)
        self.setIcon(QIcon(str(media_path("drone_bot.svg"))))
        self.setIconSize(QSize(12, 12))
        self.setCheckable(False)
        self.clicked.connect(self.focused.emit)
        self._state = "idle"
        self._launching = False
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)
        self._pulse = QPropertyAnimation(self._opacity, b"opacity", self)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._set_idle()

    def _set_idle(self) -> None:
        self._state = "idle"
        self._launching = False
        self._stop_pulse()
        self._opacity.setOpacity(1.0)
        self.setStyleSheet(
            "QToolButton#edgeDroneRunPip { background: transparent; border: none; }"
        )
        self.hide()

    def begin_launch_animation(self) -> None:
        """Keep the layout slot reserved while a ghost bot slides into it."""
        self._launching = True
        self._stop_pulse()
        self._opacity.setOpacity(0.0)
        self.show()

    def finish_launch_animation(self) -> None:
        self._launching = False
        self._apply_state()

    def set_summoning(self) -> None:
        self.set_state("summoning")

    def set_running(self) -> None:
        self.set_state("running")

    def set_waiting_for_approval(self) -> None:
        self.set_state("waiting_for_approval")

    def set_error(self) -> None:
        self.set_state("failed")

    def set_completed(self) -> None:
        self.set_state("completed")

    def set_cancelled(self) -> None:
        self.set_state("cancelled")

    def set_idle(self) -> None:
        self._set_idle()

    def set_state(self, state: str) -> None:
        self._state = self._normalize_state(state)
        self._apply_state()

    def _apply_state(self) -> None:
        if self._state == "idle":
            self._set_idle()
            return

        palette = {
            "summoning": ("#14303a", "#7dcfff", "#1d4a5e"),
            "running": ("#102a24", "#4ec9b0", "#174538"),
            "completed": ("#142615", SUCCESS, "#203a20"),
            "failed": ("#35161d", DANGER, "#4a1c27"),
            "cancelled": ("#202126", FG_DIM, "#2b2d34"),
            "timed_out": ("#35161d", DANGER, "#4a1c27"),
            "waiting_for_approval": ("#332716", WARN, "#473519"),
        }
        bg, border, hover = palette.get(self._state, palette["running"])
        self.setStyleSheet(
            "QToolButton#edgeDroneRunPip {"
            f"  background: {bg};"
            f"  border: 1px solid {border};"
            "  border-radius: 9px;"
            "  padding: 0px;"
            "}"
            "QToolButton#edgeDroneRunPip:hover {"
            f"  background: {hover};"
            f"  border-color: {border};"
            "}"
        )
        self.show()
        if self._launching:
            self._stop_pulse()
            self._opacity.setOpacity(0.0)
            return

        if self._state == "summoning":
            self._start_pulse(low=0.45, duration_ms=420)
        elif self._state == "running":
            self._start_pulse(low=0.72, duration_ms=1050)
        elif self._state == "waiting_for_approval":
            self._start_pulse(low=0.55, duration_ms=740)
        else:
            self._stop_pulse()
            self._opacity.setOpacity(1.0)

    def _start_pulse(self, low: float, duration_ms: int) -> None:
        self._pulse.stop()
        self._pulse.setDuration(duration_ms)
        self._pulse.setStartValue(low)
        self._pulse.setEndValue(1.0)
        self._pulse.setLoopCount(-1)
        self._pulse.start()

    def _stop_pulse(self) -> None:
        self._pulse.stop()
        self._pulse.setLoopCount(1)

    @staticmethod
    def _normalize_state(state: str) -> str:
        normalized = state.strip().lower().replace(" ", "_").replace("-", "_")
        if normalized in {"waiting", "approval", "waiting_approval"}:
            return "waiting_for_approval"
        if normalized in {"error", "failed"}:
            return "failed"
        if normalized in {"done", "success"}:
            return "completed"
        return normalized
