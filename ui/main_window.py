#--------------------#
# main_window.py
# main window (menu bar, nav rail, session tabs, pages), open log dialog and help page
# layout map in docs/UI_GUIDE.md, architecture
#--------------------#
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QSplitter, QStackedWidget, QTabBar, QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

from core.config_loader import (
    AppSettings, ConfigLoadError, PlatformConfig, discover_platforms, discover_themes,
    load_theme_config, save_app_settings,
)
from core.help_content import list_help_keys, load_help_text
from core.theme_loader import apply_theme, derived_colors
from ui.settings_page import SettingsPage
from ui.widgets import (
    EmptyState, NavRail, PageHeader, action_button, button, filter_list, icon, label,
    refresh_all_widgets, search_field, set_icon_color,
)

# the decoding, plotting and report libraries load on first use, see docs/ARCHITECTURE.md, startup
if TYPE_CHECKING:
    from ui.session_view import SessionWidget

# analysis pages show the current session, keys match the views in ui/session_view.py
PAGE_GRAPH = "graph"
PAGE_DATA = "data"
PAGE_TABLE = "table"
PAGE_ADVANCED = "advanced"
PAGE_HELP = "help"
PAGE_SETTINGS = "settings"
ANALYSIS_PAGES = (PAGE_GRAPH, PAGE_DATA, PAGE_TABLE, PAGE_ADVANCED)

# nav and menu text, icon, shortcut, header subtitle
_PAGE_INFO = {
    PAGE_GRAPH: ("Graph analysis", "graph", "Ctrl+1",
                 "Plot signals, place cursors and read values at them"),
    PAGE_DATA: ("Data analysis", "analytics", "Ctrl+2",
                "Statistics for every signal, over the whole log or between the cursors"),
    PAGE_TABLE: ("Table view", "table", "Ctrl+3",
                 "Signals side by side on one time axis"),
    PAGE_ADVANCED: ("Advanced", "tools", "Ctrl+4",
                    "Force decode unknown CAN IDs, and view or edit the DBC"),
    PAGE_HELP: ("Help", "help", "F1", ""),
    PAGE_SETTINGS: ("Settings", "settings", "Ctrl+,", ""),
}


