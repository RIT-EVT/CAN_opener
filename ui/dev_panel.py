#--------------------#
# dev_panel.py
# developer options: github token and repo, content managers, git, password, app folders
# see docs/ARCHITECTURE.md, developer options
#--------------------#
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QFileSystemModel, QHBoxLayout, QLineEdit, QMessageBox,
    QTextEdit, QTreeView, QVBoxLayout, QWidget,
)

from core.config_loader import (
    AppSettings, github_remote_url, normalize_github_repo, set_dev_password, set_updater_repo,
)
from ui.help_manager import HelpContentManagerDialog
from ui.platform_manager import PlatformManagerDialog
from ui.widgets import Card, SettingRow, button, label
from utils.keyring_bridge import KeyringUnavailableError, get_github_token, set_github_token

try:
    from git import GitCommandError, InvalidGitRepositoryError, Repo
except ImportError:  # gitpython not installed
    Repo = None
    InvalidGitRepositoryError = GitCommandError = Exception


# yes/no prompt that defaults to no
def _confirm(parent: QWidget, title: str, text: str) -> bool:
    return QMessageBox.question(
        parent, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
    ) == QMessageBox.Yes


# -- locked row --
# editors stay disabled until edit is clicked
# on_save returns true to re-lock or false to stay editing, cancel restores the saved value

class _LockableRow(QWidget):
    def __init__(self, title: str, description: str, editors: list[QWidget],
                 on_save, on_cancel, parent=None):
        super().__init__(parent)
        self._editors = editors
        self._on_save = on_save
        self._on_cancel = on_cancel
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(6)
        head = QHBoxLayout()
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.addWidget(label(title))
        text_col.addWidget(label(description, "muted", wrap=True))
        head.addLayout(text_col, stretch=1)
        self.lock_icon = label("", "muted")
        head.addWidget(self.lock_icon, alignment=Qt.AlignVCenter)
        outer.addLayout(head)

        # editors then edit, or save and cancel while editing
        row = QHBoxLayout()
        for editor in editors:
            row.addWidget(editor, stretch=1 if isinstance(editor, QLineEdit) else 0)
        self.edit_btn = button("Edit", icon_name="edit", tooltip="Unlock this field to change it")
        self.save_btn = button("Save", variant="primary", icon_name="save")
        self.cancel_btn = button("Cancel")
        self.edit_btn.clicked.connect(lambda: self.set_locked(False))
        self.save_btn.clicked.connect(self.save)
        self.cancel_btn.clicked.connect(self.cancel)
        for btn in (self.edit_btn, self.save_btn, self.cancel_btn):
            row.addWidget(btn)
        outer.addLayout(row)
        self.set_locked(True)

    def is_locked(self) -> bool:
        return not self._editors[0].isEnabled()

    def set_locked(self, locked: bool) -> None:
        for editor in self._editors:
            editor.setEnabled(not locked)
        self.lock_icon.setText("\U0001F512 Locked" if locked else "Editing")
        self.edit_btn.setVisible(locked)
        self.save_btn.setVisible(not locked)
        self.cancel_btn.setVisible(not locked)

    def save(self) -> None:
        if self._on_save():
            self.set_locked(True)

    def cancel(self) -> None:
        self._on_cancel()
        self.set_locked(True)


# -- developer panel --

