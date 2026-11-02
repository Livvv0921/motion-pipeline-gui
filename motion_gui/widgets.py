from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class PathRow(QWidget):
    changed = Signal(str)

    def __init__(self, placeholder="", mode="folder", filter_text="All files (*)", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.filter_text = filter_text
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed)
        self.button = QPushButton("BROWSE")
        self.button.setObjectName("browseButton")
        self.button.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, value: str):
        self.edit.setText(value or "")

    def _browse(self):
        current = self.text()
        if self.mode == "file":
            path, _ = QFileDialog.getOpenFileName(self, "Select file", current, self.filter_text)
        elif self.mode == "save":
            path, _ = QFileDialog.getSaveFileName(self, "Save file", current, self.filter_text)
        else:
            path = QFileDialog.getExistingDirectory(self, "Select folder", current)
        if path:
            self.setText(path)


class StepNavItem(QWidget):
    clicked = Signal()

    def __init__(self, number: int, title: str, parent=None):
        super().__init__(parent)
        self.status = "idle"
        self.check = QCheckBox()
        self.check.setEnabled(False)
        self.dot = QLabel("●")
        self.dot.setFixedWidth(16)
        self.button = QPushButton(f"{number:02d}  {title.upper()}")
        self.button.setObjectName("navButton")
        self.button.clicked.connect(self.clicked)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        top.addWidget(self.dot)
        top.addWidget(self.check)
        top.addWidget(self.button, 1)

        self.progress = QProgressBar()
        self.progress.setObjectName("navProgress")
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        self.progress.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(2)
        layout.addLayout(top)
        layout.addWidget(self.progress)
        self.set_status("idle")

    def set_selected(self, selected: bool):
        self.button.setProperty("selected", selected)
        self.button.style().unpolish(self.button)
        self.button.style().polish(self.button)

    def set_progress(self, value: int):
        if self.status != "running":
            return
        self.progress.show()
        if value < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, int(value))))

    def set_status(self, status: str):
        self.status = status
        # These semantic colors intentionally come from the three final palettes.
        colors = {
            "idle": "#8B8D94",
            "running": "#FF7BBF",
            "success": "#4FE0B6",
            "failed": "#F14666",
        }
        self.dot.setStyleSheet(f"color: {colors.get(status, colors['idle'])}; font-size: 16px;")
        if status == "running":
            self.check.setChecked(False)
            self.progress.show()
            self.progress.setRange(0, 0)
        else:
            self.progress.hide()
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            if status == "success":
                self.check.setChecked(True)
            elif status in {"failed", "idle"}:
                self.check.setChecked(False)

