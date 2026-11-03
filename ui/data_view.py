#--------------------#
# data_view.py
# data analysis page of a session: per signal statistics table, over the whole log or between the graph cursors
#--------------------#
from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QMenu, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.log_parser import LogParser
from core.signal_stats import SignalStats, compute_stats, format_number, label_text
from core.theme_loader import derived_colors
from ui.widgets import Card, StatTile, button, icon, label, search_field

SHOW_ALL, SHOW_IMPORTANT, SHOW_PLOTTED = "All signals", "Important signals", "Plotted signals"
RANGE_WHOLE, RANGE_CURSORS = "Whole log", "Between cursors A and B"


# sorts by the number in UserRole instead of the display text, blanks sort last
class _NumberItem(QTableWidgetItem):
    def __init__(self, value: Optional[float], text: str):
        super().__init__(text)
        self.setData(Qt.UserRole, value)
        self.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def __lt__(self, other) -> bool:
        a, b = self.data(Qt.UserRole), other.data(Qt.UserRole)
        if a is None or b is None:
            return a is not None
        return a < b


class DataAnalysisView(QWidget):
    plot_requested = Signal(str)
    # names and True to add them to the important signals, False to remove them
    important_changed = Signal(list, bool)

    COLUMNS = ["Signal", "Unit", "Samples", "Rate (Hz)", "Min", "Max", "Mean", "Std dev",
               "Min at (s)", "Max at (s)"]

    def __init__(self, log_parser: LogParser, theme,
                 important_names: Callable[[], list[str]],
                 plotted_names: Callable[[], list[str]],
                 cursor_range: Callable[[], Optional[tuple[float, float]]],
                 parent=None):
        super().__init__(parent)
        self.log_parser = log_parser
        self._important_names = important_names
        self._plotted_names = plotted_names
        self._cursor_range = cursor_range
        self._stats: dict[str, SignalStats] = {}
        self._dirty = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.filter_input = search_field("Filter signals", lambda _t: self._apply_filter())
        tools.addWidget(self.filter_input, stretch=1)
        tools.addWidget(label("Show", "muted"))
        self.show_combo = QComboBox()
        self.show_combo.addItems([SHOW_ALL, SHOW_IMPORTANT, SHOW_PLOTTED])
        self.show_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        tools.addWidget(self.show_combo)
        tools.addWidget(label("over", "muted"))
        self.range_combo = QComboBox()
        self.range_combo.addItems([RANGE_WHOLE, RANGE_CURSORS])
        self.range_combo.setToolTip("Place cursors A and B on the Graph page to analyse just that stretch")
        self.range_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        tools.addWidget(self.range_combo)
        tools.addWidget(button("Plot on graph", icon_name="graph",
                               tooltip="Plot the selected signals (or double-click a row)",
                               on_click=self._plot_selected))
        layout.addLayout(tools)
        self.range_note = label("", "muted", wrap=True)
        layout.addWidget(self.range_note)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSortIndicator(0, Qt.AscendingOrder)  # by name until a header is clicked
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # names get the room, numbers stay compact, a narrow window scrolls sideways
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 60)
        for col in range(2, len(self.COLUMNS)):
            self.table.setColumnWidth(col, 80)
        self.table.itemDoubleClicked.connect(lambda item: self.plot_requested.emit(self._row_name(item.row())))
        self.table.currentCellChanged.connect(lambda row, *_: self._show_detail(self._row_name(row)))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        splitter.addWidget(self.table)
        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([800, 300])
        layout.addWidget(splitter, stretch=1)
        self.apply_theme(theme)

    # stat tiles, time of peaks and the value distribution for the selected signal
    def _build_detail(self) -> QWidget:
        card = Card("Selected signal")
        card.setMinimumWidth(260)
        self.detail_title = label("Select a signal in the table.", "muted", wrap=True)
        self.detail_title.setTextFormat(Qt.RichText)
        card.add(self.detail_title)
        tiles = QHBoxLayout()
        tiles.setSpacing(6)
        self.stat_max, self.stat_min = StatTile("Max"), StatTile("Min")
        self.stat_avg, self.stat_std = StatTile("Average"), StatTile("Std dev")
        for tile in (self.stat_max, self.stat_min):
            tiles.addWidget(tile)
        card.add(tiles)
        tiles2 = QHBoxLayout()
        tiles2.setSpacing(6)
        for tile in (self.stat_avg, self.stat_std):
            tiles2.addWidget(tile)
        card.add(tiles2)
        self.detail_info = label("", "muted", wrap=True)
        self.detail_info.setTextFormat(Qt.RichText)
        card.add(self.detail_info)
        card.add(label("Distribution", "section"))
        self.histogram = pg.PlotWidget()
        self.histogram.setMinimumHeight(160)
        self.histogram.setMouseEnabled(x=False, y=False)
        self.histogram.hideButtons()
        self.histogram.getPlotItem().setMenuEnabled(False)
        card.add(self.histogram, stretch=1)
        return card

    def apply_theme(self, theme) -> None:
        self.theme = theme
        if theme is None:
            return
        colors = derived_colors(theme)
        self._bar_color = colors["accent"]
        self.histogram.setBackground(colors["surface"])
        pen = pg.mkPen(color=colors["muted"], width=1)
        for name in ("left", "bottom"):
            axis = self.histogram.getAxis(name)
            axis.setPen(pen)
            axis.setTextPen(pen)
        current = self._row_name(self.table.currentRow())
        if current:
            self._show_detail(current)

    # -- refreshing --

    # recomputes when shown, so cursor moves on the graph page cost nothing until you look
    def mark_dirty(self) -> None:
        self._dirty = True
        if self.isVisible():
            self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._dirty:
            self.refresh()

    def _names(self) -> list[str]:
        choice = self.show_combo.currentText()
        if choice == SHOW_IMPORTANT:
            names = self._important_names()
        elif choice == SHOW_PLOTTED:
            names = self._plotted_names()
        else:
            names = list(self.log_parser.decoded)
        return [n for n in names if n in self.log_parser.decoded]

    def refresh(self) -> None:
        self._dirty = False
        rng = None
        if self.range_combo.currentText() == RANGE_CURSORS:
            rng = self._cursor_range()
            if rng is None:
                self.range_note.setText(
                    "Cursors A and B aren't both placed on the Graph page, so this shows the whole log."
                )
            else:
                lo, hi = sorted(rng)
                self.range_note.setText(f"From {lo:.3f} s to {hi:.3f} s ({hi - lo:.3f} s).")
        else:
            self.range_note.setText("")
        self.range_note.setVisible(bool(self.range_note.text()))

        current = self._row_name(self.table.currentRow())
        self._stats = {}
        for name in self._names():
            series = self.log_parser.decoded[name]
            self._stats[name] = compute_stats(name, series.timestamps, series.values, series.unit,
                                              *(rng or (None, None)))
        self._fill_table()
        self._apply_filter()
        self._select(current)

    def _fill_table(self) -> None:
        sort_col = self.table.horizontalHeader().sortIndicatorSection()
        sort_order = self.table.horizontalHeader().sortIndicatorOrder()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self._stats))
        important = set(self._important_names())
        for r, st in enumerate(self._stats.values()):
            name_item = QTableWidgetItem(st.name)
            name_item.setData(Qt.UserRole, st.name)
            if st.name in important:
                name_item.setIcon(icon("star_filled"))
                name_item.setToolTip("Important signal")
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, QTableWidgetItem(st.unit))
            cells = [
                (float(st.samples), str(st.samples)),
                (st.rate_hz, format_number(st.rate_hz)),
                (st.minimum, format_number(st.minimum)),
                (st.maximum, format_number(st.maximum)),
                (st.mean, format_number(st.mean)),
                (st.std, format_number(st.std)),
                (st.time_of_min, format_number(st.time_of_min)),
                (st.time_of_max, format_number(st.time_of_max)),
            ]
            if not st.numeric:
                if st.distinct:
                    cells[4] = (None, f"{st.distinct} state" + ("s" if st.distinct != 1 else ""))
            for c, (value, text) in enumerate(cells, start=2):
                self.table.setItem(r, c, _NumberItem(value, text))
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(sort_col, sort_order)

    def _apply_filter(self) -> None:
        text = self.filter_input.text().strip().lower()
        for r in range(self.table.rowCount()):
            self.table.setRowHidden(r, bool(text) and text not in self._row_name(r).lower())

    def _row_name(self, row: int) -> str:
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item is not None else ""

    def _select(self, name: str) -> None:
        for r in range(self.table.rowCount()):
            if self._row_name(r) == name:
                self.table.setCurrentCell(r, 0)
                return
        self._show_detail("")

    def _selected_names(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        return [self._row_name(r) for r in rows]

    # -- detail pane --

    def _show_detail(self, name: str) -> None:
        st = self._stats.get(name)
        self.histogram.clear()
        if st is None:
            self.detail_title.setText("Select a signal in the table.")
            self.detail_info.setText("")
            for tile in (self.stat_max, self.stat_min, self.stat_avg, self.stat_std):
                tile.set_value("—")
            return
        unit = f" ({st.unit})" if st.unit else ""
        self.detail_title.setText(f"<b>{st.name}</b>{unit}")
        self.stat_max.set_value(format_number(st.maximum))
        self.stat_min.set_value(format_number(st.minimum))
        self.stat_avg.set_value(format_number(st.mean))
        self.stat_std.set_value(format_number(st.std))
        lines = [f"{st.samples} samples"]
        if st.rate_hz:
            lines[0] += f" at about {st.rate_hz:.3g} Hz"
        if st.start is not None:
            lines.append(f"From {st.start:.3f} s to {st.end:.3f} s")
        if st.numeric and st.time_of_max is not None:
            lines.append(f"Max at {st.time_of_max:.3f} s, min at {st.time_of_min:.3f} s")
        if not st.numeric and st.distinct:
            lines.append(f"{st.distinct} states, most often <b>{st.most_common}</b>")
        self.detail_info.setText("<br>".join(lines))
        self._draw_distribution(name)

    # histogram for numbers, one bar per state for enum signals, over the same range as the table
    def _draw_distribution(self, name: str) -> None:
        series = self.log_parser.decoded[name]
        values, timestamps = series.values, series.timestamps
        rng = self._cursor_range() if self.range_combo.currentText() == RANGE_CURSORS else None
        if rng is not None:
            lo, hi = sorted(rng)
            values = values[(timestamps >= lo) & (timestamps <= hi)]
        if not len(values):
            return
        brush = pg.mkBrush(getattr(self, "_bar_color", "#4a90d9"))
        bottom = self.histogram.getAxis("bottom")
        if np.issubdtype(values.dtype, np.number):
            finite = values[np.isfinite(values)]
            if not len(finite):
                return
            counts, edges = np.histogram(finite, bins=min(40, max(1, len(np.unique(finite)))))
            self.histogram.addItem(pg.BarGraphItem(x0=edges[:-1], x1=edges[1:], height=counts,
                                                   brush=brush, pen=None))
            bottom.setTicks(None)
        else:
            labels, counts = np.unique(values, return_counts=True)
            xs = np.arange(len(labels))
            self.histogram.addItem(pg.BarGraphItem(x=xs, width=0.7, height=counts, brush=brush, pen=None))
            bottom.setTicks([[(int(x), label_text(lbl)) for x, lbl in zip(xs, labels)]])
        self.histogram.autoRange()

    # -- actions --

    def _plot_selected(self) -> None:
        for name in self._selected_names():
            self.plot_requested.emit(name)

    def _context_menu(self, pos) -> None:
        names = self._selected_names()
        if not names:
            return
        important = set(self._important_names())
        menu = QMenu(self)
        menu.addAction(icon("graph"), "Plot on graph", self._plot_selected)
        to_add = [n for n in names if n not in important]
        to_remove = [n for n in names if n in important]
        if to_add:
            menu.addAction(icon("star_filled"), "Add to important signals",
                           lambda: self.important_changed.emit(to_add, True))
        if to_remove:
            menu.addAction(icon("star"), "Remove from important signals",
                           lambda: self.important_changed.emit(to_remove, False))
        menu.exec(self.table.viewport().mapToGlobal(pos))
