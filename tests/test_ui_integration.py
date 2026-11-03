#--------------------#
# test_ui_integration.py
# end to end ui tests against the real sample log
#--------------------#
from pathlib import Path

import pytest

from core.config_loader import PlatformConfig
from core.dbc_handler import DbcHandler
from core.log_parser import LogParser

FIXTURE_DBC = Path(__file__).parent / "fixtures" / "sample.dbc"
SAMPLE_LOG = Path(__file__).parent / "fixtures" / "sample_log.mf4"

requires_sample_log = pytest.mark.skipif(
    not SAMPLE_LOG.exists(), reason="Real sample .mf4 log not present in tests/fixtures/"
)

# reuse one qt application across test modules
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.session_view import SessionWidget  # noqa: E402

_qt_app = QApplication.instance() or QApplication([])


# force decode button to plot_requested to SessionWidget to TraceView, with real widgets
@requires_sample_log
def test_force_decode_button_flow_plots_a_real_signal(tmp_path, monkeypatch):
    import PySide6.QtWidgets as qtw
    # the summary popup is modal and would block the test
    monkeypatch.setattr(qtw.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(qtw.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(qtw.QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    dbc_handler = DbcHandler(FIXTURE_DBC)
    log_parser = LogParser(SAMPLE_LOG, dbc_handler)
    log_parser.load()

    platform = PlatformConfig(name="Test", dbc_path="sample.dbc", important_values=[])
    widget = SessionWidget(
        log_path=SAMPLE_LOG,
        dbc_handler=dbc_handler,
        log_parser=log_parser,
        platform=platform,
        platform_path=tmp_path / "test.yaml",
        theme=_load_default_theme(),
        help_dir=tmp_path / "help",
    )
    browser = widget.advanced_panel
    real_id_item = [
        browser.not_decoded_list.item(i) for i in range(browser.not_decoded_list.count())
        if browser.not_decoded_list.item(i).text() == "0x380"
    ]
    assert real_id_item, "0x380 should be in this log's Not Decoded list"
    browser.not_decoded_list.setCurrentItem(real_id_item[0])
    browser.force_message_input.setText("EngineData")
    requested_views = []
    widget.view_requested.connect(requested_views.append)
    browser._on_force_decode()

    assert browser.force_decoded_list.count() == 2  # both engine signals
    # the new signals reach the other pages of the session
    forced = browser.force_decoded_list.item(0).text()
    assert forced in widget.all_list.names()
    columns = widget.table_view.column_list
    assert forced in [columns.item(i).text() for i in range(columns.count())]
    browser.force_decoded_list.setCurrentRow(0)
    browser._on_plot_clicked()  # emits plot_requested -> SessionWidget -> TraceView

    assert len(widget.trace_view._series_cache) == 1
    assert requested_views == ["graph"]  # plotting from the advanced page shows the graph

    log_parser.close()


# regression, enum signals used to do nothing when clicked, now they plot as codes
@requires_sample_log
def test_categorical_signal_plots_as_coded_values_instead_of_silently_failing(tmp_path, monkeypatch):
    import PySide6.QtWidgets as qtw
    monkeypatch.setattr(qtw.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    value_table_dbc = Path(__file__).parent / "fixtures" / "value_table.dbc"
    dbc_handler = DbcHandler(value_table_dbc)
    log_parser = LogParser(SAMPLE_LOG, dbc_handler)
    log_parser.load()

    platform = PlatformConfig(
        name="Test", dbc_path="value_table.dbc", important_values=["StateEnum", "RawValue"]
    )
    widget = SessionWidget(
        log_path=SAMPLE_LOG,
        dbc_handler=dbc_handler,
        log_parser=log_parser,
        platform=platform,
        platform_path=tmp_path / "test.yaml",
        theme=_load_default_theme(),
        help_dir=tmp_path / "help",
    )

    assert widget.values_list.names() == ["StateEnum", "RawValue"]
    widget._show_signal("StateEnum")

    assert len(widget.trace_view._series_cache) == 1
    labels = widget.trace_view._labels["StateEnum"]
    assert labels and all(isinstance(lbl, str) for lbl in labels)  # decoded text, not codes

    log_parser.close()


def _load_default_theme():
    from core.config_loader import load_theme_config
    app_root = Path(__file__).resolve().parents[1]
    return load_theme_config(app_root / "config" / "defaults" / "dark_theme.yaml")
