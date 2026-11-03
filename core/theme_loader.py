#--------------------#
# theme_loader.py
# loads themes, derives extra shades and builds the app-wide qss stylesheet
#--------------------#
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from core.config_loader import AppSettings, ConfigLoadError, ThemeConfig, discover_themes, load_theme_config
from utils.file_utils import copy_default_if_missing

BASE_FONT_PT = 10
UI_FONT_FAMILY = '"Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", sans-serif'

# -- stylesheet --
# widgets opt in with setProperty: variant on buttons, role on labels, card on frames
# full list in docs/UI_GUIDE.md, conventions
QSS_TEMPLATE = """
* {{
    font-family: {font_family};
    font-size: {font_pt}pt;
    outline: none;
}}
/* only windows paint a background so nested rows show their card color */
QWidget {{ color: {text}; }}
QMainWindow, QDialog, QMessageBox {{ background-color: {background}; }}
QToolTip {{
    background-color: {surface}; color: {text};
    border: 1px solid {border}; border-radius: 4px; padding: 4px 8px;
}}

/* -- labels ---------------------------------------------------------- */
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: {title_pt}pt; font-weight: 600; }}
QLabel[role="subtitle"] {{ color: {muted}; }}
QLabel[role="section"] {{ font-size: {section_pt}pt; font-weight: 600; padding-top: 4px; }}
QLabel[role="muted"] {{ color: {muted}; }}
QLabel[role="stat"] {{ font-size: {stat_pt}pt; font-weight: 600; }}
QLabel[role="statLabel"] {{ color: {muted}; font-size: {small_pt}pt; }}
QLabel[role="error"] {{ color: {error}; }}

/* -- cards / frames -------------------------------------------------- */
QFrame[card="true"] {{
    background-color: {surface};
    border: 1px solid {border_soft};
    border-radius: 8px;
}}
QFrame[card="true"] QLabel, QFrame[card="true"] QCheckBox {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* -- navigation rail (Task Manager style) ----------------------------- */
QFrame#navRail {{ background-color: {rail}; border: none; }}
QFrame#navRail QToolButton {{
    background: transparent; border: none; border-radius: 6px;
    padding: 8px 10px; text-align: left; color: {text};
}}
QFrame#navRail QToolButton:hover {{ background-color: {hover}; }}
QFrame#navRail QToolButton:checked {{ background-color: {selected}; font-weight: 600; }}
QFrame#headerBar {{ background-color: {background}; border: none; border-bottom: 1px solid {border_soft}; }}

/* -- buttons --------------------------------------------------------- */
QPushButton, QToolButton {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 5px 14px;
    min-height: 20px;
}}
QPushButton:hover, QToolButton:hover {{ background-color: {hover}; }}
QPushButton:pressed, QToolButton:pressed {{ background-color: {pressed}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {disabled}; border-color: {border_soft}; }}
QPushButton:focus {{ border-color: {accent}; }}
QPushButton[variant="primary"], QToolButton[variant="primary"] {{
    background-color: {accent}; color: {on_accent}; border: 1px solid {accent};
}}
QPushButton[variant="primary"]:hover, QToolButton[variant="primary"]:hover {{
    background-color: {accent_hover}; border-color: {accent_hover};
}}
QPushButton[variant="primary"]:disabled, QToolButton[variant="primary"]:disabled {{
    background-color: {border_soft}; color: {disabled};
}}
QPushButton[variant="danger"] {{ color: {error}; }}
QPushButton[variant="danger"]:hover {{ border-color: {error}; }}
QPushButton[variant="subtle"], QToolButton[variant="subtle"] {{
    background: transparent; border: 1px solid transparent;
}}
QPushButton[variant="subtle"]:hover, QToolButton[variant="subtle"]:hover {{ background-color: {hover}; }}
/* toggle buttons, e.g. the plot cursors */
QPushButton:checked, QPushButton[variant="subtle"]:checked {{
    background-color: {selected}; border: 1px solid {accent}; font-weight: 600;
}}

/* -- inputs ---------------------------------------------------------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {input_bg};
    border: 1px solid {border};
    border-bottom: 1px solid {input_underline};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {accent};
    selection-color: {on_accent};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus {{
    border-bottom: 2px solid {accent};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {disabled}; background-color: {surface};
}}
QLineEdit[readOnly="true"] {{ background-color: {surface}; }}
QComboBox {{ padding-right: 28px; min-height: 20px; }}
QComboBox:hover {{ background-color: {hover}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 26px; border: none; background: transparent;
}}
QComboBox::down-arrow {{ image: {chevron_down}; width: 10px; height: 10px; }}
QComboBox::down-arrow:on {{ image: {chevron_up}; }}
QComboBox QAbstractItemView {{
    background-color: {surface}; border: 1px solid {border}; border-radius: 6px;
    padding: 4px; selection-background-color: {selected}; selection-color: {text};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    border: none; background: transparent; width: 18px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: {chevron_up}; width: 8px; height: 8px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: {chevron_down}; width: 8px; height: 8px; }}

QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 4px;
    border: 1px solid {input_underline}; background-color: {input_bg};
}}
QCheckBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background-color: {accent}; border-color: {accent}; image: {check}; }}
QCheckBox::indicator:disabled {{ border-color: {border_soft}; background-color: {surface}; }}
QCheckBox::indicator:checked:disabled {{ background-color: {border}; }}

/* -- lists / tables / trees ------------------------------------------ */
QListWidget, QListView, QTreeView, QTreeWidget, QTableView, QTableWidget {{
    background-color: {surface};
    alternate-background-color: {alt_row};
    border: 1px solid {border_soft};
    border-radius: 8px;
    padding: 2px;
}}
QListWidget::item, QListView::item {{ padding: 6px 8px; border-radius: 4px; }}
QListWidget::item:hover, QListView::item:hover,
QTreeView::item:hover, QTableView::item:hover {{ background-color: {hover}; }}
QListWidget::item:selected, QListView::item:selected, QTreeView::item:selected,
QTableView::item:selected {{
    background-color: {selected}; color: {text};
}}
QTableView {{ gridline-color: {border_soft}; }}
QTableView::item {{ padding: 4px 6px; }}
QHeaderView {{ background: transparent; border: none; }}
QHeaderView::section {{
    background-color: {surface}; color: {muted};
    border: none; border-bottom: 1px solid {border_soft};
    padding: 6px 8px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {surface}; border: none; }}

/* -- tabs (session tabs + inner tabs) -------------------------------- */
QTabWidget::pane {{ border: none; top: -1px; }}
QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent; color: {muted};
    padding: 8px 16px; margin-right: 2px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{ color: {text}; background-color: {hover}; border-top-left-radius: 6px; border-top-right-radius: 6px; }}
QTabBar::tab:selected {{ color: {text}; border-bottom: 2px solid {accent}; font-weight: 600; }}
QTabBar::close-button {{ image: {close}; subcontrol-position: right; margin-left: 4px; }}
QTabBar::close-button:hover {{ background-color: {pressed}; border-radius: 4px; }}

/* -- menus ----------------------------------------------------------- */
QMenuBar {{ background-color: {background}; border: none; padding: 2px 4px; }}
QMenuBar::item {{ background: transparent; padding: 5px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background-color: {hover}; }}
QMenuBar::item:pressed {{ background-color: {pressed}; }}
QMenu {{
    background-color: {surface}; border: 1px solid {border};
    border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 6px 28px 6px 12px; border-radius: 4px; background: transparent; }}
QMenu::item:selected {{ background-color: {hover}; }}
QMenu::item:disabled {{ color: {disabled}; }}
QMenu::separator {{ height: 1px; background: {border_soft}; margin: 4px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 6px; }}
QMenu::indicator:checked {{ image: {check_plain}; }}
QMenu::right-arrow {{ image: {chevron_right}; width: 10px; height: 10px; }}

/* -- splitters / scrollbars / status bar ----------------------------- */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background-color: {border_soft}; }}
QSplitter::handle:horizontal {{ width: 6px; }}
QSplitter::handle:vertical {{ height: 6px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background-color: {scroll}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background-color: {muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QStatusBar {{ background-color: {rail}; color: {muted}; border-top: 1px solid {border_soft}; }}
QStatusBar QLabel {{ color: {muted}; padding: 0 8px; }}
QStatusBar::item {{ border: none; }}
"""


