#--------------------#
# test_main_window.py
# tests for the main window: menus, nav rail, settings unlock, themes and a real session
#--------------------#
from pathlib import Path
import shutil

import pytest

from core.config_loader import (
    DEFAULT_DEV_PASSWORD, discover_platforms, ensure_default_settings, load_app_settings,
)
from core.theme_loader import bootstrap_user_themes, load_active_theme
from utils.file_utils import ensure_directories

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMenu, QToolBar, QToolButton  # noqa: E402

from ui.main_window import (  # noqa: E402
    ANALYSIS_PAGES, PAGE_ADVANCED, PAGE_DATA, PAGE_GRAPH, PAGE_HELP, PAGE_SETTINGS, PAGE_TABLE,
    MainWindow,
)

_qt_app = QApplication.instance() or QApplication([])
_REAL_APP_ROOT = Path(__file__).resolve().parents[1]


def _make_window(tmp_path: Path) -> MainWindow:
    ensure_directories(tmp_path)
    shutil.copytree(
        _REAL_APP_ROOT / "config" / "defaults", tmp_path / "config" / "defaults",
        dirs_exist_ok=True,
    )
    settings_path = tmp_path / "config" / "settings.yaml"
    ensure_default_settings(settings_path)
    settings = load_app_settings(settings_path)
    bootstrap_user_themes(tmp_path / "config" / "themes", tmp_path / "config" / "defaults")
    theme = load_active_theme(tmp_path, settings)
    return MainWindow(tmp_path, _qt_app, settings, theme)


def _menu(window: MainWindow, title: str) -> QMenu:
    return next(m for m in window.menuBar().findChildren(QMenu) if m.title() == title)


def _page_buttons_for(window: MainWindow, action) -> list[QToolButton]:
    return [b for b in window.findChildren(QToolButton) if b.defaultAction() is action]


def test_menu_bar_has_standard_file_view_help_menus(tmp_path):
    window = _make_window(tmp_path)
    titles = [a.text() for a in window.menuBar().actions()]
    assert titles == ["&File", "&View", "&Help"]


# one shared action per command, used by the file menu and the page header
def test_open_and_export_actions_are_shared_not_duplicated(tmp_path):
    window = _make_window(tmp_path)
    file_menu = _menu(window, "&File")

    assert window.open_action in file_menu.actions()
    assert window.export_action in file_menu.actions()
    assert _page_buttons_for(window, window.open_action)
    assert _page_buttons_for(window, window.export_action)


def test_export_disabled_until_a_session_is_open(tmp_path):
    window = _make_window(tmp_path)
    assert not window.export_action.isEnabled()
    assert not window.close_session_action.isEnabled()


def test_advanced_mode_action_is_shared_with_settings_toggle(tmp_path):
    window = _make_window(tmp_path)
    assert window.advanced_action.isCheckable()
    assert window.advanced_action in _menu(window, "&View").actions()

    window.advanced_action.setChecked(True)
    assert window.advanced_mode is True
    assert window.settings_page.advanced_checkbox.isChecked()
    assert window.nav.button(PAGE_ADVANCED).isVisibleTo(window.nav)

    window.settings_page.advanced_checkbox.setChecked(False)
    assert window.advanced_action.isChecked() is False
    assert window.advanced_mode is False


def test_no_toolbar_or_stray_advanced_checkbox(tmp_path):
    window = _make_window(tmp_path)
    assert not window.findChildren(QToolBar)
    assert not hasattr(window, "advanced_toggle")


def test_nav_rail_switches_pages(tmp_path):
    window = _make_window(tmp_path)
    assert window.current_page() == PAGE_GRAPH
    window.nav.button(PAGE_SETTINGS).click()
    assert window.current_page() == PAGE_SETTINGS
    assert window.pages.currentWidget() is window.settings_page
    window.page_actions[PAGE_HELP].trigger()
    assert window.pages.currentWidget() is window.help_page
    window.page_actions[PAGE_DATA].trigger()
    assert window.current_page() == PAGE_DATA
    assert window.analysis_header.title.text() == "Data analysis"


