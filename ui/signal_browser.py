#--------------------#
# signal_browser.py
# advanced page: unknown can ids with force decode, dbc structure table and signal editor
#--------------------#
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCompleter, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLineEdit,
    QListWidget, QMessageBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from core.dbc_handler import DbcHandler, SignalEdit
from core.log_parser import LogParser
from ui.widgets import Card, button, icon, label, search_field


# the advanced page of a session, shown in advanced mode only
class SignalBrowser(QWidget):
    # signal name to plot, SessionWidget sends it to its TraceView and shows the graph
    plot_requested = Signal(str)
    # names force decode just added to the log, SessionWidget refreshes its signal lists
    signals_added = Signal(list)

    def __init__(self, dbc_handler: DbcHandler, log_parser: LogParser, parent=None):
        super().__init__(parent)
        self.dbc_handler = dbc_handler
        self.log_parser = log_parser

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_not_decoded_tab(), icon("list"),
                         f"Unknown CAN IDs ({len(self.log_parser.not_decoded_ids)})")
        self.tabs.addTab(self._build_dbc_structure_tab(), icon("database"), "DBC structure")
        layout.addWidget(self.tabs)

    # -- not decoded and force decode --
    # three columns for the three steps: pick an id, pick a message, plot a result

    def _build_not_decoded_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 10, 0, 0)
        outer.setSpacing(8)
        outer.addWidget(label(
            "CAN IDs in this log that the platform's DBC has no message for. Force decode reads "
            "one of them with an existing message's layout; the resulting signals join every "
            "page of this session until it is closed.", "muted", wrap=True,
        ))
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter, stretch=1)

        left = Card("1. Pick an unknown CAN ID")
        self.not_decoded_list = QListWidget()
        for raw_id in sorted(self.log_parser.not_decoded_ids):
            self.not_decoded_list.addItem(f"0x{raw_id:X}")
        left.add(self.not_decoded_list, stretch=1)
        splitter.addWidget(left)

        middle = Card("2. Decode it as a DBC message")
        mv = middle.body
        self.force_message_input = QLineEdit()
        self.force_message_input.setPlaceholderText("Message name, e.g. EngineData")
        completer = QCompleter(sorted(m.name for m in self.dbc_handler.messages()), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.force_message_input.setCompleter(completer)
        self.force_message_input.returnPressed.connect(self._on_force_decode)
        mv.addWidget(self.force_message_input)
        mv.addWidget(button("Force decode", variant="primary", icon_name="sync",
                            tooltip="Decode the selected ID's frames using this message's layout",
                            on_click=self._on_force_decode))
        mv.addStretch()
        splitter.addWidget(middle)

        right = Card("3. Plot a force-decoded signal")
        self.force_decoded_list = QListWidget()
        self.force_decoded_list.setToolTip("Double-click to plot it on the graph")
        self.force_decoded_list.itemDoubleClicked.connect(lambda _item: self._on_plot_clicked())
        right.add(self.force_decoded_list, stretch=1)
        right.add(button("Plot on graph", icon_name="graph", on_click=self._on_plot_clicked))
        splitter.addWidget(right)
        splitter.setSizes([200, 300, 300])
        return w

    # maps the selected id to the typed message, decodes it and lists the new signals
    def _on_force_decode(self) -> None:
        item = self.not_decoded_list.currentItem()
        message_name = self.force_message_input.text().strip()
        if not item or not message_name:
            QMessageBox.information(
                self, "Pick an ID and a message",
                "Select a CAN ID on the left and enter the DBC message to decode it as."
            )
            return
        raw_id = int(item.text(), 16)
        try:
            self.dbc_handler.force_map(raw_id, message_name)
        except KeyError:
            QMessageBox.critical(
                self, "Unknown message", f"No message named {message_name!r} in this DBC."
            )
            return

        decoded = self.log_parser.apply_force_decode(raw_id)
        if not decoded:
            QMessageBox.warning(
                self, "No frames decoded",
                f"No frames with ID {item.text()} could be decoded against {message_name!r}."
            )
            return

        for name in decoded:
            if not self.force_decoded_list.findItems(name, Qt.MatchExactly):
                self.force_decoded_list.addItem(name)
        self.signals_added.emit(list(decoded))

        frame_count = len(next(iter(decoded.values())).timestamps)
        lines = []
        for name in decoded:
            summary = self.log_parser.summaries.get(name)
            if summary:
                lines.append(
                    f"{name}: max={summary.maximum:.2f} min={summary.minimum:.2f} "
                    f"avg={summary.average:.2f}"
                )
        QMessageBox.information(
            self, "Force-decoded",
            f"Decoded {len(decoded)} signal(s) from {frame_count} frame(s):\n" + "\n".join(lines)
        )

    def _on_plot_clicked(self) -> None:
        item = self.force_decoded_list.currentItem()
        if item:
            self.plot_requested.emit(item.text())

    # -- dbc structure and temp edits --

    # filter, edit and export tools over a read-only message/signal table
    def _build_dbc_structure_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.addWidget(label(
            "Every message and signal in the platform's DBC. Edits apply to this session only; "
            "export the edited DBC to keep them.", "muted", wrap=True,
        ))
        tools = QHBoxLayout()
        self.dbc_filter = search_field("Filter by message or signal", self._apply_dbc_filter)
        tools.addWidget(self.dbc_filter, stretch=1)
        tools.addWidget(button("Edit signal…", icon_name="edit",
                               tooltip="Edit the selected signal (or double-click a row)",
                               on_click=self._edit_selected))
        tools.addWidget(button("Export edited DBC…", icon_name="export", on_click=self._export_dbc))
        layout.addLayout(tools)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Message", "Signal", "Unit", "Scale", "Offset"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.itemDoubleClicked.connect(self._open_edit_dialog)
        self._refresh_table()
        layout.addWidget(self.table)
        return w

    # one row per signal, filled once, an edit only rewrites its own row
    def _refresh_table(self) -> None:
        rows = [(msg.name, sig) for msg in self.dbc_handler.messages() for sig in msg.signals]
        self.table.setRowCount(len(rows))
        for r, (msg_name, sig) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(msg_name))
            self._fill_signal_cells(r, sig.name, sig.unit, sig.scale, sig.offset)

    def _fill_signal_cells(self, row: int, name: str, unit, scale, offset) -> None:
        for col, value in enumerate((name, unit or "", str(scale), str(offset)), start=1):
            self.table.setItem(row, col, QTableWidgetItem(value))

    def _apply_dbc_filter(self, text: str) -> None:
        text = text.strip().lower()
        for r in range(self.table.rowCount()):
            haystack = f"{self.table.item(r, 0).text()} {self.table.item(r, 1).text()}".lower()
            self.table.setRowHidden(r, bool(text) and text not in haystack)

    def _edit_selected(self) -> None:
        item = self.table.currentItem()
        if item is None:
            QMessageBox.information(self, "No signal selected", "Select a signal in the table first.")
            return
        self._open_edit_dialog(item)

    def _open_edit_dialog(self, item: QTableWidgetItem) -> None:
        row = item.row()
        message_name = self.table.item(row, 0).text()
        signal_name = self.table.item(row, 1).text()
        dlg = SignalEditDialog(self.dbc_handler, message_name, signal_name, self)
        if dlg.exec():
            detail = self.dbc_handler.signal_detail(message_name, dlg.name_input.text() or signal_name)
            self._fill_signal_cells(row, detail["name"], detail["unit"], detail["scale"], detail["offset"])
            self._apply_dbc_filter(self.dbc_filter.text())

    # saves the edited dbc as a new file
    def _export_dbc(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(self, "Export Edited DBC", "", "DBC Files (*.dbc)")
        if not path_str:
            return
        try:
            self.dbc_handler.export_edited_dbc(Path(path_str))
            QMessageBox.information(self, "Exported", f"Saved to {path_str}")
        except ValueError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))


