#--------------------#
# tabular_view.py
# table page of a session: chosen signals side by side on one time axis, with csv export
# cells are looked up when drawn, so a long log never builds millions of table items
#--------------------#
from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter, QTableView, QVBoxLayout, QWidget,
)

from core.log_parser import LogParser, SignalSeries
from core.signal_stats import format_value, label_text, sample_index_at, sample_indices_at
from core.theme_loader import derived_colors
from ui.widgets import Card, button, filter_list, label, search_field

# row spacing choices, None means one row per received sample
ROW_STEPS = [("Every sample", None), ("Every 10 ms", 0.01), ("Every 100 ms", 0.1), ("Every 1 s", 1.0)]


# time column plus one column per signal, each cell is the value held at that row's time
class TimeAlignedModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.times = np.array([], dtype=float)
        self.columns: list[SignalSeries] = []
        self.held_color = QColor("#888888")

    def set_data(self, times: np.ndarray, columns: list[SignalSeries]) -> None:
        self.beginResetModel()
        self.times = times
        self.columns = columns
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.times)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else 1 + len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal or role != Qt.DisplayRole:
            return None
        if section == 0:
            return "Time (s)"
        series = self.columns[section - 1]
        return f"{series.name} ({series.unit})" if series.unit else series.name

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        t = float(self.times[index.row()])
        if index.column() == 0:
            if role == Qt.DisplayRole:
                return f"{t:.4f}"
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return None
        series = self.columns[index.column() - 1]
        idx = sample_index_at(series.timestamps, t)
        if role == Qt.DisplayRole:
            return "" if idx < 0 else format_value(series.values[idx])
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        # values carried over from an earlier frame are dimmed, fresh frames are not
        if role == Qt.ForegroundRole and idx >= 0 and series.timestamps[idx] != t:
            return self.held_color
        if role == Qt.ToolTipRole and idx >= 0:
            return f"Received at {float(series.timestamps[idx]):.4f} s"
        return None

    # the row at or just before t
    def row_at(self, t: float) -> int:
        return max(0, sample_index_at(self.times, t))


