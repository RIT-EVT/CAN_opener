#--------------------#
# test_session_pages.py
# tests for the session pages: important signals drag and drop, data analysis and the table view
# uses stand-in log data so it runs without the sample log
#--------------------#
from pathlib import Path

import numpy as np
import pytest

from core.config_loader import PlatformConfig, load_platform_config, load_theme_config
from core.log_parser import SignalSeries, SignalSummary

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.session_view import SessionWidget  # noqa: E402
from ui.tabular_view import write_csv  # noqa: E402

_qt_app = QApplication.instance() or QApplication([])
APP_ROOT = Path(__file__).resolve().parents[1]


class _FakeParser:
    def __init__(self):
        t = np.array([0.0, 1.0, 2.0, 3.0])
        self.decoded = {
            "Speed": SignalSeries("Speed", t, np.array([0.0, 10.0, 30.0, 20.0]), "km/h"),
            "Rpm": SignalSeries("Rpm", t + 0.5, np.array([800.0, 900.0, 3000.0, 1200.0]), "rpm"),
            "Gear": SignalSeries("Gear", t, np.array([b"P", b"D", b"D", b"N"])),
        }
        self.summaries = {
            n: SignalSummary(n, float(s.values.max()), float(s.values.min()), float(s.values.mean()))
            for n, s in self.decoded.items() if s.values.dtype.kind == "f"
        }
        self.not_decoded_ids = set()

    def close(self):
        pass


class _FakeDbc:
    def messages(self):
        return []


def _session(tmp_path, important=()):
    platform = PlatformConfig(name="Test", dbc_path="x.dbc", important_values=list(important))
    theme = load_theme_config(APP_ROOT / "config" / "defaults" / "dark_theme.yaml")
    return SessionWidget(Path("log.mf4"), _FakeDbc(), _FakeParser(), platform,
                         tmp_path / "test.yaml", theme, tmp_path / "help")


# -- important signals --

def test_dragging_from_all_signals_adds_at_the_drop_row_and_saves(tmp_path):
    widget = _session(tmp_path, ["Speed"])
    widget.values_list.names_dropped.emit(["Rpm"], 0, widget.all_list)
    assert widget.values_list.names() == ["Rpm", "Speed"]
    assert load_platform_config(tmp_path / "test.yaml").important_values == ["Rpm", "Speed"]


def test_dragging_within_important_reorders(tmp_path):
    widget = _session(tmp_path, ["Speed", "Rpm", "Gear"])
    widget.values_list.names_dropped.emit(["Speed"], 3, widget.values_list)  # to the end
    assert widget.values_list.names() == ["Rpm", "Gear", "Speed"]
    widget.values_list.names_dropped.emit(["Gear"], 0, widget.values_list)  # to the top
    assert widget.values_list.names() == ["Gear", "Rpm", "Speed"]


def test_dragging_back_to_all_signals_removes_it(tmp_path):
    widget = _session(tmp_path, ["Speed", "Rpm"])
    widget.all_list.names_dropped.emit(["Speed"], 0, widget.values_list)
    assert widget.values_list.names() == ["Rpm"]


# a real drop event, the all signals list only takes drops from the important list
def test_signal_list_drop_event_reads_names_and_respects_sources(tmp_path):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QDropEvent

    from ui.widgets import signal_names_mime

    widget = _session(tmp_path)

    mime = signal_names_mime(["Rpm", "Gear"])  # the event doesn't own it, so keep a reference

    def drop(target):
        event = QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        target.dropEvent(event)
        return event.isAccepted()

    assert drop(widget.values_list)
    assert widget.values_list.names() == ["Rpm", "Gear"]
    assert not drop(widget.all_list)  # a synthetic drop has no source widget
    assert widget.values_list.names() == ["Rpm", "Gear"]


# a signal this log lacks stays in the platform list, so other logs still see it
def test_important_signals_missing_from_the_log_are_kept(tmp_path):
    widget = _session(tmp_path, ["NotInThisLog", "Speed"])
    assert widget.values_list.names() == ["NotInThisLog", "Speed"]
    widget.values_list.names_dropped.emit(["Rpm"], 2, widget.all_list)
    assert widget.important_names() == ["NotInThisLog", "Speed", "Rpm"]


def test_all_signals_filter_and_click_to_plot(tmp_path):
    widget = _session(tmp_path)
    assert widget.all_list.names() == ["Gear", "Rpm", "Speed"]
    widget.values_filter.setText("sp")
    shown = [widget.all_list.item(i).text() for i in range(widget.all_list.count())
             if not widget.all_list.item(i).isHidden()]
    assert shown == ["Speed"]
    widget.trace_view.signals_dropped.emit(["Speed", "Gear"])  # dropped on the plot
    assert widget.trace_view.plotted_names() == ["Speed", "Gear"]


# -- data analysis --

def test_data_view_uses_the_cursor_range_when_asked(tmp_path):
    widget = _session(tmp_path, ["Speed"])
    view = widget.data_view
    view.refresh()
    assert view._stats["Speed"].maximum == 30.0
    assert view._stats["Gear"].distinct == 3

    view.show_combo.setCurrentText("Important signals")
    assert list(view._stats) == ["Speed"]

    widget.trace_view.plot.set_cursor("A", 2.5)
    widget.trace_view.plot.set_cursor("B", 3.0)
    view.range_combo.setCurrentText("Between cursors A and B")
    assert view._stats["Speed"].samples == 1 and view._stats["Speed"].maximum == 20.0
    assert "2.500" in view.range_note.text()


def test_data_view_plot_request_shows_the_graph(tmp_path):
    widget = _session(tmp_path)
    views = []
    widget.view_requested.connect(views.append)
    widget.data_view.plot_requested.emit("Rpm")
    assert widget.trace_view.plotted_names() == ["Rpm"] and views == ["graph"]


# -- table view --

def test_table_rows_hold_values_on_a_shared_time_axis(tmp_path):
    widget = _session(tmp_path)
    table = widget.table_view
    table.set_columns(["Speed", "Rpm"])
    model = table.model
    # every sample: union of 0,1,2,3 and 0.5,1.5,2.5,3.5
    assert model.rowCount() == 8 and model.columnCount() == 3
    # columns follow the checklist, which is alphabetical
    assert model.headerData(1, Qt.Horizontal) == "Rpm (rpm)"
    assert model.headerData(2, Qt.Horizontal) == "Speed (km/h)"
    rpm_col = [model.data(model.index(r, 1)) for r in range(model.rowCount())]
    speed_col = [model.data(model.index(r, 2)) for r in range(model.rowCount())]
    assert speed_col[:3] == ["0", "0", "10"]  # held from t=0 at t=0.5
    assert rpm_col[0] == ""  # Rpm's first frame is at 0.5

    table.step_combo.setCurrentIndex(3)  # every 1 s
    assert [model.data(model.index(r, 0)) for r in range(model.rowCount())] == \
        ["0.0000", "1.0000", "2.0000", "3.0000"]

    widget.trace_view.plot.set_cursor("A", 2.2)
    table.go_to_cursor("A")
    assert table.table.currentIndex().row() == 2


def test_table_starts_with_plotted_signals_and_exports_csv(tmp_path):
    widget = _session(tmp_path, ["Rpm"])
    widget._show_signal("Gear")
    widget.show_view("table")
    widget.show()  # the first show picks the plotted signals over the important ones
    assert widget.table_view.checked_names() == ["Gear"]
    widget.hide()

    out = tmp_path / "out.csv"
    write_csv(out, widget.table_view.model.times, widget.table_view.model.columns)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "time_s,Gear"
    assert lines[1] == "0.000000,P"