# analysis pages on top in order, help then settings pinned at the bottom
def test_nav_rail_order_and_advanced_page_needs_advanced_mode(tmp_path):
    window = _make_window(tmp_path)
    top = [window.nav._top.itemAt(i).widget() for i in range(window.nav._top.count())]
    bottom = [window.nav._bottom.itemAt(i).widget() for i in range(window.nav._bottom.count())]
    assert top == [window.nav.button(k) for k in ANALYSIS_PAGES]
    assert bottom == [window.nav.button(PAGE_HELP), window.nav.button(PAGE_SETTINGS)]

    assert not window.nav.button(PAGE_ADVANCED).isVisibleTo(window.nav)
    window.show_page(PAGE_ADVANCED)
    assert window.current_page() == PAGE_GRAPH  # falls back while advanced mode is off

    window.advanced_action.setChecked(True)
    window.show_page(PAGE_ADVANCED)
    assert window.current_page() == PAGE_ADVANCED
    window.advanced_action.setChecked(False)
    assert window.current_page() == PAGE_GRAPH


def test_nav_rail_collapses_to_icons(tmp_path):
    window = _make_window(tmp_path)
    window.toggle_nav_action.trigger()
    assert not window.nav.is_expanded()
    assert window.nav.button(PAGE_GRAPH).text() == ""
    window.toggle_nav_action.trigger()
    assert window.nav.is_expanded()


def test_developer_options_are_hidden_in_settings_behind_password(tmp_path):
    window = _make_window(tmp_path)
    page = window.settings_page
    assert not page.is_developer_unlocked()

    window.dev_action.trigger()  # help > developer options only jumps to settings
    assert window.current_page() == PAGE_SETTINGS
    assert not page.is_developer_unlocked()

    page.dev_password_input.setText("wrong")
    assert page.try_unlock() is False
    assert not page.is_developer_unlocked()

    page.dev_password_input.setText(DEFAULT_DEV_PASSWORD)
    assert page.try_unlock() is True
    assert page.is_developer_unlocked()
    assert "default password" in page.dev_message.text()

    page.lock_developer()
    assert not page.is_developer_unlocked()


def test_theme_switch_persists_and_updates_both_pickers(tmp_path):
    window = _make_window(tmp_path)
    theme_names = [a.text() for a in window.theme_menu.actions()]
    assert {"Dark", "Light"} <= set(theme_names)

    window.set_theme("light")
    assert load_app_settings(tmp_path / "config" / "settings.yaml").active_theme == "light"
    assert window.settings_page.theme_combo.currentData() == "light"
    checked = [a.text() for a in window.theme_menu.actions() if a.isChecked()]
    assert checked == ["Light"]


# -- a real session, end to end --

_FIXTURES = Path(__file__).parent / "fixtures"


# open (lazy imports), plot, advanced mode, theme, pdf export and close on one real log
@pytest.mark.skipif(not (_FIXTURES / "sample_log.mf4").exists(), reason="sample log fixture missing")
def test_open_session_export_and_close_end_to_end(tmp_path, monkeypatch):
    import PySide6.QtWidgets as qtw
    window = _make_window(tmp_path)
    shutil.copy(_FIXTURES / "value_table.dbc", tmp_path / "dbc_store" / "value_table.dbc")
    (tmp_path / "config" / "platforms" / "bench.yaml").write_text(
        "name: Bench\ndbc_path: value_table.dbc\n"
    )
    window.platforms = discover_platforms(tmp_path / "config" / "platforms")

    window._open_session(_FIXTURES / "sample_log.mf4", "bench")
    assert window.session_bar.count() == 1
    assert window.session_strip.isVisibleTo(window)
    assert window.export_action.isEnabled()
    session = window.current_session()
    assert "time" not in session.log_parser.decoded  # the master channel isn't a signal

    session._show_signal("RawValue")
    assert len(session.trace_view._series_cache) == 1

    # every analysis page switches the session's view, the session tabs stay on top
    for key in (PAGE_DATA, PAGE_TABLE, PAGE_GRAPH):
        window.show_page(key)
        assert session.current_view() == key
    window.show_page(PAGE_SETTINGS)
    assert window.session_strip.isVisibleTo(window)
    window._return_to_analysis()  # what clicking a session tab does from settings
    assert window.current_page() == PAGE_GRAPH

    window.advanced_action.setChecked(True)
    window.show_page(PAGE_ADVANCED)
    assert session.current_view() == PAGE_ADVANCED
    window.set_theme("light")

    out_pdf = tmp_path / "report.pdf"
    monkeypatch.setattr(qtw.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_pdf), "")))
    monkeypatch.setattr(qtw.QMessageBox, "critical", staticmethod(lambda *a, **k: pytest.fail(str(a))))
    window._export_report()
    assert out_pdf.read_bytes()[:4] == b"%PDF"

    window._close_tab(0)
    assert window.session_bar.count() == 0
    assert not window.session_strip.isVisibleTo(window)
    assert not window.export_action.isEnabled()
