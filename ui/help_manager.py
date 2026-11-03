#--------------------#
# help_manager.py
# developer dialog to edit help topics with a live markdown preview
#--------------------#
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

from core.help_content import (
    bootstrap_default_help, list_help_keys, load_help_text, save_help_text,
)
from ui.widgets import button, icon, label


class HelpContentManagerDialog(QDialog):
    def __init__(self, app_root: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Help Content")
        self.resize(900, 600)
        self.help_dir = app_root / "config" / "help"
        self.defaults_dir = app_root / "config" / "defaults" / "help"
        # copy any new default topics in case they arrived since startup
        bootstrap_default_help(self.help_dir, self.defaults_dir)
        self._current_key: Optional[str] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(10)
        outer.addWidget(label("Help content", "title"))
        outer.addWidget(label(
            "Written in Markdown. Shown by the ? buttons and on the Help page.", "muted"
        ))
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_editor_panel())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 700])
        outer.addWidget(splitter, stretch=1)

        close_box = QDialogButtonBox(QDialogButtonBox.Close)
        close_box.rejected.connect(self.accept)
        outer.addWidget(close_box)

        self._refresh_list()

    # -- left: topic list --

    def _build_list_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.addWidget(label("Topics", "section"))
        self.key_list = QListWidget()
        self.key_list.itemClicked.connect(self._on_select_key)
        layout.addWidget(self.key_list)
        return w

    def _refresh_list(self, select_key: Optional[str] = None) -> None:
        self.key_list.clear()
        for key in list_help_keys(self.help_dir, self.defaults_dir):
            item = QListWidgetItem(icon("document"), key)
            self.key_list.addItem(item)
            if select_key == key:
                self.key_list.setCurrentItem(item)

    def _on_select_key(self, item: QListWidgetItem) -> None:
        self._current_key = item.text()
        self.editor_title.setText(self._current_key)
        self.editor.setPlainText(load_help_text(self.help_dir, self._current_key))

    # -- right: markdown source and live preview side by side --

    def _build_editor_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 0, 0, 0)
        head = QHBoxLayout()
        self.editor_title = label("Select a topic", "section")
        head.addWidget(self.editor_title)
        head.addStretch()
        head.addWidget(button("Save", variant="primary", icon_name="save", on_click=self._on_save))
        layout.addLayout(head)

        panes = QSplitter(Qt.Horizontal)
        panes.setChildrenCollapsible(False)
        src = QWidget()
        sv = QVBoxLayout(src)
        sv.setContentsMargins(0, 0, 4, 0)
        sv.addWidget(label("Markdown", "muted"))
        self.editor = QPlainTextEdit()
        self.editor.textChanged.connect(self._update_preview)
        sv.addWidget(self.editor)
        panes.addWidget(src)

        prev = QWidget()
        pv = QVBoxLayout(prev)
        pv.setContentsMargins(4, 0, 0, 0)
        pv.addWidget(label("Preview", "muted"))
        self.preview = QTextBrowser()
        pv.addWidget(self.preview)
        panes.addWidget(prev)
        layout.addWidget(panes, stretch=1)
        return w

    def _update_preview(self) -> None:
        self.preview.setMarkdown(self.editor.toPlainText())

    def _on_save(self) -> None:
        if not self._current_key:
            QMessageBox.warning(self, "No topic selected", "Select a help topic first.")
            return
        save_help_text(self.help_dir, self._current_key, self.editor.toPlainText())
        QMessageBox.information(self, "Saved", f"Updated help for {self._current_key!r}.")
