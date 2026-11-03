#--------------------#
# test_dev_panel.py
# tests for the developer panel: password, managers, locked github fields, git remote sync
#--------------------#
import pytest

from core.config_loader import (
    DEFAULT_DEV_PASSWORD, ensure_default_settings, load_app_settings, verify_dev_password,
)

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.dev_panel import DevPanel  # noqa: E402
from ui.help_manager import HelpContentManagerDialog  # noqa: E402
from ui.platform_manager import PlatformManagerDialog  # noqa: E402

_qt_app = QApplication.instance() or QApplication([])


def test_change_password_from_dev_panel_persists_and_takes_effect(tmp_path, monkeypatch):
    import PySide6.QtWidgets as qtw
    # the success popup is modal and would block the test
    monkeypatch.setattr(qtw.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    settings_path = tmp_path / "settings.yaml"
    ensure_default_settings(settings_path)
    settings = load_app_settings(settings_path)
    assert verify_dev_password(settings, DEFAULT_DEV_PASSWORD)

    panel = DevPanel(tmp_path, settings, settings_path)
    panel.new_password_input.setText("my-new-team-password")
    panel._change_password()

    # reload from disk, like after a restart
    reloaded = load_app_settings(settings_path)
    assert verify_dev_password(reloaded, "my-new-team-password")
    assert not verify_dev_password(reloaded, DEFAULT_DEV_PASSWORD)


def test_manage_help_content_button_opens_the_right_dialog(tmp_path):
    settings_path = tmp_path / "settings.yaml"
    ensure_default_settings(settings_path)
    settings = load_app_settings(settings_path)
    panel = DevPanel(tmp_path, settings, settings_path)

    opened = {}
    orig_exec = HelpContentManagerDialog.exec

    def fake_exec(self):
        opened["dialog"] = self
        return 0

    HelpContentManagerDialog.exec = fake_exec
    try:
        panel._open_help_manager()
    finally:
        HelpContentManagerDialog.exec = orig_exec

    assert "dialog" in opened
    assert opened["dialog"].help_dir == tmp_path / "config" / "help"


def test_manage_platforms_button_opens_the_right_dialog(tmp_path):
    settings_path = tmp_path / "settings.yaml"
    ensure_default_settings(settings_path)
    settings = load_app_settings(settings_path)
    panel = DevPanel(tmp_path, settings, settings_path)

    opened = {}
    orig_exec = PlatformManagerDialog.exec

    def fake_exec(self):
        opened["dialog"] = self
        return 0

    PlatformManagerDialog.exec = fake_exec
    try:
        panel._open_platform_manager()
    finally:
        PlatformManagerDialog.exec = orig_exec

    assert "dialog" in opened
    assert opened["dialog"].app_root == tmp_path


# -- github repo and token locking --

# stubs every modal popup, state["yes"] answers confirmations
@pytest.fixture
def dialogs(monkeypatch):
    import PySide6.QtWidgets as qtw
    state = {"yes": True, "questions": [], "warnings": [], "errors": []}
    monkeypatch.setattr(qtw.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(qtw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: state["warnings"].append(a)))
    monkeypatch.setattr(qtw.QMessageBox, "critical",
                        staticmethod(lambda *a, **k: state["errors"].append(a)))
    monkeypatch.setattr(
        qtw.QMessageBox, "question",
        staticmethod(lambda *a, **k: (state["questions"].append(a),
                                      qtw.QMessageBox.Yes if state["yes"] else qtw.QMessageBox.No)[1]),
    )
    return state


@pytest.fixture
def fake_keyring(monkeypatch):
    store = {"token": None}
    import ui.dev_panel as dp
    monkeypatch.setattr(dp, "get_github_token", lambda: store["token"])
    monkeypatch.setattr(dp, "set_github_token", lambda t: store.__setitem__("token", t))
    return store


def _panel(tmp_path):
    settings_path = tmp_path / "settings.yaml"
    ensure_default_settings(settings_path)
    return DevPanel(tmp_path, load_app_settings(settings_path), settings_path), settings_path


def test_repo_and_token_rows_start_locked(tmp_path, fake_keyring):
    panel, _ = _panel(tmp_path)
    assert panel.repo_row.is_locked()
    assert panel.token_row.is_locked()
    assert not panel.repo_input.isEnabled()
    assert not panel.test_mode_checkbox.isEnabled()
    assert not panel.token_input.isEnabled()


def test_save_repo_after_confirming_persists_and_relocks(tmp_path, dialogs, fake_keyring):
    panel, settings_path = _panel(tmp_path)
    panel.repo_row.edit_btn.click()
    assert not panel.repo_row.is_locked()

    panel.repo_input.setText("https://github.com/someone/other_repo")
    panel.test_mode_checkbox.setChecked(False)
    panel.repo_row.save_btn.click()

    assert dialogs["questions"], "should have asked for confirmation"
    assert panel.repo_row.is_locked()
    assert panel.repo_input.text() == "someone/other_repo"
    reloaded = load_app_settings(settings_path)
    assert reloaded.updater.repo == "someone/other_repo"
    assert reloaded.updater.test_mode is False


def test_declining_repo_confirmation_saves_nothing(tmp_path, dialogs, fake_keyring):
    panel, settings_path = _panel(tmp_path)
    dialogs["yes"] = False
    panel.repo_row.edit_btn.click()
    panel.repo_input.setText("someone/other_repo")
    panel.repo_row.save_btn.click()

    assert not panel.repo_row.is_locked()  # stays in edit mode
    assert load_app_settings(settings_path).updater.repo == ""


def test_cancel_restores_saved_repo(tmp_path, dialogs, fake_keyring):
    panel, settings_path = _panel(tmp_path)
    panel.repo_row.edit_btn.click()
    panel.repo_input.setText("someone/typo")
    panel.repo_row.cancel_btn.click()

    assert panel.repo_row.is_locked()
    assert panel.repo_input.text() == ""
    assert not dialogs["questions"]
    assert load_app_settings(settings_path).updater.repo == ""


def test_invalid_repo_is_rejected(tmp_path, dialogs, fake_keyring):
    panel, settings_path = _panel(tmp_path)
    panel.repo_row.edit_btn.click()
    panel.repo_input.setText("not a repo")
    panel.repo_row.save_btn.click()

    assert dialogs["warnings"]
    assert not panel.repo_row.is_locked()
    assert load_app_settings(settings_path).updater.repo == ""


def test_replacing_existing_token_requires_confirmation(tmp_path, dialogs, fake_keyring):
    fake_keyring["token"] = "old-token"
    panel, _ = _panel(tmp_path)
    assert panel.token_input.text() == "old-token"

    dialogs["yes"] = False
    panel.token_row.edit_btn.click()
    panel.token_input.setText("new-token")
    panel.token_row.save_btn.click()
    assert fake_keyring["token"] == "old-token"

    dialogs["yes"] = True
    panel.token_row.save_btn.click()
    assert fake_keyring["token"] == "new-token"
    assert panel.token_row.is_locked()


def test_blank_token_is_never_saved(tmp_path, dialogs, fake_keyring):
    fake_keyring["token"] = "old-token"
    panel, _ = _panel(tmp_path)
    panel.token_row.edit_btn.click()
    panel.token_input.clear()
    panel.token_row.save_btn.click()

    assert dialogs["warnings"]
    assert fake_keyring["token"] == "old-token"


# -- repo setting drives the git remote --

git = pytest.importorskip("git")


def test_saving_repo_repoints_git_origin(tmp_path, dialogs, fake_keyring):
    git.Repo.init(tmp_path).create_remote("origin", "https://github.com/old/place.git")
    panel, _ = _panel(tmp_path)

    panel.repo_row.edit_btn.click()
    panel.repo_input.setText("someone/other_repo")
    panel.repo_row.save_btn.click()

    assert git.Repo(tmp_path).remote("origin").url == "https://github.com/someone/other_repo.git"
    assert "someone/other_repo" in panel.git_status.toPlainText()


def test_saving_repo_creates_origin_if_missing(tmp_path, dialogs, fake_keyring):
    git.Repo.init(tmp_path)
    panel, _ = _panel(tmp_path)

    panel.repo_row.edit_btn.click()
    panel.repo_input.setText("someone/other_repo")
    panel.repo_row.save_btn.click()

    assert git.Repo(tmp_path).remote("origin").url == "https://github.com/someone/other_repo.git"


def test_equivalent_ssh_origin_is_left_alone(tmp_path, dialogs, fake_keyring):
    git.Repo.init(tmp_path).create_remote("origin", "git@github.com:someone/other_repo.git")
    panel, _ = _panel(tmp_path)

    panel.repo_row.edit_btn.click()
    panel.repo_input.setText("someone/other_repo")
    panel.repo_row.save_btn.click()

    assert git.Repo(tmp_path).remote("origin").url == "git@github.com:someone/other_repo.git"


def test_push_resyncs_hand_edited_origin_first(tmp_path, dialogs, fake_keyring):
    git.Repo.init(tmp_path).create_remote("origin", "https://github.com/old/place.git")
    panel, settings_path = _panel(tmp_path)
    panel.repo_row.edit_btn.click()
    panel.repo_input.setText("someone/other_repo")
    panel.repo_row.save_btn.click()

    # someone hand-edits .git/config behind the app's back
    git.Repo(tmp_path).remote("origin").set_url("https://github.com/elsewhere/oops.git")

    pushed_to = []
    panel._run_remote_op("Push", lambda origin: pushed_to.append(origin.url))
    assert pushed_to == ["https://github.com/someone/other_repo.git"]

