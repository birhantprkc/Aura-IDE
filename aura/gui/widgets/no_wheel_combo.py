"""A QComboBox subclass that ignores wheel events to prevent accidental value changes."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse-wheel events.

    Wheel events are ignored so that scrolling the parent panel does not
    accidentally change the selected item.  Normal click/dropdown selection
    works as usual.
    """

    def wheelEvent(self, event) -> None:
        event.ignore()