class MainWindow(QMainWindow):
    def __init__(self, app_root: Path, qt_app, settings: AppSettings, theme):
        super().__init__()
        self.app_root = app_root
        self.qt_app = qt_app
        self.settings = settings
        self.active_theme = theme
        self.settings_path = app_root / "config" / "settings.yaml"
        self.platforms_dir = app_root / "config" / "platforms"
        self.dbc_store_dir = app_root / "dbc_store"
        self.help_dir = app_root / "config" / "help"

        self.setWindowTitle("CAN Decoder")
        self.resize(1280, 820)
        self.setMinimumSize(900, 600)
        self.setAcceptDrops(True)
        if theme is not None:
            set_icon_color(derived_colors(theme)["text"])

        self.platforms = discover_platforms(self.platforms_dir)
        self.advanced_mode = False
        self._last_analysis_page = PAGE_GRAPH

        self._build_actions()
        self._build_pages()
        self._build_menu()
        self._build_status_bar()
        self._on_advanced_toggled(False)
        self.show_page(PAGE_GRAPH)

    # -- actions (shared between menu bar and page buttons) --
    # one action per command, shared by the menu bar and any page button
    def _build_actions(self) -> None:
        # file commands
        self.open_action = QAction(icon("open"), "Open Log…", self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_action.setToolTip("Open an MF4 log file (Ctrl+O)")
        self.open_action.triggered.connect(self._open_log_dialog)

        self.export_action = QAction(icon("export"), "Export PDF Report…", self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.setToolTip("Export the current session's signals to a PDF report (Ctrl+E)")
        self.export_action.triggered.connect(self._export_report)
        self.export_action.setEnabled(False)

        self.close_session_action = QAction(icon("close"), "Close Session", self)
        self.close_session_action.setShortcut(QKeySequence("Ctrl+W"))
        self.close_session_action.triggered.connect(
            lambda: self._close_tab(self.session_bar.currentIndex()) if self.session_bar.count() else None
        )
        self.close_session_action.setEnabled(False)

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self.exit_action.triggered.connect(self.close)

        # view commands
        self.advanced_action = QAction("Advanced Mode", self)
        self.advanced_action.setCheckable(True)
        self.advanced_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
        self.advanced_action.setToolTip(
            "Toggle Advanced Mode (adds the Advanced page) -- a soft, no-password toggle for this session"
        )
        self.advanced_action.toggled.connect(self._on_advanced_toggled)

        self.toggle_nav_action = QAction("Collapse Navigation", self)
        self.toggle_nav_action.setShortcut(QKeySequence("Ctrl+B"))
        self.toggle_nav_action.triggered.connect(self._toggle_nav)

        # one action per nav page, for the view menu and shortcuts
        self.page_actions: dict[str, QAction] = {}
        for key, (text, icon_name, shortcut, _subtitle) in _PAGE_INFO.items():
            act = QAction(icon(icon_name), text, self)
            act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(lambda _=False, k=key: self.show_page(k))
            self.page_actions[key] = act

        # help commands, developer options only jumps to settings (still password locked)
        self.dev_action = QAction(icon("lock"), "Developer Options…", self)
        self.dev_action.triggered.connect(self._go_to_developer_options)

        self.about_action = QAction(icon("info"), "About CAN Decoder", self)
        self.about_action.triggered.connect(self._show_about)

    # file / view / help menus
    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(self.close_session_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        view_menu = bar.addMenu("&View")
        for key in ANALYSIS_PAGES:
            view_menu.addAction(self.page_actions[key])
        view_menu.addSeparator()
        view_menu.addAction(self.page_actions[PAGE_HELP])
        view_menu.addAction(self.page_actions[PAGE_SETTINGS])
        view_menu.addSeparator()
        view_menu.addAction(self.advanced_action)
        self.theme_menu = view_menu.addMenu(icon("palette"), "Theme")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._rebuild_theme_menu()
        view_menu.addSeparator()
        view_menu.addAction(self.toggle_nav_action)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.page_actions[PAGE_HELP])
        help_menu.addSeparator()
        help_menu.addAction(self.dev_action)
        help_menu.addSeparator()
        help_menu.addAction(self.about_action)

    # one checkable entry per theme file that loads
    def _rebuild_theme_menu(self) -> None:
        self.theme_menu.clear()
        for act in self._theme_group.actions():
            self._theme_group.removeAction(act)
        themes = discover_themes(self.app_root / "config" / "themes")
        for name, theme in themes.items():
            if isinstance(theme, ConfigLoadError):
                continue
            act = QAction(name.replace("_", " ").title(), self)
            act.setData(name)
            act.setCheckable(True)
            act.setChecked(name == self.settings.active_theme)
            act.triggered.connect(lambda _=False, n=name: self.set_theme(n))
            self._theme_group.addAction(act)
            self.theme_menu.addAction(act)

    # -- layout --
    # nav rail on the left; session tabs across the top of every page, then the page itself
    def _build_pages(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # analysis pages top to bottom, a gap, then help and settings pinned low
        self.nav = NavRail()
        for key in ANALYSIS_PAGES:
            text, icon_name, _shortcut, _subtitle = _PAGE_INFO[key]
            self.nav.add_page(key, text, icon_name)
        for key in (PAGE_HELP, PAGE_SETTINGS):
            text, icon_name, _shortcut, _subtitle = _PAGE_INFO[key]
            self.nav.add_page(key, text, icon_name, bottom=True)
        self.nav.page_selected.connect(self.show_page)
        root.addWidget(self.nav)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addWidget(self._build_session_strip())
        self.pages = QStackedWidget()
        rv.addWidget(self.pages, stretch=1)
        root.addWidget(right, stretch=1)
        self._page_index: dict[str, int] = {}

        analysis_index = self.pages.addWidget(self._build_analysis_page())
        for key in ANALYSIS_PAGES:
            self._page_index[key] = analysis_index
        self.help_page = HelpPage(self.help_dir, self.app_root / "config" / "defaults" / "help")
        self._page_index[PAGE_HELP] = self.pages.addWidget(self.help_page)
        self.settings_page = SettingsPage(
            self.app_root, self.settings, self.settings_path,
            self.advanced_action, self.set_theme,
        )
        self._page_index[PAGE_SETTINGS] = self.pages.addWidget(self.settings_page)
        self.setCentralWidget(central)

    # one tab per open log, shown above every page, with an open button on the end
    # the tab data holds the SessionWidget, so dragging tabs around needs no bookkeeping
    def _build_session_strip(self) -> QWidget:
        self.session_strip = QFrame()
        self.session_strip.setObjectName("sessionStrip")
        row = QHBoxLayout(self.session_strip)
        row.setContentsMargins(12, 6, 12, 0)
        row.setSpacing(4)
        self.session_bar = QTabBar()
        self.session_bar.setDocumentMode(True)
        self.session_bar.setTabsClosable(True)
        self.session_bar.setMovable(True)
        self.session_bar.setExpanding(False)
        self.session_bar.setElideMode(Qt.ElideMiddle)
        self.session_bar.tabCloseRequested.connect(self._close_tab)
        self.session_bar.currentChanged.connect(lambda _i: self._on_session_changed())
        # clicking a session from help or settings goes back to the last analysis page
        self.session_bar.tabBarClicked.connect(lambda _i: self._return_to_analysis())
        row.addWidget(self.session_bar)
        new_tab = QToolButton()
        new_tab.setIcon(icon("add"))
        new_tab.setToolTip("Open another log (Ctrl+O)")
        new_tab.setCursor(Qt.PointingHandCursor)
        new_tab.setAutoRaise(True)
        new_tab.clicked.connect(lambda: self._open_log_dialog())
        row.addWidget(new_tab)
        row.addStretch(1)
        return self.session_strip

    # header, then an empty state or the current session's view
    def _build_analysis_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.analysis_header = PageHeader("Graph analysis", "")
        self.analysis_header.add_action_widget(action_button(self.export_action))
        self.analysis_header.add_action_widget(action_button(self.open_action, variant="primary"))
        layout.addWidget(self.analysis_header)

        # index 0 empty state, index 1 the sessions
        self.analysis_stack = QStackedWidget()
        open_btn = button("Open log…", variant="primary", icon_name="open",
                          on_click=self._open_log_dialog)
        self.empty_state = EmptyState(
            "graph", "No logs open",
            "Open an MF4 log to decode it against a vehicle platform. You can also drag a "
            ".mf4 file onto this window. Each log opens in its own tab along the top, and "
            "every page works on the tab that's selected.",
            [open_btn],
        )
        self.analysis_stack.addWidget(self.empty_state)
        self.session_stack = QStackedWidget()
        sessions_wrap = QWidget()
        sw = QVBoxLayout(sessions_wrap)
        sw.setContentsMargins(12, 0, 12, 0)
        sw.addWidget(self.session_stack)
        self.analysis_stack.addWidget(sessions_wrap)
        layout.addWidget(self.analysis_stack, stretch=1)
        return page

    def _build_status_bar(self) -> None:
        self.mode_label = QLabel("Simple mode")
        self.session_info_label = QLabel("")
        self.statusBar().addWidget(self.mode_label)
        self.statusBar().addPermanentWidget(self.session_info_label)
        self.statusBar().setSizeGripEnabled(False)

    # -- navigation --
    def show_page(self, key: str) -> None:
        if key == PAGE_ADVANCED and not self.advanced_mode:
            key = PAGE_GRAPH
        self.pages.setCurrentIndex(self._page_index[key])
        self.nav.select(key)
        if key in ANALYSIS_PAGES:
            self._last_analysis_page = key
            for widget in self._session_widgets():
                widget.show_view(key)
            self._refresh_session_chrome()
        elif key == PAGE_SETTINGS:
            self.settings_page.refresh_update_source()
        elif key == PAGE_HELP:
            self.help_page.reload()

    def current_page(self) -> Optional[str]:
        return self.nav.current()

    def _return_to_analysis(self) -> None:
        if self.current_page() not in ANALYSIS_PAGES:
            self.show_page(self._last_analysis_page)

    def _toggle_nav(self) -> None:
        self.nav.toggle_expanded()
        self.toggle_nav_action.setText(
            "Collapse Navigation" if self.nav.is_expanded() else "Expand Navigation"
        )

    def _go_to_developer_options(self) -> None:
        self.show_page(PAGE_SETTINGS)
        self.settings_page.reveal_developer()

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About CAN Decoder",
            f"<h3>CAN Decoder</h3><p>Version {self.settings.version}</p>"
            "<p>Decode and plot CAN bus logs (MF4) against vehicle DBC files.</p>",
        )

    # -- mode handling --
    # no password needed, shows or hides the advanced page
    def _on_advanced_toggled(self, checked: bool) -> None:
        self.advanced_mode = checked
        self.mode_label.setText("Advanced mode" if checked else "Simple mode")
        self.nav.set_page_visible(PAGE_ADVANCED, checked)
        self.page_actions[PAGE_ADVANCED].setEnabled(checked)
        if not checked and self.current_page() == PAGE_ADVANCED:
            self.show_page(PAGE_GRAPH)

    # -- theme --
    # applies and saves a theme, then syncs the menu, the settings combo and open plots
    def set_theme(self, name: str) -> None:
        try:
            theme = load_theme_config(self.app_root / "config" / "themes" / f"{name}.yaml")
        except ConfigLoadError:
            QMessageBox.warning(self, "Theme unavailable", f"The theme {name!r} couldn't be loaded.")
            return
        set_icon_color(derived_colors(theme)["text"])
        apply_theme(self.qt_app, theme)
        self.active_theme = theme
        self.settings.active_theme = name
        save_app_settings(self.settings_path, self.settings)
        for act in self._theme_group.actions():
            act.setChecked(act.data() == name)
        idx = self.settings_page.theme_combo.findData(name)
        if idx >= 0 and self.settings_page.theme_combo.currentIndex() != idx:
            self.settings_page.theme_combo.blockSignals(True)
            self.settings_page.theme_combo.setCurrentIndex(idx)
            self.settings_page.theme_combo.blockSignals(False)
        for widget in self._session_widgets():
            widget.apply_theme(theme)
        refresh_all_widgets()

    # -- sessions --
    # drag an .mf4 onto the window to open it
    def dragEnterEvent(self, event) -> None:
        if any(u.toLocalFile().lower().endswith(".mf4") for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".mf4"):
                self._open_log_dialog(path)
                break

    def _open_log_dialog(self, initial_path: Optional[str] = None) -> None:
        # re-read platforms each time since they can be edited while the app runs
        self.platforms = discover_platforms(self.platforms_dir)
        valid = {n: p for n, p in self.platforms.items() if not isinstance(p, ConfigLoadError)}
        if not valid:
            QMessageBox.warning(
                self, "No platforms configured",
                "There are no usable vehicle platforms yet.\n\n"
                "Add one under Settings › Developer options › Manage platforms, "
                "or copy config/defaults/platform_template.yaml into config/platforms/."
            )
            return

        dlg = OpenLogDialog(valid, initial_path if isinstance(initial_path, str) else "", self)
        if not dlg.exec():
            return
        path_str, platform_name = dlg.selected()
        self._open_session(Path(path_str), platform_name)

    # one SessionWidget per session tab, in tab order
    def _session_widgets(self) -> list[SessionWidget]:
        widgets = (self.session_bar.tabData(i) for i in range(self.session_bar.count()))
        return [w for w in widgets if w is not None]  # tab data is set just after addTab

    def current_session(self) -> Optional[SessionWidget]:
        index = self.session_bar.currentIndex()
        return self.session_bar.tabData(index) if index >= 0 else None

    # decodes the log and adds it as a new tab
    def _open_session(self, log_path: Path, platform_name: str) -> None:
        from core.dbc_handler import DbcHandler
        from core.log_parser import LogParser
        from ui.session_view import SessionWidget

        platform = self.platforms[platform_name]
        platform_path = self.platforms_dir / f"{platform_name}.yaml"
        dbc_path = self.dbc_store_dir / platform.dbc_path

        self.statusBar().showMessage(f"Decoding {log_path.name}…")
        self.qt_app.processEvents()
        try:
            dbc_handler = DbcHandler(dbc_path)
            log_parser = LogParser(log_path, dbc_handler)
            log_parser.load()
        except Exception as exc:
            self.statusBar().clearMessage()
            QMessageBox.critical(self, "Couldn't open log", str(exc))
            return
        self.statusBar().clearMessage()

        widget = SessionWidget(log_path, dbc_handler, log_parser, platform, platform_path,
                               self.active_theme, self.help_dir)
        widget.view_requested.connect(self.show_page)
        self.session_stack.addWidget(widget)
        index = self.session_bar.addTab(icon("document"), log_path.name)
        self.session_bar.setTabData(index, widget)
        self.session_bar.setTabToolTip(index, f"{log_path}\nPlatform: {platform.name}")
        self.session_bar.setCurrentIndex(index)
        self._on_session_changed()  # addTab signals before the tab data is set
        self.show_page(self._last_analysis_page)

    # closing a tab closes its mf4 file and drops any session-only dbc edits
    def _close_tab(self, index: int) -> None:
        widget = self.session_bar.tabData(index)
        if widget is None:
            return
        widget.log_parser.close()
        self.session_bar.removeTab(index)
        self.session_stack.removeWidget(widget)
        widget.deleteLater()
        self._on_session_changed()

    def _on_session_changed(self) -> None:
        widget = self.current_session()
        if widget is not None:
            self.session_stack.setCurrentWidget(widget)
        self._refresh_session_chrome()

    # keeps the header, status bar and enabled actions in sync with the tabs and page
    def _refresh_session_chrome(self) -> None:
        count = self.session_bar.count()
        self.session_strip.setVisible(count > 0)
        self.analysis_stack.setCurrentIndex(1 if count else 0)
        self.export_action.setEnabled(count > 0)
        self.close_session_action.setEnabled(count > 0)
        title, _icon, _shortcut, subtitle = _PAGE_INFO[self._last_analysis_page]
        self.analysis_header.title.setText(title)
        widget = self.current_session()
        if widget is not None:
            parser = widget.log_parser
            self.analysis_header.set_subtitle(
                f"{widget.log_path.name} on {widget.platform.name}  •  {subtitle}"
            )
            self.session_info_label.setText(
                f"{len(parser.decoded)} signals decoded  •  "
                f"{len(parser.not_decoded_ids)} unknown CAN IDs"
            )
        else:
            self.analysis_header.set_subtitle(subtitle)
            self.session_info_label.setText("")

    # -- report export --
    # pdf of the important values (or every numeric signal) in the current tab
    # snapshots go in a temp folder that is removed once the pdf is written
    def _export_report(self) -> None:
        widget = self.current_session()
        if widget is None:
            QMessageBox.information(self, "No session", "Open a log first.")
            return
        default_name = widget.log_path.with_suffix(".pdf").name
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report", default_name, "PDF Files (*.pdf)"
        )
        if not path_str:
            return

        parser = widget.log_parser
        names = widget.platform.important_values or list(parser.decoded)
        names = [n for n in names if n in parser.decoded and n in parser.summaries]
        if not names:
            QMessageBox.warning(self, "Nothing to export", "No signals available to include.")
            return

        from core.plot_engine import render_static_snapshot
        from core.report_builder import ReportBuilder

        try:
            with tempfile.TemporaryDirectory(prefix="can_report_") as tmp:
                selected = {}
                for i, name in enumerate(names):
                    series = parser.decoded[name]
                    png_path = render_static_snapshot(
                        name, series.timestamps, series.values, Path(tmp) / f"{i}.png"
                    )
                    selected[name] = (parser.summaries[name], png_path)
                ReportBuilder(widget.log_path.name).build(Path(path_str), selected)
            self.statusBar().showMessage(f"Report saved to {path_str}", 6000)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))