# -- signal editor --

# field-level only (name, unit, scale, offset), not a full dbc editor
class SignalEditDialog(QDialog):
    def __init__(self, dbc_handler: DbcHandler, message_name: str, signal_name: str, parent=None):
        super().__init__(parent)
        self.dbc_handler = dbc_handler
        self.message_name = message_name
        self.signal_name = signal_name
        self.setWindowTitle(f"Edit {signal_name}")
        self.setMinimumWidth(380)

        detail = dbc_handler.signal_detail(message_name, signal_name)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(10)
        outer.addWidget(label(signal_name, "title"))
        outer.addWidget(label(
            f"In message {message_name}. Changes apply to this session until you "
            "export the edited DBC.", "muted", wrap=True,
        ))
        layout = QFormLayout()
        layout.setSpacing(10)
        outer.addLayout(layout)

        self.name_input = QLineEdit(detail["name"])
        self.unit_input = QLineEdit(detail["unit"] or "")
        self.scale_input = QDoubleSpinBox()
        self.scale_input.setDecimals(6)
        self.scale_input.setRange(-1e9, 1e9)
        self.scale_input.setValue(detail["scale"] or 1.0)
        self.offset_input = QDoubleSpinBox()
        self.offset_input.setDecimals(6)
        self.offset_input.setRange(-1e9, 1e9)
        self.offset_input.setValue(detail["offset"] or 0.0)

        layout.addRow("Name", self.name_input)
        layout.addRow("Unit", self.unit_input)
        layout.addRow("Scale", self.scale_input)
        layout.addRow("Offset", self.offset_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setProperty("variant", "primary")
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # applies the edit in memory for this session only
    def _apply(self) -> None:
        edit = SignalEdit(
            message_name=self.message_name,
            signal_name=self.signal_name,
            new_name=self.name_input.text() or None,
            unit=self.unit_input.text() or None,
            scale=self.scale_input.value(),
            offset=self.offset_input.value(),
        )
        self.dbc_handler.apply_temp_edit(edit)
        self.accept()
