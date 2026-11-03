#--------------------#
# settings_page.py
# settings page cards plus the password-locked developer options at the bottom
#--------------------#
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QScrollArea, QVBoxLayout, QWidget,
)

from core.config_loader import (
    AppSettings, ConfigLoadError, discover_themes, is_default_dev_password, verify_dev_password,
)
from ui.widgets import Card, PageHeader, SettingRow, button, label

# DevPanel pulls in gitpython and keyring, so it's imported on unlock, see docs/ARCHITECTURE.md, startup
if TYPE_CHECKING:
    from ui.dev_panel import DevPanel


class SettingsPage(QWidget):
    def __init__(self, app_root: Path, settings: AppSettings, settings_path: Path,
                 advanced_action: QAction, on_theme_selected: Callable[[str], None],
                 parent=None):
        super().__init__(parent)
        self.app_root = app_root
        self.settings = settings
        self.settings_path = settings_path
        self._on_theme_selected = on_theme_selected
        self.dev_panel: Optional[DevPanel] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(PageHeader("Settings", "Appearance, modes and app information"))

        # scrolling column of cards, developer options last
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll, stretch=1)

        content = QWidget()
        scroll.setWidget(content)
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(24, 16, 24, 24)
        self._content_layout.setSpacing(12)

        self._content_layout.addWidget(self._appearance_card())
        self._content_layout.addWidget(self._mode_card(advanced_action))
        self._content_layout.addWidget(self._updates_card())
        self._content_layout.addWidget(self._about_card())
        self._content_layout.addWidget(self._developer_card())
        self._content_layout.addStretch(1)

    # -- appearance --

    def _appearance_card(self) -> Card:
        card = Card("Appearance", icon_name="palette")
        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumWidth(180)
        self.reload_themes()
        self.theme_combo.currentTextChanged.connect(self._theme_combo_changed)
        card.add(SettingRow(
            "Theme", "Themes live in config/themes/ -- add your own YAML file to create one.",
            [self.theme_combo],
        ))
        return card

    # fills the combo without firing a theme change
    def reload_themes(self) -> None:
        themes = discover_themes(self.app_root / "config" / "themes")
        names = [n for n, t in themes.items() if not isinstance(t, ConfigLoadError)]
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        for name in names:
            self.theme_combo.addItem(name.replace("_", " ").title(), name)
        idx = self.theme_combo.findData(self.settings.active_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.blockSignals(False)

    def _theme_combo_changed(self, _text: str) -> None:
        name = self.theme_combo.currentData()
        if name:
            self._on_theme_selected(name)

    # -- mode --

    def _mode_card(self, advanced_action: QAction) -> Card:
        card = Card("Mode", icon_name="view")
        self.advanced_checkbox = QCheckBox("On")
        self.advanced_checkbox.setChecked(advanced_action.isChecked())
        # two-way sync with the shared action in the view menu
        self.advanced_checkbox.toggled.connect(advanced_action.setChecked)
        advanced_action.toggled.connect(self.advanced_checkbox.setChecked)
        card.add(SettingRow(
            "Advanced mode",
            "Adds the Advanced page: unknown CAN IDs, force decode, and the DBC "
            "structure and signal editor. No password needed. Ctrl+Shift+A.",
            [self.advanced_checkbox],
        ))
        return card

    # -- updates and about --

    def _updates_card(self) -> Card:
        card = Card("Updates", "The app checks for a new release every time it starts.",
                    icon_name="update")
        self.update_source_label = label("", "muted")
        card.add(SettingRow("Update source", "Changed from Developer options.",
                            [self.update_source_label]))
        self.refresh_update_source()
        return card

    # read only here, edited in developer options
    def refresh_update_source(self) -> None:
        repo = self.settings.updater.repo or "Not set"
        suffix = "  •  test mode" if self.settings.updater.test_mode else ""
        self.update_source_label.setText(repo + suffix)

    def _about_card(self) -> Card:
        card = Card("About", icon_name="info")
        card.add(SettingRow("CAN Decoder", f"Version {self.settings.version}"))
        open_btn = button("Open folder", icon_name="folder", on_click=lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.app_root))))
        card.add(SettingRow("Data folder", str(self.app_root), [open_btn]))
        return card

    # -- developer options (password locked) --
    # unlocking builds a DevPanel inside this card, locking destroys it

    def _developer_card(self) -> Card:
        self.dev_card = Card(
            "Developer options",
            "For people maintaining this app: GitHub repo, platforms, help content and git.",
            icon_name="lock",
        )
        self.dev_unlock_btn = button("Unlock…", on_click=self._show_password_row)
        self.dev_lock_btn = button("Lock", icon_name="lock", on_click=self.lock_developer)
        self.dev_lock_btn.setVisible(False)
        self.dev_card.header_layout.addWidget(self.dev_unlock_btn, alignment=Qt.AlignTop)
        self.dev_card.header_layout.addWidget(self.dev_lock_btn, alignment=Qt.AlignTop)

        # inline password row, hidden until unlock is clicked
        self.password_row = QWidget()
        row = QHBoxLayout(self.password_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.dev_password_input = QLineEdit()
        self.dev_password_input.setEchoMode(QLineEdit.Password)
        self.dev_password_input.setPlaceholderText("Developer password")
        self.dev_password_input.returnPressed.connect(self.try_unlock)
        row.addWidget(self.dev_password_input, stretch=1)
        row.addWidget(button("Unlock", variant="primary", icon_name="unlock", on_click=self.try_unlock))
        row.addWidget(button("Cancel", on_click=self._hide_password_row))
        self.password_row.setVisible(False)
        self.dev_card.add(self.password_row)

        # wrong password or default password warning
        self.dev_message = label("", "error", wrap=True)
        self.dev_message.setVisible(False)
        self.dev_card.add(self.dev_message)

        self.dev_container = QVBoxLayout()  # the DevPanel goes here once unlocked
        self.dev_card.add(self.dev_container)
        return self.dev_card

    def _show_password_row(self) -> None:
        self.dev_unlock_btn.setVisible(False)
        self.password_row.setVisible(True)
        self.dev_password_input.setFocus()

    def _hide_password_row(self) -> None:
        self.password_row.setVisible(False)
        self.dev_password_input.clear()
        self.dev_message.setVisible(False)
        self.dev_unlock_btn.setVisible(True)

    def is_developer_unlocked(self) -> bool:
        return self.dev_panel is not None

    # checks the typed password, builds the DevPanel on success
    def try_unlock(self) -> bool:
        if not verify_dev_password(self.settings, self.dev_password_input.text()):
            self.dev_message.setProperty("role", "error")
            self.dev_message.setText("Incorrect password.")
            self.dev_message.style().polish(self.dev_message)
            self.dev_message.setVisible(True)
            self.dev_password_input.selectAll()
            return False
        self.dev_password_input.clear()
        self.password_row.setVisible(False)
        self.dev_unlock_btn.setVisible(False)
        if is_default_dev_password(self.settings):
            self.dev_message.setText(
                "You're still using the default password. Change it under Security below."
            )
            self.dev_message.setVisible(True)
        else:
            self.dev_message.setVisible(False)
        from ui.dev_panel import DevPanel

        self.dev_panel = DevPanel(self.app_root, self.settings, self.settings_path, self)
        self.dev_container.addWidget(self.dev_panel)
        self.dev_lock_btn.setVisible(True)
        return True

    # removes the DevPanel and resets the card
    def lock_developer(self) -> None:
        if self.dev_panel is not None:
            self.dev_panel.setParent(None)
            self.dev_panel.deleteLater()
            self.dev_panel = None
        self.dev_lock_btn.setVisible(False)
        self._hide_password_row()
        self.refresh_update_source()

    # used by help > developer options, opens the password row
    def reveal_developer(self) -> None:
        if not self.is_developer_unlocked():
            self._show_password_row()
