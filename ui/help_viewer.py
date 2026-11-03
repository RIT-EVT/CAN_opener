#--------------------#
# help_viewer.py
# read-only help popup and the small ? button that opens it
#--------------------#
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from core.help_content import load_help_text


# renders one topic's markdown
class HelpViewerDialog(QDialog):
    def __init__(self, title: str, markdown_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(460, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setMarkdown(markdown_text)
        layout.addWidget(self.browser)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)


# round ? button for help topic key
def make_help_button(help_dir: Path, key: str, title: str, parent: QWidget) -> QPushButton:
    btn = QPushButton("?", parent)
    btn.setObjectName("helpButton")
    btn.setFixedSize(22, 22)
    btn.setCursor(Qt.PointingHandCursor)
    # id-scoped rule removes the global button padding that would clip the ?
    btn.setStyleSheet(
        "QPushButton#helpButton {"
        " padding: 0px; margin: 0px; border-radius: 11px; font-weight: bold;"
        "}"
    )
    btn.setToolTip("Help")
    btn.clicked.connect(
        lambda: HelpViewerDialog(title, load_help_text(help_dir, key), parent).exec()
    )
    return btn
