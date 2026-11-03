#--------------------#
# platform_manager.py
# developer dialog to create, edit and delete platform configs and import dbc files
#--------------------#
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.config_loader import (
    ConfigLoadError, PlatformConfig, discover_platforms, load_platform_config,
    save_platform_config,
)
from ui.widgets import button, icon, label


# platform name to a safe yaml filename, e.g. 2026 ev a becomes 2026_ev_a
def _slugify(name: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "_" for c in name.strip())
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_") or "platform"


class PlatformManagerDialog(QDialog):
    def __init__(self, app_root: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Platforms")
        self.resize(780, 580)
        self.app_root = app_root
        self.platforms_dir = app_root / "config" / "platforms"
        self.dbc_store_dir = app_root / "dbc_store"
        self.platforms_dir.mkdir(parents=True, exist_ok=True)
        self.dbc_store_dir.mkdir(parents=True, exist_ok=True)

        # empty while creating a platform that hasn't been saved yet
        self._current_slug: Optional[str] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(10)
        outer.addWidget(label("Platforms", "title"))
        outer.addWidget(label(
            "A platform ties a vehicle to its DBC file and the signals that matter most for it.",
            "muted", wrap=True,
        ))
        # platform list on the left, editor form on the right
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_editor_panel())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 540])
        outer.addWidget(splitter, stretch=1)

        close_box = QDialogButtonBox(QDialogButtonBox.Close)
        close_box.rejected.connect(self.accept)
        outer.addWidget(close_box)

        self._refresh_list()

    # -- left: platform list --

    def _build_list_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 8, 0)
        buttons = QHBoxLayout()
        buttons.addWidget(button("New", variant="primary", icon_name="add",
                                 on_click=self._on_new_platform))
        buttons.addStretch()
        buttons.addWidget(button("Delete", variant="danger", icon_name="delete",
                                 tooltip="Delete the selected platform config",
                                 on_click=self._on_delete_platform))
        layout.addLayout(buttons)
        self.platform_list = QListWidget()
        self.platform_list.itemClicked.connect(self._on_select_platform)
        layout.addWidget(self.platform_list)
        return w

    # invalid files stay listed in red so they can be found and fixed
    def _refresh_list(self, select_slug: Optional[str] = None) -> None:
        self.platform_list.clear()
        for slug, cfg in sorted(discover_platforms(self.platforms_dir).items()):
            text = f"{slug}  (invalid file)" if isinstance(cfg, ConfigLoadError) else cfg.name
            item = QListWidgetItem(icon("car"), text)
            item.setData(Qt.UserRole, slug)
            item.setToolTip(str(cfg) if isinstance(cfg, ConfigLoadError) else f"{slug}.yaml")
            if isinstance(cfg, ConfigLoadError):
                item.setForeground(QColor("#e05a4e"))
            self.platform_list.addItem(item)
            if select_slug == slug:
                self.platform_list.setCurrentItem(item)

    def _on_select_platform(self, item: QListWidgetItem) -> None:
        slug = item.data(Qt.UserRole)
        path = self.platforms_dir / f"{slug}.yaml"
        try:
            config = load_platform_config(path)
        except ConfigLoadError as exc:
            QMessageBox.critical(self, "Invalid platform config", str(exc))
            return
        self._load_into_editor(slug, config)

    def _on_new_platform(self) -> None:
        self.platform_list.clearSelection()
        self._load_into_editor(None, PlatformConfig(name="", dbc_path=""))

    # deletes the yaml only, the dbc file stays in dbc_store/
    def _on_delete_platform(self) -> None:
        item = self.platform_list.currentItem()
        if not item:
            return
        slug = item.data(Qt.UserRole)
        confirm = QMessageBox.question(
            self, "Delete platform",
            f"Delete the platform config {slug!r}? This does not delete its .dbc file."
        )
        if confirm != QMessageBox.Yes:
            return
        (self.platforms_dir / f"{slug}.yaml").unlink(missing_ok=True)
        self._refresh_list()
        self._on_new_platform()

    # -- right: editor form --

    # name, description, dbc, image, important values and metadata
    def _build_editor_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(8)
        self.editor_title = label("New platform", "section")
        layout.addWidget(self.editor_title)
        form = QFormLayout()
        form.setSpacing(8)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. 2026 EV Chassis A")
        self.description_input = QPlainTextEdit()
        self.description_input.setPlaceholderText("Optional -- shown when opening a log")
        self.description_input.setMaximumHeight(60)

        dbc_row = QHBoxLayout()
        self.dbc_path_label = QLabel("(none)")
        self.dbc_path_label.setProperty("role", "muted")
        dbc_row.addWidget(self.dbc_path_label, stretch=1)
        dbc_row.addWidget(button("Import DBC…", icon_name="database", on_click=self._on_import_dbc))

        image_row = QHBoxLayout()
        self.image_path_label = QLabel("(none)")
        self.image_path_label.setProperty("role", "muted")
        image_row.addWidget(self.image_path_label, stretch=1)
        image_row.addWidget(button("Choose…", icon_name="folder", on_click=self._on_set_image))
        image_row.addWidget(button("Clear", variant="subtle",
                                   on_click=lambda: self.image_path_label.setText("(none)")))

        form.addRow("Name", self.name_input)
        form.addRow("Description", self.description_input)
        form.addRow("DBC file", dbc_row)
        form.addRow("Image", image_row)
        layout.addLayout(form)

        layout.addWidget(label("Important values", "section"))
        layout.addWidget(label("Signal names to show first, one per line.", "muted"))
        self.important_values_input = QPlainTextEdit()
        self.important_values_input.setMaximumHeight(100)
        layout.addWidget(self.important_values_input)

        meta_head = QHBoxLayout()
        meta_head.addWidget(label("Metadata", "section"))
        meta_head.addStretch()
        meta_head.addWidget(button("Add row", variant="subtle", icon_name="add", on_click=lambda:
                                   self.metadata_table.insertRow(self.metadata_table.rowCount())))
        meta_head.addWidget(button("Remove row", variant="subtle", icon_name="delete",
                                   on_click=self._on_remove_metadata_row))
        layout.addLayout(meta_head)
        self.metadata_table = QTableWidget(0, 2)
        self.metadata_table.setHorizontalHeaderLabels(["Key", "Value"])
        self.metadata_table.horizontalHeader().setStretchLastSection(True)
        self.metadata_table.verticalHeader().setVisible(False)
        layout.addWidget(self.metadata_table)

        save_row = QHBoxLayout()
        save_row.addStretch()
        save_row.addWidget(button("Save platform", variant="primary", icon_name="save",
                                  on_click=self._on_save))
        layout.addLayout(save_row)

        self._load_into_editor(None, PlatformConfig(name="", dbc_path=""))
        return w

    def _on_remove_metadata_row(self) -> None:
        row = self.metadata_table.currentRow()
        if row >= 0:
            self.metadata_table.removeRow(row)

    # no slug means a new unsaved platform
    def _load_into_editor(self, slug: Optional[str], config: PlatformConfig) -> None:
        self._current_slug = slug
        self.editor_title.setText(f"Edit {config.name}" if slug else "New platform")
        self.name_input.setText(config.name)
        self.description_input.setPlainText(config.description)
        self.dbc_path_label.setText(config.dbc_path or "(none)")
        self.image_path_label.setText(config.image or "(none)")
        self.important_values_input.setPlainText("\n".join(config.important_values))
        self.metadata_table.setRowCount(0)
        for key, value in (config.metadata or {}).items():
            row = self.metadata_table.rowCount()
            self.metadata_table.insertRow(row)
            self.metadata_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.metadata_table.setItem(row, 1, QTableWidgetItem(str(value)))

    # -- dbc import and image --

    # copies a parsed dbc into dbc_store/, asks before overwriting one with the same name
    def _on_import_dbc(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Import DBC File", "", "DBC Files (*.dbc)")
        if not path_str:
            return
        from core.dbc_handler import DbcHandler

        src = Path(path_str)
        try:
            DbcHandler(src)  # make sure it parses first
        except Exception as exc:
            QMessageBox.critical(self, "Invalid DBC", f"Could not parse this DBC:\n{exc}")
            return

        dest = self.dbc_store_dir / src.name
        if dest.exists() and dest.resolve() != src.resolve():
            confirm = QMessageBox.question(
                self, "File exists",
                f"{src.name} already exists in dbc_store/. Overwrite it?"
            )
            if confirm != QMessageBox.Yes:
                return
        shutil.copy(src, dest)
        self.dbc_path_label.setText(dest.name)

    def _on_set_image(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select Platform Image", "", "Images (*.png *.jpg *.jpeg *.gif)"
        )
        if path_str:
            self.image_path_label.setText(path_str)

    # -- save --

    # needs a name and a dbc, new platforms can't reuse an existing slug
    def _on_save(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Name required", "Give the platform a name before saving.")
            return

        dbc_label = self.dbc_path_label.text()
        if dbc_label == "(none)":
            QMessageBox.warning(self, "DBC required", "Import a .dbc file for this platform first.")
            return

        important_values = [
            line.strip() for line in self.important_values_input.toPlainText().splitlines()
            if line.strip()
        ]
        metadata = {}
        for row in range(self.metadata_table.rowCount()):
            key_item = self.metadata_table.item(row, 0)
            value_item = self.metadata_table.item(row, 1)
            if key_item and key_item.text().strip():
                metadata[key_item.text().strip()] = value_item.text() if value_item else ""

        image_label = self.image_path_label.text()
        image = None if image_label == "(none)" else image_label

        config = PlatformConfig(
            name=name,
            description=self.description_input.toPlainText(),
            dbc_path=dbc_label,
            image=image,
            important_values=important_values,
            metadata=metadata,
        )

        slug = self._current_slug or _slugify(name)
        path = self.platforms_dir / f"{slug}.yaml"
        if self._current_slug is None and path.exists():
            QMessageBox.critical(
                self, "Slug already exists",
                f"A platform config already exists at {path.name} -- rename this platform."
            )
            return

        save_platform_config(path, config)
        self._current_slug = slug
        self._refresh_list(select_slug=slug)
        QMessageBox.information(self, "Saved", f"Platform saved to {path.name}")
