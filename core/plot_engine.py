#--------------------#
# plot_engine.py
# interactive pyqtgraph plot plus the static snapshot used for pdf reports
#--------------------#
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from PySide6.QtCore import QRectF, Qt, Signal


class PlotEngine(pg.PlotWidget):
    # cursor key ("A" or "B") and its new x position, fired while dragging and on snap or click
    cursor_moved = Signal(str, float)
    # cursor key and whether it is now shown
    cursor_toggled = Signal(str, bool)

    CURSOR_KEYS = ("A", "B")

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setLabel("bottom", "Time (s)")
        self._traces: dict[str, pg.PlotDataItem] = {}
        # two vertical cursors, hidden until placed, each with a marker per trace where it crosses
        self._cursors: dict[str, pg.InfiniteLine] = {}
        self._markers: dict[str, pg.ScatterPlotItem] = {}
        for key in self.CURSOR_KEYS:
            line = pg.InfiniteLine(angle=90, movable=True, label=key,
                                   labelOpts={"position": 0.96, "movable": False})
            line.sigPositionChanged.connect(lambda ln, k=key: self._on_cursor_dragged(k))
            line.setZValue(10)
            line.hide()
            self.addItem(line, ignoreBounds=True)
            self._cursors[key] = line
            markers = pg.ScatterPlotItem(size=7, pxMode=True)
            markers.setZValue(11)
            self.addItem(markers, ignoreBounds=True)
            self._markers[key] = markers
        # click places cursor A, shift+click places cursor B
        self.scene().sigMouseClicked.connect(self._on_scene_clicked)

    # matches the plot to the app theme instead of pyqtgraph's black default
    # cursor A is drawn in the text color, cursor B in the accent color
    def apply_colors(self, background: str, foreground: str, grid_alpha: float = 0.25,
                     accent: Optional[str] = None) -> None:
        self.setBackground(background)
        axis_pen = pg.mkPen(color=foreground, width=1)
        for name in ("left", "bottom"):
            axis = self.getAxis(name)
            axis.setPen(axis_pen)
            axis.setTextPen(axis_pen)
        self.showGrid(x=True, y=True, alpha=grid_alpha)
        for key, color in (("A", foreground), ("B", accent or foreground)):
            line = self._cursors[key]
            line.setPen(pg.mkPen(color=color, width=1.5, style=Qt.DashLine))
            line.setHoverPen(pg.mkPen(color=color, width=3))
            line.label.setColor(color)
            line.label.fill = pg.mkBrush(background)
            self._markers[key].setPen(pg.mkPen(color=background, width=1))
            self._markers[key].setBrush(pg.mkBrush(color))

    # -- traces --

    def add_trace(self, name: str, timestamps: np.ndarray, values: np.ndarray,
                  color: str, width: float = 1.5) -> None:
        pen = pg.mkPen(color=color, width=width)
        curve = self.plot(timestamps, values, pen=pen, name=name)
        # downsample long logs instead of drawing every raw point
        curve.setDownsampling(auto=True, method="peak")
        curve.setClipToView(True)
        self._traces[name] = curve

    def remove_trace(self, name: str) -> None:
        curve = self._traces.pop(name, None)
        if curve is not None:
            self.removeItem(curve)

    def set_trace_visible(self, name: str, visible: bool) -> None:
        if name in self._traces:
            self._traces[name].setVisible(visible)

    # -- cursors --

    def cursor_visible(self, key: str) -> bool:
        return self._cursors[key].isVisible()

    # x position of a shown cursor, None while it is hidden
    def cursor_pos(self, key: str) -> Optional[float]:
        line = self._cursors[key]
        return float(line.value()) if line.isVisible() else None

    # shows the cursor at x, or in the visible window if x is None and it has never been placed
    def set_cursor(self, key: str, x: Optional[float] = None) -> None:
        line = self._cursors[key]
        was_visible = line.isVisible()
        if x is None:
            if was_visible:
                return
            (x_min, x_max), _ = self.viewRange()
            x = x_min + (x_max - x_min) * (0.35 if key == "A" else 0.65)
        line.show()
        if not was_visible:
            self.cursor_toggled.emit(key, True)
        if x != line.value():
            line.setValue(x)  # fires sigPositionChanged, which emits cursor_moved
        else:
            self.cursor_moved.emit(key, float(x))

    def hide_cursor(self, key: str) -> None:
        if self._cursors[key].isVisible():
            self._cursors[key].hide()
            self._markers[key].clear()
            self.cursor_toggled.emit(key, False)

    # dots where the cursor crosses each shown trace, (x, y) pairs from the caller
    def set_cursor_markers(self, key: str, points: list[tuple[float, float]]) -> None:
        if not points or not self._cursors[key].isVisible():
            self._markers[key].clear()
            return
        xs, ys = zip(*points)
        self._markers[key].setData(x=list(xs), y=list(ys))

    # moves a cursor to the max or min, over the whole log or only the visible window
    def snap_cursor_to_peak(self, timestamps: np.ndarray, values: np.ndarray,
                             mode: str = "max", visible_only: bool = False,
                             cursor: str = "A") -> Optional[float]:
        if visible_only:
            (x_min, x_max), _ = self.viewRange()
            mask = (timestamps >= x_min) & (timestamps <= x_max)
            if not mask.any():
                return None
            ts_slice, val_slice = timestamps[mask], values[mask]
        else:
            ts_slice, val_slice = timestamps, values
        if not len(val_slice) or np.isnan(val_slice).all():
            return None

        idx = int(np.nanargmax(val_slice)) if mode == "max" else int(np.nanargmin(val_slice))
        peak_t = float(ts_slice[idx])
        self.set_cursor(cursor, peak_t)
        return peak_t

    def _on_cursor_dragged(self, key: str) -> None:
        line = self._cursors[key]
        if line.isVisible():
            self.cursor_moved.emit(key, float(line.value()))

    # left clicks inside the plot area only, drags (pan and zoom) never arrive here
    def _on_scene_clicked(self, ev) -> None:
        if ev.button() != Qt.LeftButton or ev.double():
            return
        view_box = self.getPlotItem().getViewBox()
        if not view_box.sceneBoundingRect().contains(ev.scenePos()):
            return
        x = float(view_box.mapSceneToView(ev.scenePos()).x())
        self.set_cursor("B" if ev.modifiers() & Qt.ShiftModifier else "A", x)


# -- pdf snapshot --

# 1200x600 png on white for the pdf report, separate from the live plot (needs a qt app)
# laid out at 600x300 and exported at 2x so text and lines stay readable in the pdf
def render_static_snapshot(name: str, timestamps: np.ndarray, values: np.ndarray,
                            out_path: Path) -> Path:
    widget = pg.PlotWidget(background="w")
    item = widget.getPlotItem()
    item.setTitle(name, color="#222222")
    item.setLabel("bottom", "Time (s)", color="#222222")
    for axis_name in ("left", "bottom"):
        axis = item.getAxis(axis_name)
        axis.setPen("#444444")
        axis.setTextPen("#222222")
    curve = item.plot(timestamps, values, pen=pg.mkPen("#1f77b4", width=1))
    curve.setDownsampling(auto=True, method="peak")
    item.setGeometry(QRectF(0, 0, 600, 300))  # the widget is never shown, so size the plot directly
    exporter = ImageExporter(item)
    exporter.parameters()["width"] = 1200
    exporter.export(str(out_path))
    widget.deleteLater()
    return out_path
