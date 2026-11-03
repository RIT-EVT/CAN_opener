#--------------------#
# session_view.py
# one open log (a session tab): graph, data analysis, table and advanced pages, and the important signals editor
# imported only when a log opens, see docs/ARCHITECTURE.md, startup
#--------------------#
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QListWidget, QListWidgetItem, QMenu, QSplitter,
    QStackedWidget, QVBoxLayout, QWidget,
)

from core.config_loader import PlatformConfig, save_platform_config
from core.dbc_handler import DbcHandler
from core.log_parser import LogParser
from core.signal_stats import label_text
from ui.data_view import DataAnalysisView
from ui.help_viewer import make_help_button
from ui.signal_browser import SignalBrowser
from ui.tabular_view import TabularView
from ui.trace_view import TraceView
from ui.widgets import SignalList, button, filter_list, icon, label, search_field

# the same keys as the analysis pages in ui/main_window.py
VIEW_GRAPH, VIEW_DATA, VIEW_TABLE, VIEW_ADVANCED = "graph", "data", "table", "advanced"


# -- session view (one per tab) --

# one page per analysis view, the main window picks which one shows
class SessionWidget(QWidget):
    # another page asked to show a view, e.g. plotting from data analysis jumps to the graph
    view_requested = Signal(str)

    def __init__(self, log_path: Path, dbc_handler: DbcHandler, log_parser: LogParser,
                 platform: PlatformConfig, platform_path: Path, theme, help_dir: Path,
                 parent=None):
        super().__init__(parent)
        self.log_path = log_path
        self.dbc_handler = dbc_handler
        self.log_parser = log_parser
        self.platform = platform
        self.platform_path = platform_path
        self.help_dir = help_dir

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 8)
        self.views = QStackedWidget()
        outer.addWidget(self.views)
        self._view_index: dict[str, int] = {}

        self.trace_view = TraceView(theme, help_dir)
        self._view_index[VIEW_GRAPH] = self.views.addWidget(self._build_graph_page())

        self.data_view = DataAnalysisView(
            log_parser, theme, self.important_names, self.trace_view.plotted_names,
            self.trace_view.cursor_range,
        )
        self._view_index[VIEW_DATA] = self.views.addWidget(self.data_view)

        self.table_view = TabularView(
            log_parser, theme, self.important_names, self.trace_view.plotted_names,
            self.trace_view.plot.cursor_pos,
        )
        self._view_index[VIEW_TABLE] = self.views.addWidget(self.table_view)

        self.advanced_panel = SignalBrowser(dbc_handler, log_parser)
        self._view_index[VIEW_ADVANCED] = self.views.addWidget(self.advanced_panel)

        # every page plots through _show_signal, and plotting elsewhere brings the graph forward
        self.trace_view.signals_dropped.connect(lambda names: [self._show_signal(n) for n in names])
        self.trace_view.cursors_changed.connect(self.data_view.mark_dirty)
        self.data_view.plot_requested.connect(self._plot_and_show_graph)
        self.data_view.important_changed.connect(self._on_important_changed)
        self.advanced_panel.plot_requested.connect(self._plot_and_show_graph)
        self.advanced_panel.signals_added.connect(lambda _names: self._on_signals_added())

    def show_view(self, key: str) -> None:
        self.views.setCurrentIndex(self._view_index[key])

    def current_view(self) -> str:
        return next(k for k, i in self._view_index.items() if i == self.views.currentIndex())

    def apply_theme(self, theme) -> None:
        self.trace_view.apply_theme(theme)
        self.data_view.apply_theme(theme)
        self.table_view.apply_theme(theme)

    # -- graph page --

    # sidebar of signal lists on the left, plot on the right
    def _build_graph_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self.trace_view)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([290, 900])
        return page

    # one filter over both lists, important signals on top, every signal below
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setMinimumWidth(240)
        left = QVBoxLayout(side)
        left.setContentsMargins(0, 0, 6, 0)
        left.setSpacing(8)

        self.values_filter = search_field("Filter signals", self._apply_filter)
        left.addWidget(self.values_filter)

        lists = QSplitter(Qt.Vertical)
        lists.setChildrenCollapsible(False)

        top = QWidget()
        tv = QVBoxLayout(top)
        tv.setContentsMargins(0, 0, 0, 4)
        tv.setSpacing(4)
        header = QHBoxLayout()
        header.addWidget(label("Important signals", "section"))
        header.addWidget(make_help_button(self.help_dir, "important_values", "Important Signals", self))
        header.addStretch()
        self.edit_values_btn = button("", variant="subtle", icon_name="edit",
                                      tooltip="Choose important signals from a checklist",
                                      on_click=self._edit_important_values)
        header.addWidget(self.edit_values_btn)
        tv.addLayout(header)
        self.values_list = SignalList(
            "Drag signals here from All signals to keep them for this platform", accept_drops=True
        )
        self.values_list.setToolTip("Click to plot. Drag to reorder, or drag onto the plot. "
                                    "Delete removes from this list.")
        self.values_list.itemClicked.connect(lambda item: self._show_signal(item.text()))
        self.values_list.names_dropped.connect(self._on_dropped_on_important)
        self.values_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.values_list.customContextMenuRequested.connect(self._important_menu)
        remove_action = QAction("Remove from important signals", self.values_list)
        remove_action.setShortcut(QKeySequence.Delete)
        remove_action.setShortcutContext(Qt.WidgetShortcut)
        remove_action.triggered.connect(self._remove_selected_important)
        self.values_list.addAction(remove_action)
        tv.addWidget(self.values_list, stretch=1)
        lists.addWidget(top)

        bottom = QWidget()
        bv = QVBoxLayout(bottom)
        bv.setContentsMargins(0, 4, 0, 0)
        bv.setSpacing(4)
        self.all_title = label("All signals", "section")
        bv.addWidget(self.all_title)
        self.all_list = SignalList(accept_drops=True)
        self.all_list.setToolTip("Click to plot. Drag onto Important signals to keep it, "
                                 "or onto the plot to plot it.")
        # dropping an important signal back here removes it from the important list
        self.all_list.drop_sources = (self.values_list,)
        self.all_list.itemClicked.connect(lambda item: self._show_signal(item.text()))
        self.all_list.names_dropped.connect(
            lambda names, _row, _src: self._on_important_changed(names, False)
        )
        self.all_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.all_list.customContextMenuRequested.connect(self._all_menu)
        bv.addWidget(self.all_list, stretch=1)
        lists.addWidget(bottom)
        lists.setSizes([260, 380])
        left.addWidget(lists, stretch=1)

        self._refresh_values_list()
        return side

    # important list keeps names this log doesn't have, dimmed, so other logs still get them
    def _refresh_values_list(self) -> None:
        decoded = self.log_parser.decoded
        self.values_list.set_names(self.important_names())
        muted = QColor(self.palette().color(self.foregroundRole()))
        muted.setAlphaF(0.45)
        for i in range(self.values_list.count()):
            item = self.values_list.item(i)
            if item.text() not in decoded:
                item.setForeground(muted)
                item.setToolTip("Not in this log")

        important = set(self.important_names())
        star, blank = icon("star_filled"), _blank_icon()
        names = sorted(decoded, key=str.lower)
        self.all_list.set_names(names, icon_for=lambda n: star if n in important else blank)
        self.all_title.setText(f"All signals ({len(names)})")
        self._apply_filter(self.values_filter.text())

    def _apply_filter(self, text: str) -> None:
        filter_list(self.values_list, text)
        filter_list(self.all_list, text)

    # -- important signals --

    def important_names(self) -> list[str]:
        return list(self.platform.important_values)

    # saves the list back to the platform yaml and refreshes every page that shows it
    def _set_important(self, names: list[str]) -> None:
        self.platform.important_values = list(dict.fromkeys(names))  # no duplicates, order kept
        save_platform_config(self.platform_path, self.platform)
        self._refresh_values_list()
        self.data_view.mark_dirty()

    def _on_important_changed(self, names: list[str], add: bool) -> None:
        current = self.important_names()
        if add:
            self._set_important(current + [n for n in names if n not in current])
        else:
            self._set_important([n for n in current if n not in set(names)])

    # a drop from the list itself reorders, from anywhere else inserts at the drop row
    def _on_dropped_on_important(self, names: list[str], row: int, source) -> None:
        current = self.important_names()
        moving = [n for n in names if n in current] if source is self.values_list else \
                 [n for n in names if n not in current]
        if not moving:
            return
        before = sum(1 for n in current[:row] if n in moving)
        kept = [n for n in current if n not in moving]
        at = max(0, min(len(kept), row - before))
        self._set_important(kept[:at] + moving + kept[at:])

    def _remove_selected_important(self) -> None:
        names = self.values_list.selected_names()
        if names:
            self._on_important_changed(names, False)

    def _important_menu(self, pos) -> None:
        names = self.values_list.selected_names()
        if not names:
            return
        menu = QMenu(self)
        menu.addAction(icon("graph"), "Plot", lambda: [self._show_signal(n) for n in names])
        menu.addAction(icon("star"), "Remove from important signals",
                       lambda: self._on_important_changed(names, False))
        menu.exec(self.values_list.viewport().mapToGlobal(pos))

    def _all_menu(self, pos) -> None:
        names = self.all_list.selected_names()
        if not names:
            return
        important = set(self.important_names())
        menu = QMenu(self)
        menu.addAction(icon("graph"), "Plot", lambda: [self._show_signal(n) for n in names])
        to_add = [n for n in names if n not in important]
        to_remove = [n for n in names if n in important]
        if to_add:
            menu.addAction(icon("star_filled"), "Add to important signals",
                           lambda: self._on_important_changed(to_add, True))
        if to_remove:
            menu.addAction(icon("star"), "Remove from important signals",
                           lambda: self._on_important_changed(to_remove, False))
        menu.exec(self.all_list.viewport().mapToGlobal(pos))

    # checklist alternative to dragging, saves the new list back to the platform yaml
    def _edit_important_values(self) -> None:
        dlg = ImportantValuesDialog(
            sorted(set(self.log_parser.decoded) | set(self.important_names()), key=str.lower),
            self.important_names(), self,
        )
        if dlg.exec():
            self._set_important(dlg.selected_values())

    # -- plotting --

    # single path for plotting a signal, every list, drop and page uses it
    def _show_signal(self, name: str) -> None:
        series = self.log_parser.decoded.get(name)
        if series is None:
            return
        if np.issubdtype(series.values.dtype, np.number):
            self.trace_view.add_signal(name, series.timestamps, series.values, series.unit)
        else:
            self._plot_categorical(name, series)

    # enum signals decode to text, so plot them as integer codes and label them at the cursors
    def _plot_categorical(self, name, series) -> None:
        labels, codes = np.unique(series.values, return_inverse=True)
        self.trace_view.add_signal(name, series.timestamps, codes.astype(float), series.unit,
                                   labels=[label_text(lbl) for lbl in labels])

    def _plot_and_show_graph(self, name: str) -> None:
        self._show_signal(name)
        self.view_requested.emit(VIEW_GRAPH)

    # force decode added signals to the log
    def _on_signals_added(self) -> None:
        self._refresh_values_list()
        self.table_view.refresh_signal_list()
        self.data_view.mark_dirty()