# -- color helpers --

def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.strip().lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


# blends amount (0 to 1) of color b into color a
def mix(a: str, b: str, amount: float) -> str:
    ra, rb = _hex_to_rgb(a), _hex_to_rgb(b)
    return _rgb_to_hex(tuple(x + (y - x) * amount for x, y in zip(ra, rb)))


def _luminance(color: str) -> float:
    r, g, b = (c / 255 for c in _hex_to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# every color the stylesheet uses, computed from the few base colors in the theme file
def derived_colors(theme: ThemeConfig) -> dict[str, str]:
    c = theme.colors
    dark = _luminance(c.background) < 0.5
    return {
        "background": c.background,
        "surface": c.surface,
        "text": c.text,
        "accent": c.accent,
        "border": c.border,
        "error": c.error,
        "muted": mix(c.text, c.background, 0.40),
        "disabled": mix(c.text, c.background, 0.60),
        "border_soft": mix(c.border, c.background, 0.45),
        "hover": mix(c.surface, c.text, 0.07),
        "pressed": mix(c.surface, c.text, 0.12),
        "selected": mix(c.surface, c.accent, 0.22),
        "alt_row": mix(c.surface, c.text, 0.025),
        "rail": mix(c.background, c.text, 0.035) if dark else mix(c.background, "#000000", 0.025),
        "input_bg": mix(c.surface, c.text, 0.03) if dark else c.surface,
        "input_underline": mix(c.border, c.text, 0.35),
        "scroll": mix(c.border, c.background, 0.1),
        "accent_hover": mix(c.accent, c.text if dark else "#000000", 0.15),
        "on_accent": "#000000" if _luminance(c.accent) > 0.55 else "#ffffff",
    }


# -- glyph images (chevrons, checks, close) --
# qss can only reference image files, so these are drawn as small pngs per color
# see docs/ARCHITECTURE.md, theming

_GLYPH_DIR = Path(tempfile.gettempdir()) / "can_decoder_qss"


# returns a cached png path, or nothing when no qt app is running (plain tests)
def _render_glyph(kind: str, color: str, size: int = 32) -> Optional[str]:
    try:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPolygonF
    except ImportError:
        return None
    if QGuiApplication.instance() is None:
        return None
    _GLYPH_DIR.mkdir(parents=True, exist_ok=True)
    path = _GLYPH_DIR / f"{kind}_{color.lstrip('#')}.png"
    if path.exists():
        return path.as_posix()

    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), size * 0.11, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    s = size
    shapes = {
        "chevron_down": [(0.22, 0.38), (0.5, 0.66), (0.78, 0.38)],
        "chevron_up": [(0.22, 0.62), (0.5, 0.34), (0.78, 0.62)],
        "chevron_right": [(0.38, 0.22), (0.66, 0.5), (0.38, 0.78)],
        "check": [(0.22, 0.52), (0.42, 0.72), (0.80, 0.30)],
    }
    if kind == "close":
        painter.drawLine(QPointF(s * 0.3, s * 0.3), QPointF(s * 0.7, s * 0.7))
        painter.drawLine(QPointF(s * 0.7, s * 0.3), QPointF(s * 0.3, s * 0.7))
    else:
        painter.drawPolyline(QPolygonF([QPointF(x * s, y * s) for x, y in shapes[kind]]))
    painter.end()
    image.save(str(path))
    return path.as_posix()


