from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from aura.gui.theme import (
    ACCENT,
    BG_RAISED,
    BORDER,
    FG,
    FG_DIM,
)


class GlassSwitch(QWidget):
    """Custom toggle switch that fits the Aura glass theme."""
    toggled = Signal(bool)

    def __init__(self, label: str, checked: bool = False, vertical: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._checked = checked
        self._label_text = label
        self._label: QLabel | None = None

        if vertical:
            layout = QVBoxLayout(self)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            layout = QHBoxLayout(self)

        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # The Track
        self._track = QFrame(self)
        self._track.setFixedSize(32, 16)
        self._track.setCursor(Qt.CursorShape.PointingHandCursor)
        self._track.setStyleSheet(self._get_track_style())

        # The Thumb
        self._thumb = QFrame(self._track)
        self._thumb.setFixedSize(10, 10)
        self._thumb.move(3 if not checked else 19, 3)
        self._thumb.setStyleSheet(
            f"background: {FG}; border-radius: 5px;"
        )
        self._thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(self._track, 0, Qt.AlignmentFlag.AlignCenter)
        self._track.installEventFilter(self)

        if label:
            self._label = QLabel(label, self)
            self._label.setCursor(Qt.CursorShape.PointingHandCursor)
            self._label.installEventFilter(self)
            layout.addWidget(self._label, 0, Qt.AlignmentFlag.AlignCenter)
            self._refresh_label_style()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self.setChecked(not self._checked)
                self.toggled.emit(self._checked)
                return True
        return super().eventFilter(watched, event)

    def _get_track_style(self) -> str:
        bg = ACCENT if self._checked else BG_RAISED
        border = ACCENT if self._checked else BORDER
        return f"background: {bg}; border: 1px solid {border}; border-radius: 8px;"

    def _refresh_label_style(self) -> None:
        if self._label is None:
            return
        color = ACCENT if self._checked else FG_DIM
        weight = 700 if self._checked else 600
        self._label.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: {weight};"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
            self.toggled.emit(self._checked)

    def setChecked(self, checked: bool):
        self._checked = checked
        self._track.setStyleSheet(self._get_track_style())
        self._refresh_label_style()
        # Animate thumb position
        anim = getattr(self, "_anim", None)
        if anim:
            anim.stop()
        self._anim = QPropertyAnimation(self._thumb, b"pos", self)
        self._anim.setDuration(120)
        self._anim.setEndValue(QPoint(19 if checked else 3, 3))
        self._anim.start()

    def isChecked(self) -> bool:
        return self._checked