def _blank_icon() -> QIcon:
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    return QIcon(pm)


# -- important signals editor --

# checklist of every decoded signal with a filter and all/none buttons
class ImportantValuesDialog(QDialog):
    def __init__(self, all_signals: list[str], selected: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Important Signals")
        self.resize(420, 520)
        self._order = list(selected)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(label("Important signals", "title"))
        layout.addWidget(label(
            "Checked signals appear in the Important signals list for this platform.", "muted", wrap=True
        ))

        self.checklist = QListWidget()
        chosen = set(selected)
        for name in all_signals:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in chosen else Qt.Unchecked)
            self.checklist.addItem(item)

        tools = QHBoxLayout()
        self.filter_input = search_field(
            "Filter signals", lambda text: filter_list(self.checklist, text)
        )
        tools.addWidget(self.filter_input, stretch=1)
        tools.addWidget(button("All", variant="subtle", on_click=lambda: self._set_all(True)))
        tools.addWidget(button("None", variant="subtle", on_click=lambda: self._set_all(False)))
        layout.addLayout(tools)
        layout.addWidget(self.checklist, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setProperty("variant", "primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # only touches rows the filter is showing
    def _set_all(self, checked: bool) -> None:
        for i in range(self.checklist.count()):
            item = self.checklist.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    # keeps the existing order, newly checked signals go on the end
    def selected_values(self) -> list[str]:
        checked = [
            self.checklist.item(i).text() for i in range(self.checklist.count())
            if self.checklist.item(i).checkState() == Qt.Checked
        ]
        kept = [n for n in self._order if n in checked]
        return kept + [n for n in checked if n not in kept]
