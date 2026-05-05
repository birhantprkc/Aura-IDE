"""Smoke 6 (informal): launch the main window for ~1.5s, then quit.

Verifies the window constructs without exception and renders one frame on Windows.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from aura.config import APP_NAME, ENV_API_KEY
from aura.gui.main_window import MainWindow
from aura.gui.theme import apply_theme


def main() -> int:
    if not os.environ.get(ENV_API_KEY):
        print(f"WARN: {ENV_API_KEY} not set; window will still construct.")
    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setOrganizationName(APP_NAME)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    apply_theme(app)

    win = MainWindow()
    win.show()
    print("window shown:", win.windowTitle(), win.size().width(), "x", win.size().height())

    # Auto-quit after ~1500ms.
    QTimer.singleShot(1500, app.quit)
    rc = app.exec()
    print("rc =", rc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
