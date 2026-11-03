#--------------------#
# trace_view.py
# plot toolbar, the plot, cursor readout and snap row, and the plotted signals table (values at cursors, hide/show/remove)
# why a table instead of the pyqtgraph legend, see docs/ARCHITECTURE.md, trace view
#--------------------#
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.plot_engine import PlotEngine
from core.signal_stats import format_number, sample_index_at
from core.theme_loader import derived_colors, next_palette_color
from ui.help_viewer import make_help_button
from ui.widgets import button, icon, label, signal_names_from_mime


class TraceView(QWidget):
    # signal names dragged onto the plot, SessionWidget plots them
    signals_dropped = Signal(list)
    # a cursor moved, appeared or was hidden
    cursors_changed = Signal()

    COL_NAME, COL_A, COL_B, COL_DELTA, COL_TOGGLE, COL_REMOVE = range(6)

    def __init__(self, theme, help_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.help_dir = help_dir
        # per signal state, keyed by name, insertion order = plot order
        # values are what is drawn (codes for enum signals), labels turn codes back into text
        self._series_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self._colors: dict[str, str] = {}
        self._visible: dict[str, bool] = {}
        self._units: dict[str, str] = {}
        self._labels: dict[str, Optional[list[str]]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(self._build_toolbar())

        # plot card on top, cursor bar and plotted signals table below
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        plot_frame = QFrame()
        plot_frame.setProperty("card", True)
        pf = QVBoxLayout(plot_frame)
        pf.setContentsMargins(6, 6, 6, 6)
        self.plot = PlotEngine()
        self.plot.cursor_moved.connect(lambda _key, _x: self._on_cursor_changed())
        self.plot.cursor_toggled.connect(self._on_cursor_toggled)
        # dropping signals from the sidebar lists plots them
        self.plot.setAcceptDrops(True)
        self.plot.viewport().installEventFilter(self)
        pf.addWidget(self.plot)
        splitter.addWidget(plot_frame)

        table_box = QWidget()
        tb = QVBoxLayout(table_box)
        tb.setContentsMargins(0, 4, 0, 0)
        tb.setSpacing(6)
        tb.addLayout(self._build_cursor_bar())
        self.signal_table = QTableWidget(0, 6)
        self.signal_table.setHorizontalHeaderLabels(
            ["Signal", "At cursor A", "At cursor B", "Δ (B − A)", "", ""]
        )
        self.signal_table.verticalHeader().setVisible(False)
        self.signal_table.setShowGrid(False)
        self.signal_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.signal_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.signal_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.signal_table.setMinimumHeight(110)
        self.signal_table.setToolTip("Select a row to make it the snap target")
        self.signal_table.currentCellChanged.connect(lambda row, *_: self._on_row_selected(row))
        header = self.signal_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        for col, width in ((self.COL_A, 130), (self.COL_B, 130), (self.COL_DELTA, 120),
                           (self.COL_TOGGLE, 96), (self.COL_REMOVE, 110)):
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.signal_table.setColumnWidth(col, width)
        self.signal_table.verticalHeader().setDefaultSectionSize(36)
        tb.addWidget(self.signal_table)
        self.empty_hint = label(
            "Nothing plotted yet. Click a signal on the left, or drag it onto the plot.", "muted"
        )
        tb.addWidget(self.empty_hint)
        splitter.addWidget(table_box)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 190])
        layout.addWidget(splitter, stretch=1)

        self.apply_theme(theme)
        self._refresh_cursor_columns()
        self._refresh_empty_hint()

    # fit and cursor toggles on the left, clear on the right
    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(button("Fit to data", variant="subtle", icon_name="zoom_fit",
                             tooltip="Zoom to show every plotted trace",
                             on_click=lambda: self.plot.autoRange()))
        self.cursor_buttons: dict[str, object] = {}
        for key in PlotEngine.CURSOR_KEYS:
            btn = button(f"Cursor {key}", variant="subtle", icon_name="target",
                         tooltip=f"Show or hide cursor {key}. "
                                 + ("Click the plot to place it." if key == "A"
                                    else "Shift+click the plot to place it."))
            btn.setCheckable(True)
            btn.toggled.connect(lambda on, k=key: self._on_cursor_button(k, on))
            self.cursor_buttons[key] = btn
            row.addWidget(btn)
        if self.help_dir is not None:
            row.addWidget(make_help_button(self.help_dir, "graph_cursors", "Graph Cursors", self))
        row.addSpacing(10)
        # cursor times and the gap between them, or how to place one while none are shown
        self.cursor_readout = label("", "muted")
        self.cursor_readout.setTextFormat(Qt.RichText)
        row.addWidget(self.cursor_readout)
        row.addStretch()
        self.clear_btn = button("Clear plot", variant="subtle", icon_name="delete",
                                tooltip="Remove every trace from the plot", on_click=self.clear)
        row.addWidget(self.clear_btn)
        return row

    # table title on the left, "snap cursor A to the max of <signal> in the whole log" on the right
    def _build_cursor_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        self.table_title = label("Plotted signals", "section")
        row.addWidget(self.table_title)
        row.addStretch()

        row.addWidget(label("Snap", "muted"))
        self.snap_cursor = QComboBox()
        self.snap_cursor.addItems([f"Cursor {k}" for k in PlotEngine.CURSOR_KEYS])
        self.snap_cursor.setToolTip("Cursor to move")
        row.addWidget(self.snap_cursor)
        row.addWidget(label("to the", "muted"))
        self.snap_mode = QComboBox()
        self.snap_mode.addItems(["Max", "Min"])
        self.snap_mode.setToolTip("Peak to snap to")
        row.addWidget(self.snap_mode)
        row.addWidget(label("of", "muted"))
        self.snap_signal = QComboBox()
        self.snap_signal.setMinimumContentsLength(14)
        self.snap_signal.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.snap_signal.setToolTip("Signal whose peak the cursor snaps to (or select its row below)")
        row.addWidget(self.snap_signal)
        row.addWidget(label("in", "muted"))
        self.snap_scope = QComboBox()
        self.snap_scope.addItems(["Whole log", "Visible window"])
        self.snap_scope.setToolTip("Search the whole log, or only the zoomed-in range")
        row.addWidget(self.snap_scope)
        self.snap_btn = button("Snap", icon_name="target", on_click=self._on_snap,
                               tooltip="Move the chosen cursor to the chosen signal's peak")
        row.addWidget(self.snap_btn)
        return row

    # recolors the plot background, axes and cursors, called on theme change
    def apply_theme(self, theme) -> None:
        self.theme = theme
        if theme is None:
            return
        colors = derived_colors(theme)
        self.plot.apply_colors(colors["surface"], colors["muted"], accent=colors["accent"])
        self._cursor_colors = {"A": colors["muted"], "B": colors["accent"]}
        self._refresh_readout()

    # -- adding and removing signals --

    # labels turn plotted codes back into text for enum signals
    def add_signal(self, name: str, timestamps: np.ndarray, values: np.ndarray,
                   unit: str = "", labels: Optional[list[str]] = None) -> None:
        if name in self._series_cache:
            return  # already plotted
        color = next_palette_color(self.theme, len(self._series_cache))
        self._series_cache[name] = (timestamps, values)
        self._colors[name] = color
        self._visible[name] = True
        self._units[name] = unit
        self._labels[name] = labels
        self.plot.add_trace(name, timestamps, values, color)
        self._add_table_row(name, color)
        self.snap_signal.addItem(name)
        self.snap_signal.setCurrentIndex(self.snap_signal.count() - 1)  # newest by default
        self._refresh_empty_hint()
        self._on_cursor_changed()

    # fully unplots, drops the trace, its row and its cached data
    def remove_signal(self, name: str) -> None:
        for store in (self._series_cache, self._colors, self._visible, self._units, self._labels):
            store.pop(name, None)
        self.plot.remove_trace(name)
        row = self._find_row(name)
        if row is not None:
            self.signal_table.removeRow(row)
        idx = self.snap_signal.findText(name)
        if idx >= 0:
            self.snap_signal.removeItem(idx)
        self._refresh_empty_hint()
        self._refresh_markers()

    def clear(self) -> None:
        for name in list(self._series_cache):
            self.remove_signal(name)

    def set_signal_visible(self, name: str, visible: bool) -> None:
        self._visible[name] = visible
        self.plot.set_trace_visible(name, visible)
        self._refresh_toggle_button_text(name)
        self._refresh_markers()

    def plotted_names(self) -> list[str]:
        return list(self._series_cache)

    # -- cursors --

    # (a, b) while both cursors are shown, else None
    def cursor_range(self) -> Optional[tuple[float, float]]:
        a, b = self.plot.cursor_pos("A"), self.plot.cursor_pos("B")
        return None if a is None or b is None else (a, b)

    def _on_cursor_button(self, key: str, on: bool) -> None:
        if on:
            self.plot.set_cursor(key)
        else:
            self.plot.hide_cursor(key)

    # keeps the toggle buttons and cursor columns in step when a click places a cursor
    def _on_cursor_toggled(self, key: str, shown: bool) -> None:
        btn = self.cursor_buttons[key]
        btn.blockSignals(True)
        btn.setChecked(shown)
        btn.blockSignals(False)
        self._refresh_cursor_columns()
        self._on_cursor_changed()

    def _on_cursor_changed(self) -> None:
        self._refresh_readout()
        self._refresh_cursor_cells()
        self._refresh_markers()
        self.cursors_changed.emit()

    def _refresh_cursor_columns(self) -> None:
        a_on, b_on = self.plot.cursor_visible("A"), self.plot.cursor_visible("B")
        self.signal_table.setColumnHidden(self.COL_A, not a_on)
        self.signal_table.setColumnHidden(self.COL_B, not b_on)
        self.signal_table.setColumnHidden(self.COL_DELTA, not (a_on and b_on))

    # "A 12.345 s   B 14.000 s   Δt 1.655 s", in each cursor's color
    def _refresh_readout(self) -> None:
        if not hasattr(self, "cursor_readout"):
            return
        colors = getattr(self, "_cursor_colors", {})
        parts = []
        for key in PlotEngine.CURSOR_KEYS:
            x = self.plot.cursor_pos(key)
            if x is not None:
                color = colors.get(key, "")
                parts.append(f"<span style='color:{color}'><b>{key}</b></span> {x:.3f} s")
        rng = self.cursor_range()
        if rng is not None:
            parts.append(f"<b>Δt</b> {abs(rng[1] - rng[0]):.3f} s")
        self.cursor_readout.setText(
            "&nbsp;&nbsp;&nbsp;".join(parts) if parts
            else "Click the plot to place cursor A, Shift+click for B"
        )

    # the value each trace holds at each cursor, values hold until the next frame
    def _refresh_cursor_cells(self) -> None:
        positions = {key: self.plot.cursor_pos(key) for key in PlotEngine.CURSOR_KEYS}
        for row in range(self.signal_table.rowCount()):
            name = self.signal_table.item(row, self.COL_NAME).data(Qt.UserRole)
            held = {key: self._held_value(name, x) for key, x in positions.items()}
            self.signal_table.item(row, self.COL_A).setText(self._format(name, held["A"]))
            self.signal_table.item(row, self.COL_B).setText(self._format(name, held["B"]))
            delta = "—"
            if held["A"] is not None and held["B"] is not None:
                if self._labels.get(name):
                    delta = "same" if held["A"] == held["B"] else "changed"
                else:
                    delta = format_number(held["B"] - held["A"], self._units.get(name, ""))
            self.signal_table.item(row, self.COL_DELTA).setText(delta)

    # the plotted value at x, None before the first sample or while the cursor is hidden
    def _held_value(self, name: str, x: Optional[float]) -> Optional[float]:
        if x is None or name not in self._series_cache:
            return None
        timestamps, values = self._series_cache[name]
        idx = sample_index_at(timestamps, x)
        return None if idx < 0 else float(values[idx])

    def _format(self, name: str, value: Optional[float]) -> str:
        if value is None:
            return "—"
        labels = self._labels.get(name)
        if labels and not np.isnan(value) and 0 <= int(value) < len(labels):
            return labels[int(value)]
        return format_number(value, self._units.get(name, ""))

    # a dot where each shown trace crosses each shown cursor
    def _refresh_markers(self) -> None:
        for key in PlotEngine.CURSOR_KEYS:
            x = self.plot.cursor_pos(key)
            points = []
            if x is not None:
                for name, shown in self._visible.items():
                    y = self._held_value(name, x) if shown else None
                    if y is not None and np.isfinite(y):
                        points.append((x, y))
            self.plot.set_cursor_markers(key, points)

    def _on_snap(self) -> None:
        name = self.snap_signal.currentText()
        if name not in self._series_cache:
            return
        timestamps, values = self._series_cache[name]
        key = PlotEngine.CURSOR_KEYS[self.snap_cursor.currentIndex()]
        mode = "max" if self.snap_mode.currentText() == "Max" else "min"
        visible_only = self.snap_scope.currentText() == "Visible window"
        self.plot.snap_cursor_to_peak(timestamps, values, mode=mode,
                                      visible_only=visible_only, cursor=key)

    def _on_row_selected(self, row: int) -> None:
        item = self.signal_table.item(row, self.COL_NAME) if row >= 0 else None
        if item is not None:
            self.snap_signal.setCurrentText(item.data(Qt.UserRole))

    # -- dropping signals onto the plot --

    def eventFilter(self, obj, event) -> bool:
        if obj is self.plot.viewport() and event.type() in (
            QEvent.DragEnter, QEvent.DragMove, QEvent.Drop
        ):
            names = signal_names_from_mime(event.mimeData())
            if not names:
                return False
            event.setDropAction(Qt.CopyAction)
            event.accept()
            if event.type() == QEvent.Drop:
                self.signals_dropped.emit(names)
            return True
        return super().eventFilter(obj, event)

    # -- plotted signals table --

    # shows a hint instead of an empty table
    def _refresh_empty_hint(self) -> None:
        empty = self.signal_table.rowCount() == 0
        self.empty_hint.setVisible(empty)
        self.signal_table.setVisible(not empty)
        self.clear_btn.setEnabled(not empty)
        self.snap_btn.setEnabled(not empty)

    # name in its trace color, values at the cursors, then hide/show and remove buttons
    def _add_table_row(self, name: str, color: str) -> None:
        row = self.signal_table.rowCount()
        self.signal_table.insertRow(row)

        unit = self._units.get(name)
        name_item = QTableWidgetItem(f"{name}  ({unit})" if unit else name)
        name_item.setData(Qt.UserRole, name)
        name_item.setForeground(QColor(color))
        font = name_item.font()
        font.setBold(True)
        name_item.setFont(font)
        self.signal_table.setItem(row, self.COL_NAME, name_item)
        for col in (self.COL_A, self.COL_B, self.COL_DELTA):
            self.signal_table.setItem(row, col, QTableWidgetItem("—"))

        toggle_btn = button("Hide", variant="subtle", icon_name="hide",
                            tooltip="Hide this trace from the plot (it stays in this list)")
        toggle_btn.clicked.connect(lambda: self.set_signal_visible(name, not self._visible.get(name, True)))
        self.signal_table.setCellWidget(row, self.COL_TOGGLE, toggle_btn)

        remove_btn = button("Remove", variant="subtle", icon_name="delete",
                            tooltip="Remove this trace from the plot entirely")
        remove_btn.clicked.connect(lambda: self.remove_signal(name))
        self.signal_table.setCellWidget(row, self.COL_REMOVE, remove_btn)

    # flips the button label and fades the name while hidden
    def _refresh_toggle_button_text(self, name: str) -> None:
        row = self._find_row(name)
        if row is None:
            return
        btn = self.signal_table.cellWidget(row, self.COL_TOGGLE)
        if btn is not None:
            visible = self._visible.get(name, True)
            btn.setText("Hide" if visible else "Show")
            btn.setIcon(icon("hide" if visible else "view"))
            item = self.signal_table.item(row, self.COL_NAME)
            color = QColor(self._colors.get(name, "#888888"))
            if not visible:
                color.setAlphaF(0.4)
            item.setForeground(color)

    def _find_row(self, name: str):
        for row in range(self.signal_table.rowCount()):
            item = self.signal_table.item(row, self.COL_NAME)
            if item is not None and item.data(Qt.UserRole) == name:
                return row
        return None
