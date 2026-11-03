#--------------------#
# test_help_viewer.py
# tests for the ? help button and help popup
#--------------------#
import pytest

from core.help_content import save_help_text

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from ui.help_viewer import HelpViewerDialog, make_help_button  # noqa: E402

_qt_app = QApplication.instance() or QApplication([])


# regression, global button padding used to clip the ? glyph
def test_help_button_has_no_clipped_glyph_styling(tmp_path):
    parent = QWidget()
    btn = make_help_button(tmp_path, "some_topic", "Some Topic", parent)

    assert btn.objectName() == "helpButton"
    assert btn.text() == "?"
    assert "padding: 0px" in btn.styleSheet()
    assert btn.width() <= 24 and btn.height() <= 24


def test_clicking_help_button_shows_the_actual_saved_content(tmp_path, monkeypatch):
    help_dir = tmp_path / "help"
    save_help_text(help_dir, "some_topic", "# A Real Heading\n\nSome body text.")

    opened = {}

    def fake_exec(self):
        opened["dialog"] = self
        return 0

    monkeypatch.setattr(HelpViewerDialog, "exec", fake_exec)

    parent = QWidget()
    btn = make_help_button(help_dir, "some_topic", "Some Topic", parent)
    btn.click()

    assert "dialog" in opened
    assert opened["dialog"].windowTitle() == "Some Topic"
    assert "A Real Heading" in opened["dialog"].browser.toPlainText()


def test_help_viewer_renders_markdown_not_raw_source():
    dlg = HelpViewerDialog("Title", "**bold text**")
    # rendered text has no markdown asterisks
    assert "bold text" in dlg.browser.toPlainText()
    assert "**" not in dlg.browser.toPlainText()
