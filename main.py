#--------------------#
#
#     ___   _   _  _     ___                  _
#    / __| /_\ | \| |   |   \ ___ __ ___  __| |___ _ _
#   | (__ / _ \| .` |   | |) / -_) _/ _ \/ _` / -_) '_|
#    \___/_/ \_\_|\_|   |___/\___\__\___/\__,_\___|_|
#
#    _   _   _   _   _   _   _   _   _   _   _   _   _
#  _| |_| |_| |_| |_| |_| |_| |_| |_| |_| |_| |_| |_| |_
#
# main.py
# entry point for the can decoder app
#
# opens mf4 can bus logs, decodes them against a vehicle's dbc file and
# plots the signals that matter, with pdf reports, themes, an advanced
# mode for digging into undecoded ids and a password-locked developer
# area for the github repo, platforms and help content
#
# normally started by launcher.py after its update check, run this file
# directly during development to skip that
#
# author   tdkennedy
# repo     github.com/tkenn0/can_decoder_app
# docs     docs/DEVELOPMENT.md, docs/ARCHITECTURE.md, docs/UI_GUIDE.md
#
#--------------------#
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.config_loader import load_app_settings
from core.help_content import bootstrap_default_help
from core.theme_loader import apply_theme, bootstrap_user_themes, load_active_theme
from ui.main_window import MainWindow
from utils.file_utils import ensure_directories


# -- code root vs data root (see docs/ARCHITECTURE.md, data root) --

# where this copy of the code lives, versions/<tag>/ when installed
def _code_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# bundled defaults, frozen onedir builds keep them under _internal (sys._MEIPASS)
def _bundled_defaults_dir(code_root: Path) -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass) / "config" / "defaults"
    return code_root / "config" / "defaults"


# stable user data folder from the launcher, or the code root for dev runs
def resolve_data_root() -> Path:
    override = os.environ.get("CAN_DECODER_DATA_ROOT")
    if override:
        return Path(override)
    return _code_root()


CODE_ROOT = _code_root()
APP_ROOT = resolve_data_root()


# copies this version's bundled defaults into the data root
# skipped only when source and destination are the same folder (running from source)
# a frozen exe started directly, without the launcher, still needs the copy,
# because pyinstaller puts the defaults under _internal/, not next to the exe
def _sync_defaults(app_root: Path, code_root: Path) -> None:
    src = _bundled_defaults_dir(code_root)
    dst = app_root / "config" / "defaults"
    if not src.exists() or src.resolve() == dst.resolve():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)
# -- startup --


def run(app_root: Path = APP_ROOT, code_root: Path = CODE_ROOT) -> int:
    # folders, defaults and settings
    ensure_directories(app_root)
    _sync_defaults(app_root, code_root)

    settings = load_app_settings(app_root / "config" / "settings.yaml")

    # user-editable theme and help copies
    bootstrap_user_themes(app_root / "config" / "themes", app_root / "config" / "defaults")
    bootstrap_default_help(app_root / "config" / "help", app_root / "config" / "defaults" / "help")

    # qt app, theme and main window
    qt_app = QApplication(sys.argv)
    theme = load_active_theme(app_root, settings)
    if theme is not None:
        apply_theme(qt_app, theme)

    window = MainWindow(app_root, qt_app, settings, theme)
    window.show()
    return qt_app.exec()


# -- build self-test, run by packaging/build_release.py against the frozen exe --

# imports by string on purpose, so pyinstaller can't "see" them and the test stays honest
SELFTEST_MODULES = ["canmatrix.formats.dbc", "cantools.database", "asammdf"]
SELFTEST_DEFAULTS = ["dark_theme.yaml", "light_theme.yaml"]


# writes a report to report_path, returns 0 if everything is present
# (no print: the windowed exe has no console, so stdout doesn't exist)
def _selftest(report_path: str) -> int:
    import importlib

    failures = []
    for name in SELFTEST_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            failures.append(f"import {name} failed: {exc!r}")

    defaults_dir = _bundled_defaults_dir(CODE_ROOT)
    for name in SELFTEST_DEFAULTS:
        if not (defaults_dir / name).exists():
            failures.append(f"bundled default missing: {defaults_dir / name}")

    Path(report_path).write_text("\n".join(failures) or "OK", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        sys.exit(_selftest(sys.argv[2]))
    sys.exit(run())