class TabularView(QWidget):
    def __init__(self, log_parser: LogParser, theme,
                 important_names: Callable[[], list[str]],
                 plotted_names: Callable[[], list[str]],
                 cursor_pos: Callable[[str], Optional[float]],
                 parent=None):
        super().__init__(parent)
        self.log_parser = log_parser
        self._important_names = important_names
        self._plotted_names = plotted_names
        self._cursor_pos = cursor_pos
        self._defaults_applied = False

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter)
        splitter.addWidget(self._build_picker())

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 0, 0, 0)
        rv.setSpacing(6)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        tools.addWidget(label("Rows", "muted"))
        self.step_combo = QComboBox()
        for text, step in ROW_STEPS:
            self.step_combo.addItem(text, step)
        self.step_combo.setToolTip("One row per received frame, or a row at a fixed interval")
        self.step_combo.currentIndexChanged.connect(lambda _i: self.rebuild())
        tools.addWidget(self.step_combo)
        for key in ("A", "B"):
            tools.addWidget(button(f"Go to cursor {key}", variant="subtle", icon_name="target",
                                   tooltip=f"Scroll to the row at cursor {key} on the Graph page",
                                   on_click=lambda _=False, k=key: self.go_to_cursor(k)))
        tools.addStretch()
        self.info_label = label("", "muted")
        tools.addWidget(self.info_label)
        self.export_btn = button("Export CSV…", icon_name="export", on_click=self._export_csv)
        tools.addWidget(self.export_btn)
        rv.addLayout(tools)

        self.model = TimeAlignedModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)  # keeps huge tables fast
        self.table.verticalHeader().setDefaultSectionSize(26)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setDefaultSectionSize(140)
        rv.addWidget(self.table, stretch=1)
        self.empty_hint = label("Tick signals on the left to add them as columns.", "muted")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        rv.addWidget(self.empty_hint, stretch=1)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 820])
        self.apply_theme(theme)
        self.rebuild()

    # checklist of every signal with quick picks
    def _build_picker(self) -> QWidget:
        card = Card("Columns")
        card.setMinimumWidth(280)
        self.column_list = QListWidget()
        self.column_list.itemChanged.connect(lambda _item: self.rebuild())
        card.add(search_field("Filter signals", lambda text: filter_list(self.column_list, text)))
        quick = QHBoxLayout()
        quick.setSpacing(4)
        quick.addWidget(button("Important", variant="subtle",
                               tooltip="Show the important signals",
                               on_click=lambda: self.set_columns(self._important_names())))
        quick.addWidget(button("Plotted", variant="subtle",
                               tooltip="Show the signals plotted on the graph",
                               on_click=lambda: self.set_columns(self._plotted_names())))
        quick.addWidget(button("None", variant="subtle", on_click=lambda: self.set_columns([])))
        quick.addStretch()
        card.add(quick)
        card.add(self.column_list, stretch=1)
        self.refresh_signal_list()
        return card

    def apply_theme(self, theme) -> None:
        if theme is not None:
            self.model.held_color = QColor(derived_colors(theme)["muted"])
            self.table.viewport().update()

    # adds any new signals (force decode) without losing the ticks
    def refresh_signal_list(self) -> None:
        checked = set(self.checked_names())
        self.column_list.blockSignals(True)
        self.column_list.clear()
        for name in sorted(self.log_parser.decoded, key=str.lower):
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in checked else Qt.Unchecked)
            self.column_list.addItem(item)
        self.column_list.blockSignals(False)

    def checked_names(self) -> list[str]:
        if not hasattr(self, "column_list"):
            return []
        return [self.column_list.item(i).text() for i in range(self.column_list.count())
                if self.column_list.item(i).checkState() == Qt.Checked]

    def set_columns(self, names: list[str]) -> None:
        wanted = set(names)
        self.column_list.blockSignals(True)
        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            item.setCheckState(Qt.Checked if item.text() in wanted else Qt.Unchecked)
        self.column_list.blockSignals(False)
        self.rebuild()

    # the first time the page opens, start from what's plotted, else the important signals
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._defaults_applied:
            self._defaults_applied = True
            if not self.checked_names():
                self.set_columns(self._plotted_names() or self._important_names())

    # -- building the rows --

    def _selected_series(self) -> list[SignalSeries]:
        return [self.log_parser.decoded[n] for n in self.checked_names() if n in self.log_parser.decoded]

    def _time_axis(self, columns: list[SignalSeries]) -> np.ndarray:
        columns = [s for s in columns if len(s.timestamps)]
        if not columns:
            return np.array([], dtype=float)
        step = self.step_combo.currentData()
        if step is None:
            return np.unique(np.concatenate([s.timestamps for s in columns]))
        start = min(float(s.timestamps[0]) for s in columns)
        end = max(float(s.timestamps[-1]) for s in columns)
        return np.arange(start, end + step / 2, step)

    def rebuild(self) -> None:
        columns = self._selected_series()
        times = self._time_axis(columns)
        self.model.set_data(times, columns)
        has_columns = bool(columns)
        self.table.setVisible(has_columns)
        self.empty_hint.setVisible(not has_columns)
        self.export_btn.setEnabled(has_columns)
        self.info_label.setText(
            f"{len(times):,} rows  •  dimmed values are held from an earlier frame" if has_columns else ""
        )

    def go_to_cursor(self, key: str) -> None:
        t = self._cursor_pos(key)
        if t is None:
            self.info_label.setText(f"Cursor {key} isn't placed on the Graph page yet.")
            return
        if not self.model.rowCount():
            return
        index = self.model.index(self.model.row_at(t), 0)
        self.table.scrollTo(index, QAbstractItemView.PositionAtCenter)
        self.table.selectRow(index.row())

    # -- export --

    def _export_csv(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(self, "Export Table as CSV", "", "CSV Files (*.csv)")
        if not path_str:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            write_csv(Path(path_str), self.model.times, self.model.columns)
        except OSError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QApplication.restoreOverrideCursor()
        self.info_label.setText(f"Saved {len(self.model.times):,} rows to {Path(path_str).name}")


# same rows and held values as the table, blank before a signal's first frame
def write_csv(path: Path, times: np.ndarray, columns: list[SignalSeries]) -> None:
    cells = []
    for series in columns:
        idx = sample_indices_at(series.timestamps, times)
        valid = idx >= 0
        held = series.values[np.where(valid, idx, 0)] if len(series.values) else np.array([])
        if np.issubdtype(series.values.dtype, np.number):
            texts = [repr(float(v)) if ok else "" for v, ok in zip(held, valid)]
        else:
            texts = [label_text(v) if ok else "" for v, ok in zip(held, valid)]
        cells.append(texts)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time_s"] + [f"{s.name} ({s.unit})" if s.unit else s.name for s in columns])
        for r, t in enumerate(times):
            writer.writerow([f"{t:.6f}"] + [col[r] for col in cells])
