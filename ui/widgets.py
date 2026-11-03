#--------------------#
# widgets.py
# shared ui pieces: icons, buttons, search fields, signal lists, cards, rows, page header, nav rail, empty state
# styling lives in core/theme_loader.py, usage in docs/UI_GUIDE.md
#--------------------#
from __future__ import annotations

from typing import Callable, Iterable, Optional

from PySide6.QtCore import QMimeData, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QIcon, QIconEngine, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

# -- icons --
# drawn from the windows icon font (fluent on 11, mdl2 on 10), unicode fallback elsewhere

_GLYPHS = {
    #  name          font glyph   fallback
    "menu":         ("", "☰"),
    "sessions":     ("", "≈"),
    "open":         ("", "↗"),
    "export":       ("", "⇩"),
    "settings":     ("", "⚙"),
    "help":         ("", "?"),
    "info":         ("", "i"),
    "lock":         ("", "⚿"),
    "unlock":       ("", "⚿"),
    "add":          ("", "+"),
    "delete":       ("", "✕"),
    "close":        ("", "✕"),
    "refresh":      ("", "↻"),
    "search":       ("", "⌕"),
    "folder":       ("", "▤"),
    "code":         ("", "</>"),
    "car":          ("", "▣"),
    "document":     ("", "▤"),
    "edit":         ("", "✎"),
    "save":         ("", "✓"),
    "sync":         ("", "⇅"),
    "upload":       ("", "⇧"),
    "download":     ("", "⇩"),
    "view":         ("", "◉"),
    "hide":         ("", "○"),
    "zoom_fit":     ("", "⤢"),
    "target":       ("", "◎"),
    "palette":      ("", "◐"),
    "shield":       ("", "⛨"),
    "update":       ("", "↻"),
    "list":         ("", "≡"),
    "database":     ("", "▦"),
    "graph":        ("", "≈"),
    "analytics":    ("", "Σ"),
    "table":        ("", "▦"),
    "tools":        ("", "⚒"),
    "star":         ("", "☆"),
    "star_filled":  ("", "★"),
}

_icon_font_family: Optional[str] = None
_icon_color = "#e6e6e6"


# first installed icon font, cached
def _resolve_icon_font() -> Optional[str]:
    global _icon_font_family
    if _icon_font_family is None:
        families = set(QFontDatabase.families())
        _icon_font_family = next(
            (f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), ""
        )
    return _icon_font_family or None


# called on every theme change so icons match the text color
def set_icon_color(color: str) -> None:
    global _icon_color
    _icon_color = color