# -- open log dialog --

# picks the file and platform together, shows which dbc the log will use
class OpenLogDialog(QDialog):
    def __init__(self, platforms: dict[str, PlatformConfig], initial_path: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Log")
        self.setMinimumWidth(520)
        self._platforms = platforms

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(label("Open a log", "title"))
        layout.addWidget(label("Choose an MF4 file and the vehicle platform it came from.", "muted"))

        form = QFormLayout()
        form.setSpacing(10)
        file_row = QHBoxLayout()
        self.path_input = QLineEdit(initial_path)
        self.path_input.setPlaceholderText("Path to an .mf4 file")
        self.path_input.textChanged.connect(self._validate)
        file_row.addWidget(self.path_input, stretch=1)
        file_row.addWidget(button("Browse…", icon_name="folder", on_click=self._browse))
        form.addRow("Log file", file_row)

        self.platform_combo = QComboBox()
        for slug, cfg in sorted(platforms.items(), key=lambda kv: kv[1].name.lower()):
            self.platform_combo.addItem(icon("car"), cfg.name, slug)
        self.platform_combo.currentIndexChanged.connect(self._update_platform_info)
        form.addRow("Platform", self.platform_combo)
        layout.addLayout(form)

        self.platform_info = label("", "muted", wrap=True)
        layout.addWidget(self.platform_info)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Open).setProperty("variant", "primary")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._update_platform_info()
        self._validate()
        if not initial_path:
            self.path_input.setFocus()

    def _browse(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Open MF4 Log", self.path_input.text(),
                                                  "MF4 Files (*.mf4);;All Files (*)")
        if path_str:
            self.path_input.setText(path_str)

    def _update_platform_info(self) -> None:
        cfg = self._platforms.get(self.platform_combo.currentData())
        if cfg is None:
            self.platform_info.setText("")
            return
        parts = [cfg.description.strip()] if cfg.description.strip() else []
        parts.append(f"DBC: {cfg.dbc_path}")
        self.platform_info.setText("  •  ".join(parts))

    # open stays disabled until the path points at a real file
    def _validate(self) -> None:
        ok = Path(self.path_input.text().strip()).is_file()
        self.buttons.button(QDialogButtonBox.Open).setEnabled(ok)

    def selected(self) -> tuple[str, str]:
        return self.path_input.text().strip(), self.platform_combo.currentData()


