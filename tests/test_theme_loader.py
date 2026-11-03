#--------------------#
# test_theme_loader.py
# tests for theme loading, bootstrapping and the stylesheet
#--------------------#
from pathlib import Path

from core.config_loader import load_theme_config
from core.theme_loader import bootstrap_user_themes, build_stylesheet, next_palette_color

APP_ROOT = Path(__file__).resolve().parents[1]


def test_build_stylesheet_contains_colors():
    theme = load_theme_config(APP_ROOT / "config" / "defaults" / "dark_theme.yaml")
    qss = build_stylesheet(theme)
    assert theme.colors.background in qss
    assert theme.colors.accent in qss


def test_bootstrap_user_themes_copies_defaults(tmp_path):
    themes_dir = tmp_path / "themes"
    defaults_dir = APP_ROOT / "config" / "defaults"
    bootstrap_user_themes(themes_dir, defaults_dir)
    assert (themes_dir / "dark.yaml").exists()
    assert (themes_dir / "light.yaml").exists()


def test_bootstrap_never_overwrites_user_edit(tmp_path):
    themes_dir = tmp_path / "themes"
    defaults_dir = APP_ROOT / "config" / "defaults"
    bootstrap_user_themes(themes_dir, defaults_dir)
    (themes_dir / "dark.yaml").write_text("name: dark-but-edited\n")
    bootstrap_user_themes(themes_dir, defaults_dir)  # simulate a second run
    assert (themes_dir / "dark.yaml").read_text() == "name: dark-but-edited\n"


def test_next_palette_color_cycles():
    theme = load_theme_config(APP_ROOT / "config" / "defaults" / "dark_theme.yaml")
    n = len(theme.colors.plot_palette)
    assert next_palette_color(theme, 0) == theme.colors.plot_palette[0]
    assert next_palette_color(theme, n) == theme.colors.plot_palette[0]