class DevPanel(QWidget):
    def __init__(self, app_root: Path, settings: AppSettings, settings_path: Path, parent=None):
        super().__init__(parent)
        self.app_root = app_root
        self.settings = settings
        self.settings_path = settings_path

        # git checkout of the app itself, missing for installed builds
        self.repo = None
        if Repo is not None:
            try:
                self.repo = Repo(app_root)
            except InvalidGitRepositoryError:
                self.repo = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # cards: github, content, source control, security, app folders
        github = Card("GitHub", "Where updates are downloaded from and where Pull/Push go. "
                      "Both fields are locked -- click Edit to change them.", icon_name="code")
        github.add(self._github_token_section())
        github.add(self._repo_section())
        layout.addWidget(github)

        content = Card("Content", "Vehicle platforms, DBC files and in-app help text.",
                       icon_name="car")
        content.add(self._platform_manager_section())
        layout.addWidget(content)

        layout.addWidget(self._git_controls_section())

        security = Card("Security", icon_name="shield")
        security.add(self._dev_password_section())
        layout.addWidget(security)

        folders = Card("App folders", "Browse the platforms, themes, DBC store and log cache.",
                       icon_name="folder")
        folders.add(self._directory_panel())
        layout.addWidget(folders)

    # -- github token --
    # locked behind edit, replacing a saved token asks first

    def _github_token_section(self) -> QWidget:
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.Password)
        self._reset_token_input()
        self.token_row = _LockableRow(
            "Access token", "Personal access token, kept in the OS keychain.",
            [self.token_input],
            on_save=self._save_token, on_cancel=self._reset_token_input,
        )
        return self.token_row

    def _reset_token_input(self) -> None:
        self.token_input.setText(get_github_token() or "")

    # blank is refused, same token is a no-op
    def _save_token(self) -> bool:
        new_token = self.token_input.text().strip()
        if not new_token:
            QMessageBox.warning(self, "No token", "Enter a token, or click Cancel to keep the current one.")
            return False
        existing = get_github_token()
        if new_token == existing:
            return True
        if existing and not _confirm(
            self, "Replace GitHub token?",
            "This overwrites the token currently stored in the OS keychain. Continue?",
        ):
            return False
        try:
            set_github_token(new_token)
        except KeyringUnavailableError as exc:
            QMessageBox.critical(self, "Keychain unavailable", str(exc))
            return False
        QMessageBox.information(self, "Saved", "GitHub token stored in the OS keychain.")
        return True

    # -- github repo --
    # updater.repo drives both the updater and the git origin remote

    def _repo_section(self) -> QWidget:
        self.repo_input = QLineEdit()
        self.repo_input.setPlaceholderText("owner/name or https://github.com/owner/name")
        self.test_mode_checkbox = QCheckBox("Test mode (local feed)")
        self.test_mode_checkbox.setToolTip(
            "When checked, the updater reads the local mock feed and ignores the repo. "
            "Git Pull/Push still use the repo."
        )
        self._reset_repo_inputs()
        self.repo_row = _LockableRow(
            "Repository", "Paste owner/name or any GitHub link to the repo.",
            [self.repo_input, self.test_mode_checkbox],
            on_save=self._save_repo, on_cancel=self._reset_repo_inputs,
        )
        return self.repo_row

    def _reset_repo_inputs(self) -> None:
        self.repo_input.setText(self.settings.updater.repo)
        self.test_mode_checkbox.setChecked(self.settings.updater.test_mode)

    # validates, shows old and new values for confirmation, then saves and syncs git
    def _save_repo(self) -> bool:
        raw = self.repo_input.text()
        try:
            new_repo = normalize_github_repo(raw) if raw.strip() else ""
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid repo", str(exc))
            return False
        new_test_mode = self.test_mode_checkbox.isChecked()
        old_repo, old_test_mode = self.settings.updater.repo, self.settings.updater.test_mode
        if new_repo == old_repo and new_test_mode == old_test_mode:
            self._reset_repo_inputs()
            return True

        changes = []
        if new_repo != old_repo:
            changes.append(f"Repo: {old_repo or '(none)'}  ->  {new_repo or '(none)'}")
            if self.repo is not None and new_repo:
                changes.append(f"The git 'origin' remote will also point to {github_remote_url(new_repo)}")
        if new_test_mode != old_test_mode:
            changes.append(
                f"Test mode: {'on' if old_test_mode else 'off'}  ->  {'on' if new_test_mode else 'off'}"
            )
        if not _confirm(self, "Change GitHub repo?", "\n".join(changes) + "\n\nContinue?"):
            return False

        set_updater_repo(self.settings_path, self.settings, new_repo, test_mode=new_test_mode)
        self._reset_repo_inputs()
        try:
            self._sync_git_remote()
        except Exception as exc:
            QMessageBox.warning(self, "Git remote not updated",
                                f"Saved the repo, but couldn't update the git remote:\n{exc}")
        self._refresh_git_status()
        QMessageBox.information(
            self, "Saved",
            f"GitHub repo set to '{self.settings.updater.repo or '(none)'}'. "
            "The updater picks it up on next launch; Pull/Push use it right away.",
        )
        return True

    # points origin at the configured repo (creates it if missing), an ssh url to the same repo is kept
    def _sync_git_remote(self) -> None:
        repo_name = self.settings.updater.repo
        if self.repo is None or not repo_name:
            return
        url = github_remote_url(repo_name)
        try:
            origin = self.repo.remote("origin")
        except ValueError:
            self.repo.create_remote("origin", url)
            return
        try:
            if normalize_github_repo(origin.url).lower() == repo_name.lower():
                return
        except ValueError:
            pass  # origin isn't a github url, repoint it
        origin.set_url(url)

    # -- developer password --

    def _dev_password_section(self) -> QWidget:
        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.Password)
        self.new_password_input.setPlaceholderText("New password")
        self.new_password_input.setMinimumWidth(200)
        self.new_password_input.returnPressed.connect(self._change_password)
        change_btn = button("Change password", on_click=self._change_password)
        return SettingRow(
            "Developer password", "Required to open these developer options.",
            [self.new_password_input, change_btn],
        )

    def _change_password(self) -> None:
        new_password = self.new_password_input.text().strip()
        if not new_password:
            return
        set_dev_password(self.settings_path, self.settings, new_password)
        self.new_password_input.clear()
        QMessageBox.information(self, "Password changed", "Developer Mode password updated.")

    # -- content managers (platforms and help) --

    def _platform_manager_section(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(SettingRow(
            "Platforms", "Create or edit vehicle platforms and import .dbc files.",
            [button("Manage platforms…", icon_name="car", on_click=self._open_platform_manager)],
        ))
        layout.addWidget(SettingRow(
            "Help content", "Edit the text shown by the ? buttons and the Help page.",
            [button("Manage help…", icon_name="help", on_click=self._open_help_manager)],
        ))
        return box

    def _open_platform_manager(self) -> None:
        PlatformManagerDialog(self.app_root, self).exec()

    def _open_help_manager(self) -> None:
        HelpContentManagerDialog(self.app_root, self).exec()

    # -- source control --

    # pull, commit all, push, refresh, then a status box
    def _git_controls_section(self) -> QWidget:
        card = Card("Source control", "Status of this app's own git checkout.", icon_name="sync")
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        for text, icon_name, handler, tip in (
            ("Pull", "download", self._pull, "Get the latest changes from the GitHub repo"),
            ("Commit all", "save", self._commit, "Commit every local change"),
            ("Push", "upload", self._push, "Send commits to the GitHub repo"),
        ):
            buttons.addWidget(button(text, icon_name=icon_name, tooltip=tip, on_click=handler))
        buttons.addStretch(1)
        buttons.addWidget(button("", variant="subtle", icon_name="refresh",
                                 tooltip="Refresh status", on_click=self._refresh_git_status))
        card.add(buttons)

        self.git_status = QTextEdit()
        self.git_status.setReadOnly(True)
        self.git_status.setMinimumHeight(110)
        self.git_status.setMaximumHeight(160)
        mono = QFont("Cascadia Mono")
        mono.setStyleHint(QFont.Monospace)
        self.git_status.setFont(mono)
        self._refresh_git_status()
        card.add(self.git_status)
        return card

    def _refresh_git_status(self) -> None:
        if self.repo is not None:
            try:
                remote = f"Remote: {self.repo.remote('origin').url}"
            except ValueError:
                remote = "Remote: (no origin -- set a GitHub repo above)"
            self.git_status.setText(f"{remote}\n\n{self.repo.git.status()}")
        else:
            self.git_status.setText("Not running from a git checkout (or GitPython unavailable).")

    def _pull(self) -> None:
        self._run_remote_op("Pull", lambda origin: origin.pull())

    def _commit(self) -> None:
        if self.repo:
            self.repo.git.add(A=True)
            self.repo.index.commit("Manual commit from CAN Decoder App Developer Mode")
            self._refresh_git_status()

    def _push(self) -> None:
        self._run_remote_op("Push", lambda origin: origin.push())

    # re-syncs origin first so pull and push always hit the configured repo
    def _run_remote_op(self, name: str, op) -> None:
        if self.repo is None:
            return
        try:
            self._sync_git_remote()
            op(self.repo.remote("origin"))
        except (GitCommandError, ValueError) as exc:
            QMessageBox.critical(self, f"{name} failed", str(exc))
        self._refresh_git_status()

    # -- app folders --

    # read-only file tree of the data root
    def _directory_panel(self) -> QWidget:
        tree = QTreeView()
        model = QFileSystemModel(tree)
        model.setRootPath(str(self.app_root))
        tree.setModel(model)
        tree.setRootIndex(model.index(str(self.app_root)))
        tree.setMinimumHeight(240)
        tree.setColumnWidth(0, 260)
        tree.setAlternatingRowColors(True)
        return tree