# -- help page --

# searchable list of help topics, editing lives in developer options
class HelpPage(QWidget):
    def __init__(self, help_dir: Path, defaults_dir: Path, parent=None):
        super().__init__(parent)
        self.help_dir = help_dir
        self.defaults_dir = defaults_dir
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(PageHeader("Help", "How to use CAN Decoder"))

        # topic search and list on the left, rendered topic on the right
        splitter = QSplitter()
        splitter.setContentsMargins(16, 12, 16, 16)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(16, 12, 4, 16)
        self.topic_list = QListWidget()
        self.search = search_field("Search topics", lambda text: filter_list(self.topic_list, text))
        lv.addWidget(self.search)
        self.topic_list.currentItemChanged.connect(self._show_topic)
        lv.addWidget(self.topic_list)
        splitter.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 12, 16, 16)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        rv.addWidget(self.browser)
        splitter.addWidget(right)
        splitter.setSizes([240, 700])
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)
        self.reload()

    # rebuilds the list and keeps the current topic selected
    def reload(self) -> None:
        current = self.topic_list.currentItem()
        current_key = current.data(Qt.UserRole) if current else None
        self.topic_list.blockSignals(True)
        self.topic_list.clear()
        for key in list_help_keys(self.help_dir, self.defaults_dir):
            item = QListWidgetItem(icon("document"), key.replace("_", " ").capitalize())
            item.setData(Qt.UserRole, key)
            self.topic_list.addItem(item)
            if key == current_key:
                self.topic_list.setCurrentItem(item)
        self.topic_list.blockSignals(False)
        if self.topic_list.currentItem() is None and self.topic_list.count():
            self.topic_list.setCurrentRow(0)
        else:
            self._show_topic(self.topic_list.currentItem())
        if not self.topic_list.count():
            self.browser.setMarkdown("*No help topics yet.*")
        filter_list(self.topic_list, self.search.text())

    def _show_topic(self, item, _previous=None) -> None:
        if item is None:
            return
        self.browser.setMarkdown(load_help_text(self.help_dir, item.data(Qt.UserRole)))
