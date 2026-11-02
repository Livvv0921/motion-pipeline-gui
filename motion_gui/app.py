from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import stylesheet


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Motion Pipeline GUI")
    app.setOrganizationName("MotionPipelineGUI")
    app.setFont(QFont("Courier New", 10))

    settings = QSettings("MotionPipelineGUI", "MotionPipelineGUI")
    theme = str(settings.value("ui/theme", "dark") or "dark").lower()
    if theme not in {"dark", "light"}:
        theme = "dark"
    app.setStyleSheet(stylesheet(theme))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