# paints at draw time, so a theme switch recolors icons already on screen
class _GlyphIconEngine(QIconEngine):
    def __init__(self, name: str, color: Optional[str] = None):
        super().__init__()
        self._name = name
        self._color = color

    def paint(self, painter: QPainter, rect: QRect, mode, state) -> None:
        font_family = _resolve_icon_font()
        glyph, fallback = _GLYPHS.get(self._name, ("", "?"))
        color = QColor(self._color or _icon_color)
        if mode == QIcon.Disabled:
            color.setAlphaF(0.4)
        painter.save()
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setPen(color)
        font = QFont(font_family) if font_family else QFont()
        font.setPixelSize(max(8, int(rect.height() * 0.8)))
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, glyph if font_family else fallback)
        painter.restore()

    def pixmap(self, size: QSize, mode, state) -> QPixmap:
        pm = QPixmap(size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        self.paint(painter, QRect(QPoint(0, 0), size), mode, state)
        painter.end()
        return pm

    def clone(self) -> QIconEngine:
        return _GlyphIconEngine(self._name, self._color)


# icon by name from _GLYPHS, color defaults to the theme text color
def icon(name: str, color: Optional[str] = None) -> QIcon:
    return QIcon(_GlyphIconEngine(name, color))


# -- small helpers --

# role picks the label style (title, subtitle, section, muted, stat, statLabel, error)
def label(text: str, role: Optional[str] = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


# variant is primary, danger or subtle (none for a normal button)
def button(text: str, variant: Optional[str] = None, icon_name: Optional[str] = None,
           tooltip: Optional[str] = None, on_click: Optional[Callable] = None) -> QPushButton:
    btn = QPushButton(text)
    if variant:
        btn.setProperty("variant", variant)
    if icon_name:
        btn.setIcon(icon(icon_name))
    if tooltip:
        btn.setToolTip(tooltip)
    if on_click:
        btn.clicked.connect(on_click)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


# page button driven by the same action as the menu entry
def action_button(action: QAction, variant: Optional[str] = None) -> QToolButton:
    btn = QToolButton()
    btn.setDefaultAction(action)
    btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    btn.setCursor(Qt.PointingHandCursor)
    if variant:
        btn.setProperty("variant", variant)
    return btn


# search box with a leading icon and a clear button, on_change gets the text
def search_field(placeholder: str, on_change: Callable[[str], None]) -> QLineEdit:
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    field.addAction(icon("search"), QLineEdit.LeadingPosition)
    field.setClearButtonEnabled(True)
    field.textChanged.connect(on_change)
    return field


# hides list rows that don't contain text (case-insensitive)
def filter_list(list_widget: QListWidget, text: str) -> None:
    text = text.strip().lower()
    for i in range(list_widget.count()):
        item = list_widget.item(i)
        item.setHidden(bool(text) and text not in item.text().lower())


# -- dragging signals between lists and onto the plot --

SIGNAL_MIME = "application/x-can-signal-names"


def signal_names_mime(names: list[str]) -> QMimeData:
    mime = QMimeData()
    text = "\n".join(names)
    mime.setData(SIGNAL_MIME, text.encode("utf-8"))
    mime.setText(text)
    return mime


# the dragged signal names, [] if the drag isn't signals
def signal_names_from_mime(mime: QMimeData) -> list[str]:
    if not mime.hasFormat(SIGNAL_MIME):
        return []
    return [n for n in bytes(mime.data(SIGNAL_MIME)).decode("utf-8").split("\n") if n]


# list of signal names that can be dragged out, and optionally dropped onto
# the owner decides what a drop means through names_dropped, the list never edits itself
class SignalList(QListWidget):
    # dropped names, the row they were dropped at, and the widget they came from
    names_dropped = Signal(list, int, object)

    def __init__(self, placeholder: str = "", accept_drops: bool = False, parent=None):
        super().__init__(parent)
        self.placeholder = placeholder
        # None accepts any source, otherwise only these widgets (the list itself counts)
        self.drop_sources: Optional[tuple] = None
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setDragDropMode(QAbstractItemView.DragDrop if accept_drops else QAbstractItemView.DragOnly)
        self.setAcceptDrops(accept_drops)
        self.setDropIndicatorShown(accept_drops)

    def names(self) -> list[str]:
        return [self.item(i).text() for i in range(self.count())]

    def set_names(self, names: Iterable[str], icon_for: Optional[Callable[[str], QIcon]] = None) -> None:
        self.clear()
        for name in names:
            item = QListWidgetItem(name)
            if icon_for is not None:
                item.setIcon(icon_for(name))
            self.addItem(item)

    def selected_names(self) -> list[str]:
        return [item.text() for item in self.selectedItems()]

    def mimeTypes(self) -> list[str]:
        return [SIGNAL_MIME]

    def mimeData(self, items) -> QMimeData:
        return signal_names_mime([item.text() for item in items])

    def _accepts(self, event) -> bool:
        if not signal_names_from_mime(event.mimeData()):
            return False
        return self.drop_sources is None or event.source() in self.drop_sources

    def dragEnterEvent(self, event) -> None:
        if self._accepts(event):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._accepts(event):
            super().dragMoveEvent(event)  # draws the drop indicator
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    # copy action so the source list never removes its own rows, the owner rebuilds instead
    def dropEvent(self, event) -> None:
        if not self._accepts(event):
            event.ignore()
            return
        row = self._drop_row(event.position().toPoint())
        event.setDropAction(Qt.CopyAction)
        event.accept()
        self.names_dropped.emit(signal_names_from_mime(event.mimeData()), row, event.source())

    # the row a drop lands before, count() for the end of the list
    def _drop_row(self, pos: QPoint) -> int:
        index = self.indexAt(pos)
        if not index.isValid():
            return self.count()
        rect = self.visualRect(index)
        return index.row() + (1 if pos.y() > rect.center().y() else 0)

    # hint text while the list is empty
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.count() == 0 and self.placeholder:
            painter = QPainter(self.viewport())
            color = QColor(self.palette().color(self.foregroundRole()))
            color.setAlphaF(0.55)
            painter.setPen(color)
            rect = self.viewport().rect().adjusted(12, 12, -12, -12)
            painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, self.placeholder)
            painter.end()


# -- cards and rows --

# rounded panel for related controls, optional icon, title and description
class Card(QFrame):
    def __init__(self, title: Optional[str] = None, description: Optional[str] = None,
                 icon_name: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 14)
        self.body.setSpacing(10)
        if title:
            header = QHBoxLayout()
            header.setSpacing(10)
            if icon_name:
                ico = QLabel()
                ico.setPixmap(icon(icon_name).pixmap(20, 20))
                header.addWidget(ico, alignment=Qt.AlignTop)
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            text_col.addWidget(label(title, "section"))
            if description:
                text_col.addWidget(label(description, "muted", wrap=True))
            header.addLayout(text_col, stretch=1)
            self.header_layout = header  # callers can add buttons to the title row
            self.body.addLayout(header)

    def add(self, widget_or_layout, stretch: int = 0):
        if isinstance(widget_or_layout, QWidget):
            self.body.addWidget(widget_or_layout, stretch)
        else:
            self.body.addLayout(widget_or_layout, stretch)
        return widget_or_layout


# title and description on the left, controls on the right
class SettingRow(QWidget):
    def __init__(self, title: str, description: str = "", controls: Iterable[QWidget] = (),
                 parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(12)
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.addWidget(label(title))
        if description:
            text_col.addWidget(label(description, "muted", wrap=True))
        row.addLayout(text_col, stretch=1)
        for control in controls:
            row.addWidget(control, alignment=Qt.AlignVCenter)


# caption over a big number, used for max/min/avg
class StatTile(QFrame):
    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)
        self.caption = label(caption, "statLabel")
        self.value = label("—", "stat")
        layout.addWidget(self.caption)
        layout.addWidget(self.value)

    def set_value(self, text: str) -> None:
        self.value.setText(text)


# -- page chrome --

# page title and subtitle on the left, page actions on the right
class PageHeader(QFrame):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("headerBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 14, 20, 12)
        layout.setSpacing(8)
        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        self.title = label(title, "title")
        text_col.addWidget(self.title)
        self.subtitle = label(subtitle, "subtitle")
        self.subtitle.setVisible(bool(subtitle))
        text_col.addWidget(self.subtitle)
        layout.addLayout(text_col, stretch=1)
        self.actions_layout = QHBoxLayout()
        self.actions_layout.setSpacing(6)
        layout.addLayout(self.actions_layout)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))

    def add_action_widget(self, widget: QWidget) -> QWidget:
        self.actions_layout.addWidget(widget)
        return widget


