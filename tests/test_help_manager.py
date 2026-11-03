#--------------------#
# test_help_manager.py
# tests for the help content editor dialog
#--------------------#
from pathlib import Path

import pytest

from core.help_content import load_help_text

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from ui.help_manager import HelpContentManagerDialog  # noqa: E402

_qt_app = QApplication.instance() or QApplication([])


def _make_app_root(tmp_path: Path) -> Path:
    defaults_dir = tmp_path / "config" / "defaults" / "help"
    defaults_dir.mkdir(parents=True)
    (defaults_dir / "important_values.md").write_text("# Important Values\n\nOriginal text.")
    return tmp_path


def test_selecting_topic_loads_its_content_into_editor(tmp_path):
    app_root = _make_app_root(tmp_path)
    dlg = HelpContentManagerDialog(app_root)

    assert dlg.key_list.count() >= 1
    item = dlg.key_list.item(0)
    dlg._on_select_key(item)

    assert "Original text." in dlg.editor.toPlainText()
    assert "Original text." in dlg.preview.toPlainText()


def test_editing_and_saving_persists_to_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    app_root = _make_app_root(tmp_path)
    help_dir = app_root / "config" / "help"

    dlg = HelpContentManagerDialog(app_root)
    item = dlg.key_list.item(0)
    dlg._on_select_key(item)
    dlg.editor.setPlainText("# Important Values\n\nA developer rewrote this.")
    dlg._on_save()

    assert "A developer rewrote this." in load_help_text(help_dir, "important_values")

    # reopening shows the saved edit, not the default
    dlg2 = HelpContentManagerDialog(app_root)
    dlg2._on_select_key(dlg2.key_list.item(0))
    assert "A developer rewrote this." in dlg2.editor.toPlainText()


def test_save_without_selecting_a_topic_warns_instead_of_crashing(tmp_path, monkeypatch):
    warning_calls = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warning_calls.append(a)))
    app_root = _make_app_root(tmp_path)

    dlg = HelpContentManagerDialog(app_root)
    dlg._on_save()  # nothing selected yet

    assert warning_calls