def _glyph_urls(colors: dict[str, str]) -> dict[str, str]:
    specs = {
        "chevron_down": ("chevron_down", colors["muted"]),
        "chevron_up": ("chevron_up", colors["muted"]),
        "chevron_right": ("chevron_right", colors["muted"]),
        "check": ("check", colors["on_accent"]),
        "check_plain": ("check", colors["text"]),
        "close": ("close", colors["muted"]),
    }
    urls = {}
    for key, (kind, color) in specs.items():
        path = _render_glyph(kind, color)
        urls[key] = f'url("{path}")' if path else "none"
    return urls


# -- public api --

# first run only, gives the user editable copies of the built-in themes
def bootstrap_user_themes(themes_dir: Path, defaults_dir: Path) -> None:
    copy_default_if_missing(defaults_dir / "dark_theme.yaml", themes_dir / "dark.yaml")
    copy_default_if_missing(defaults_dir / "light_theme.yaml", themes_dir / "light.yaml")


def load_active_theme(app_root: Path, settings: AppSettings) -> ThemeConfig | None:
    themes_dir = app_root / "config" / "themes"
    path = themes_dir / f"{settings.active_theme}.yaml"
    if path.exists():
        try:
            return load_theme_config(path)
        except ConfigLoadError:
            pass
    # configured theme missing or broken, use the first one that loads
    for theme in discover_themes(themes_dir).values():
        if isinstance(theme, ThemeConfig):
            return theme
    return None


def build_stylesheet(theme: ThemeConfig) -> str:
    colors = derived_colors(theme)
    base = BASE_FONT_PT * theme.font_scale
    return QSS_TEMPLATE.format(
        font_family=UI_FONT_FAMILY,
        font_pt=round(base),
        small_pt=max(7, round(base * 0.85)),
        section_pt=round(base * 1.15),
        title_pt=round(base * 1.8),
        stat_pt=round(base * 1.5),
        **colors,
        **_glyph_urls(colors),
    )


def apply_theme(qt_app, theme: ThemeConfig) -> None:
    qt_app.setStyleSheet(build_stylesheet(theme))


# trace colors cycle through the theme's plot_palette
def next_palette_color(theme: ThemeConfig, used_count: int) -> str:
    palette = theme.colors.plot_palette or ["#1f77b4", "#ff7f0e", "#2ca02c"]
    return palette[used_count % len(palette)]