# task manager style left nav, the hamburger collapses it to icons, bottom pins a page low
class NavRail(QFrame):
    page_selected = Signal(str)

    EXPANDED_WIDTH = 200
    COLLAPSED_WIDTH = 52

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navRail")
        self._buttons: dict[str, QToolButton] = {}
        self._labels: dict[str, str] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._expanded = True

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 8, 6, 8)
        self._layout.setSpacing(2)

        self.toggle_btn = QToolButton()
        self.toggle_btn.setIcon(icon("menu"))
        self.toggle_btn.setIconSize(QSize(18, 18))
        self.toggle_btn.setToolTip("Collapse navigation")
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle_expanded)
        self._layout.addWidget(self.toggle_btn, alignment=Qt.AlignLeft)
        self._layout.addSpacing(6)

        # top pages, stretch, pinned bottom pages
        self._top = QVBoxLayout()
        self._top.setSpacing(2)
        self._layout.addLayout(self._top)
        self._layout.addStretch(1)
        self._bottom = QVBoxLayout()
        self._bottom.setSpacing(2)
        self._layout.addLayout(self._bottom)

        self.setFixedWidth(self.EXPANDED_WIDTH)

    def add_page(self, key: str, text: str, icon_name: str, bottom: bool = False) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(icon(icon_name))
        btn.setIconSize(QSize(18, 18))
        btn.setCheckable(True)
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(text)
        btn.clicked.connect(lambda: self.page_selected.emit(key))
        self._group.addButton(btn)
        self._buttons[key] = btn
        self._labels[key] = text
        self._apply_label(key)
        (self._bottom if bottom else self._top).addWidget(btn)
        return btn

    def button(self, key: str) -> QToolButton:
        return self._buttons[key]

    def set_page_visible(self, key: str, visible: bool) -> None:
        self._buttons[key].setVisible(visible)

    def select(self, key: str) -> None:
        self._buttons[key].setChecked(True)

    def current(self) -> Optional[str]:
        return next((k for k, b in self._buttons.items() if b.isChecked()), None)

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.setFixedWidth(self.EXPANDED_WIDTH if expanded else self.COLLAPSED_WIDTH)
        self.toggle_btn.setToolTip("Collapse navigation" if expanded else "Expand navigation")
        for key in self._buttons:
            self._apply_label(key)

    def toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)

    # text beside the icon when expanded, icon only when collapsed
    def _apply_label(self, key: str) -> None:
        btn = self._buttons[key]
        if self._expanded:
            btn.setText(f"  {self._labels[key]}")
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        else:
            btn.setText("")
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)


# centered icon, message and buttons for a page with nothing in it yet
class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, message: str,
                 actions: Iterable[QWidget] = (), parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        ico = QLabel()
        ico.setPixmap(icon(icon_name).pixmap(56, 56))
        ico.setAlignment(Qt.AlignCenter)
        outer.addWidget(ico)
        t = label(title, "title")
        t.setAlignment(Qt.AlignCenter)
        outer.addWidget(t)
        m = label(message, "muted", wrap=True)
        m.setAlignment(Qt.AlignCenter)
        m.setFixedWidth(460)
        outer.addWidget(m, alignment=Qt.AlignHCenter)
        row = QHBoxLayout()
        row.addStretch(1)
        for a in actions:
            row.addWidget(a)
        row.addStretch(1)
        outer.addSpacing(8)
        outer.addLayout(row)
        outer.addStretch(2)


# repaints everything, used after a theme change
def refresh_all_widgets() -> None:
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        w.update()
