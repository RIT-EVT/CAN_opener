#--------------------#
# test_trace_view.py
# tests for the plotted signals table (hide, show, remove) and the plot cursors
#--------------------#
from pathlib import Path

import numpy as np
import pytest

from core.config_loader import load_theme_config

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.trace_view import TraceView  # noqa: E402

_qt_app = QApplication.instance() or QApplication([])

APP_ROOT = Path(__file__).resolve().parents[1]


def _make_trace_view() -> TraceView:
    theme = load_theme_config(APP_ROOT / "config" / "defaults" / "dark_theme.yaml")
    return TraceView(theme)


def test_add_signal_creates_a_visible_row_with_hide_button():
    view = _make_trace_view()
    t = np.linspace(0, 10, 50)
    view.add_signal("RPM", t, np.sin(t))

    assert view.signal_table.rowCount() == 1
    assert view.signal_table.item(0, 0).text() == "RPM"
    toggle_btn = view.signal_table.cellWidget(0, view.COL_TOGGLE)
    remove_btn = view.signal_table.cellWidget(0, view.COL_REMOVE)
    assert toggle_btn.text() == "Hide"  # visible by default, so it offers hide
    assert "Remove" in remove_btn.text()


def test_toggle_button_hides_and_shows_without_removing_the_trace():
    view = _make_trace_view()
    t = np.linspace(0, 10, 50)
    view.add_signal("RPM", t, np.sin(t))

    toggle_btn = view.signal_table.cellWidget(0, view.COL_TOGGLE)
    toggle_btn.click()
    assert view._visible["RPM"] is False
    assert toggle_btn.text() == "Show"
    assert "RPM" in view.plot._traces  # still plotted, just hidden
    assert view.plot._traces["RPM"].isVisible() is False

    toggle_btn.click()
    assert view._visible["RPM"] is True
    assert toggle_btn.text() == "Hide"
    assert view.plot._traces["RPM"].isVisible() is True


# remove drops the trace, the row and the cached data
def test_remove_button_actually_unplots_the_signal():
    view = _make_trace_view()
    t = np.linspace(0, 10, 50)
    view.add_signal("RPM", t, np.sin(t))
    view.add_signal("Temp", t, np.cos(t))
    assert view.signal_table.rowCount() == 2

    remove_btn = view.signal_table.cellWidget(0, view.COL_REMOVE)
    remove_btn.click()

    assert view.signal_table.rowCount() == 1
    assert "RPM" not in view.plot._traces
    assert "RPM" not in view._series_cache
    assert "RPM" not in view._visible
    assert view.signal_table.item(0, 0).text() == "Temp"  # the other signal is untouched


def test_readding_a_removed_signal_works():
    view = _make_trace_view()
    t = np.linspace(0, 10, 50)
    view.add_signal("RPM", t, np.sin(t))
    view.remove_signal("RPM")
    view.add_signal("RPM", t, np.sin(t))

    assert view.signal_table.rowCount() == 1
    assert "RPM" in view.plot._traces


# -- cursors --

def test_cursor_values_follow_the_held_sample_and_show_delta():
    view = _make_trace_view()
    t = np.array([0.0, 1.0, 2.0, 3.0])
    view.add_signal("Speed", t, np.array([10.0, 20.0, 30.0, 40.0]), unit="km/h")

    assert view.signal_table.isColumnHidden(view.COL_A)  # no cursors yet
    view.plot.set_cursor("A", 1.5)  # between samples, holds the value from t=1
    view.plot.set_cursor("B", 3.0)

    assert view.cursor_buttons["A"].isChecked() and view.cursor_buttons["B"].isChecked()
    assert not view.signal_table.isColumnHidden(view.COL_DELTA)
    assert view.signal_table.item(0, view.COL_A).text() == "20 km/h"
    assert view.signal_table.item(0, view.COL_B).text() == "40 km/h"
    assert view.signal_table.item(0, view.COL_DELTA).text() == "20 km/h"
    assert "1.500" in view.cursor_readout.text() and "Δt" in view.cursor_readout.text()
    assert view.cursor_range() == (1.5, 3.0)

    view.cursor_buttons["B"].click()  # hide B again
    assert view.cursor_range() is None
    assert view.signal_table.isColumnHidden(view.COL_B)


def test_cursor_before_first_sample_shows_a_dash():
    view = _make_trace_view()
    view.add_signal("Late", np.array([5.0, 6.0]), np.array([1.0, 2.0]))
    view.plot.set_cursor("A", 1.0)
    assert view.signal_table.item(0, view.COL_A).text() == "—"


# the snap target is picked explicitly, not just the newest trace
def test_snap_moves_the_chosen_cursor_to_the_chosen_signal():
    view = _make_trace_view()
    t = np.linspace(0, 10, 101)
    view.add_signal("PeakAt2", t, -(t - 2) ** 2)
    view.add_signal("PeakAt8", t, -(t - 8) ** 2)

    view.snap_signal.setCurrentText("PeakAt2")
    view.snap_cursor.setCurrentIndex(1)  # cursor B
    view._on_snap()
    assert view.plot.cursor_pos("B") == 2.0
    assert view.plot.cursor_pos("A") is None

    view.signal_table.setCurrentCell(1, view.COL_NAME)  # selecting a row picks it as the target
    assert view.snap_signal.currentText() == "PeakAt8"


def test_enum_codes_show_their_labels_at_the_cursor():
    view = _make_trace_view()
    view.add_signal("Gear", np.array([0.0, 1.0]), np.array([0.0, 1.0]), labels=["P", "D"])
    view.plot.set_cursor("A", 0.5)
    view.plot.set_cursor("B", 1.0)
    assert view.signal_table.item(0, view.COL_A).text() == "P"
    assert view.signal_table.item(0, view.COL_B).text() == "D"
    assert view.signal_table.item(0, view.COL_DELTA).text() == "changed"


def test_dropping_signal_names_on_the_plot_asks_to_plot_them():
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QDropEvent

    from ui.widgets import signal_names_mime

    view = _make_trace_view()
    received = []
    view.signals_dropped.connect(received.append)
    mime = signal_names_mime(["RPM", "Temp"])
    event = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    view.eventFilter(view.plot.viewport(), event)
    assert received == [["RPM", "Temp"]]
