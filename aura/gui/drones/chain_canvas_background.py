from __future__ import annotations

import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap, QRadialGradient


def build_space_cache(size) -> QPixmap:
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    w, h = size.width(), size.height()

    # Radial gas clouds (layered additive)
    # Violet main bloom
    g1 = QRadialGradient(QPointF(0.30 * w, 0.58 * h), 0.46 * w)
    g1.setColorAt(0.0, QColor(157, 124, 216, 72))
    g1.setColorAt(0.45, QColor(150, 115, 205, 34))
    g1.setColorAt(1.0, QColor(157, 124, 216, 0))
    p.fillRect(0, 0, w, h, g1)

    # Warm magenta pocket
    g2 = QRadialGradient(QPointF(0.52 * w, 0.68 * h), 0.40 * w)
    g2.setColorAt(0.0, QColor(247, 118, 142, 55))
    g2.setColorAt(0.5, QColor(205, 95, 140, 24))
    g2.setColorAt(1.0, QColor(247, 118, 142, 0))
    p.fillRect(0, 0, w, h, g2)

    # Blue upper drift
    g3 = QRadialGradient(QPointF(0.62 * w, 0.34 * h), 0.42 * w)
    g3.setColorAt(0.0, QColor(122, 162, 247, 40))
    g3.setColorAt(0.5, QColor(110, 140, 220, 18))
    g3.setColorAt(1.0, QColor(122, 162, 247, 0))
    p.fillRect(0, 0, w, h, g3)

    # Cyan accent
    g4 = QRadialGradient(QPointF(0.80 * w, 0.55 * h), 0.28 * w)
    g4.setColorAt(0.0, QColor(125, 207, 255, 28))
    g4.setColorAt(1.0, QColor(125, 207, 255, 0))
    p.fillRect(0, 0, w, h, g4)

    # Subtle static stars
    rng = random.Random(42)
    for _ in range(250):
        sx = rng.uniform(0, w)
        sy = rng.uniform(0, h)
        sr = rng.uniform(0.4, 1.5)
        sa = rng.randint(20, 80)
        c = QColor(200, 208, 240, sa)
        p.setBrush(QBrush(c))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(sx, sy), sr, sr)

    p.end()
    return pixmap
