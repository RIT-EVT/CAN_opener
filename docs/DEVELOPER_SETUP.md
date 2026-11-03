# Developer Setup: GitHub Distribution and Packaging

A guide to building, packaging and distributing the CAN Decoder App through GitHub Releases, including the self-update mechanism used by installed copies. It is written for someone doing this for the first time, so each section explains what the commands do and why, not only which commands to run.

## Contents

1. [Architecture](#1-architecture)
2. [Prerequisites](#2-prerequisites)
3. [Put the Code on GitHub](#3-put-the-code-on-github)
4. [Configure the Update Source](#4-configure-the-update-source)
5. [GitHub Personal Access Token](#5-github-personal-access-token)
6. [Build the Release Artifacts](#6-build-the-release-artifacts)
7. [Verify the Packaging Worked](#7-verify-the-packaging-worked)
8. [Publish a Release](#8-publish-a-release)
9. [Distribute the First Install](#9-distribute-the-first-install)
10. [Cutting Subsequent Releases](#10-cutting-subsequent-releases)
11. [Offline Testing (`test_mode`)](#11-offline-testing-test_mode)
12. [Automated Tests](#12-automated-tests)
13. [Troubleshooting](#13-troubleshooting)
14. [Resolved Issues Reference](#14-resolved-issues-reference)

---

## 1. Architecture

Three components look related but serve different purposes:

| Component | Built as | Purpose | Audience |
|---|---|---|---|
| `launcher.py` | `CANDecoderLauncher.exe` | Permanent entry point. Checks for updates, stages new versions, replaces itself when a release ships a newer launcher, and launches the current app. | End users |
| `main.py` | `CANDecoder-app.exe` | The application itself. Replaced as a whole on every update. | End users, through the launcher |
| `ui/dev_panel.py` (Source control card) | Part of the app | Pull, commit and push against a source checkout. | Developers editing the code |

### Update mechanism

The end-user update mechanism does **not** use git. A running frozen executable cannot overwrite its own files, so an update is applied by downloading the new version into its own folder and moving a "current version" pointer to it, never by patching files in place. See [`ARCHITECTURE.md` §15](ARCHITECTURE.md#15-auto-update) for the details.

### Install layout

This is what an end user's machine looks like once everything is set up, which is the end state this guide builds toward:

```
<install folder>/
├── CANDecoderLauncher.exe      Never changes; this is what users open
├── data/                       Stable across every update
│   ├── config/
│   │   ├── platforms/
│   │   ├── themes/
│   │   ├── help/
│   │   └── settings.yaml
│   ├── dbc_store/
│   └── logs_cache/
└── versions/
    ├── current.txt             Which version folder is active
    ├── v1.0.0/
    │   ├── CANDecoder-app.exe
    │   └── _internal/          PySide6, Qt, bundled config/defaults
    └── v1.1.0/
        ├── CANDecoder-app.exe
        └── _internal/
```

`data/` is never modified by an update, which is what allows a platform config or an imported DBC to survive across releases. Each release adds one `versions/<tag>/` folder.

---

## 2. Prerequisites

| Requirement | Notes |
|---|---|
| GitHub account | A free account is fine. |
| Git | See [§3](#3-put-the-code-on-github) if `git --version` does not work in a terminal. |
| Windows | Required for the packaging step ([§6](#6-build-the-release-artifacts) onward). PyInstaller builds a binary for the operating system it runs on, and the deployment target is Windows. Cloning, editing code and running the tests also work on macOS and Linux. |
| Python 3.11 or later | Confirm with `python --version`. If that fails, Python is not on your PATH: reinstall it from [python.org](https://www.python.org/downloads/) and check "Add python.exe to PATH" during installation. |
| GitHub Personal Access Token (optional) | Required only for a private release repository, or for pushing from Developer options. See [§5](#5-github-personal-access-token). |

Run these three checks in a terminal before starting. If any of them fails, fix it first, because nothing later will work otherwise.

```powershell
git --version
python --version
pip --version
```

---

## 3. Put the Code on GitHub

This section covers going from a project folder on your computer to a GitHub repository you can publish releases from. If you have done this before, skip to the commands in §3.4.

### 3.1 Install Git (if `git --version` failed)

1. Download Git from **https://git-scm.com/download/win**. The download starts automatically.
2. Run the installer. The defaults are fine on every screen; click **Next** through them.
3. **Close and reopen your terminal.** A terminal that was already open will not see the updated PATH.
4. Confirm that `git --version` now prints a version number.

### 3.2 Create the repository on GitHub

1. On [github.com](https://github.com), click **New repository**.
2. Give it a name, for example `can-decoder-app`.
3. **Visibility:** Private is a reasonable default for an internal team tool. Public also works; it only affects who can see the code, not how updates work.
4. **Do not** check "Add a README", "Add .gitignore" or "Add a license". The project already has these files, and letting GitHub create its own copies causes a conflict on the first push.
5. Click **Create repository**. GitHub shows a page of setup commands; you do not need them, because §3.4 covers the same steps.

### 3.3 Know what not to commit

Never commit `dist/`, `build/` or your virtual environment folder (`.venv/` or `venv/`). These hold generated output, not source code. `dist/` in particular contains the packaged application (hundreds of megabytes), and GitHub rejects any single file over 100 MB. The project's `.gitignore` already excludes these folders, along with personal editor settings (`.vscode/`); if you add another folder of generated output later, add it to `.gitignore` too.

If a push ever fails with `File ... exceeds GitHub's file size limit`, something that should be ignored was committed; see [§13](#13-troubleshooting).

### 3.4 Initialize, commit and push

Run these from the project's root folder (where `main.py` is):

```powershell
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git push -u origin main
```

What each line does:

| Command | What it does |
|---|---|
| `git init` | Turns the folder into a git repository by creating a hidden `.git/` folder that tracks history. Only needed once, and only if the folder is not already a repository. |
| `git add .` | Stages every file for the next commit, except anything matched by `.gitignore`. |
| `git commit -m "..."` | Saves a snapshot of everything staged, with a message describing it. This is local; nothing has reached GitHub yet. |
| `git branch -M main` | Names the current branch `main`, GitHub's default branch name. |
| `git remote add origin <url>` | Tells your local repository where the GitHub copy is. Copy the URL from the green **Code** button on your repository's page. |
| `git push -u origin main` | Uploads your commits to GitHub. `-u` remembers the pairing, so later pushes can be a plain `git push`. |

Refreshing your repository's page on GitHub should now show your files.

The same repository can also be set from inside the app: **Settings → Developer options → GitHub → Repository → Edit** accepts any GitHub link and points the checkout's `origin` remote at it.

### 3.5 Making changes later

After the first push, day-to-day updates are:

```powershell
git add .
git commit -m "Describe what changed"
git push
```

The **Source control** card in Developer options offers the same Pull, Commit all and Push actions.

---

## 4. Configure the Update Source

This tells *installed copies of the app* which GitHub repository to check for updates. It is separate from where the *code* lives, although they are usually the same repository.

It is **not** the `config/settings.yaml` that is created when you run `python main.py` locally. That file only affects your own development checkout: it is gitignored, never bundled by PyInstaller, and has no effect on what a real install receives. (An earlier version of this guide said to edit it, which meant the update source never reached a distributed install; see [§14](#14-resolved-issues-reference).)

The real configuration point is `config/settings_template.yaml`, which is tracked in git. `packaging/build_release.py` reads it at build time and bakes the result into `data/config/settings.yaml` inside the Setup zip, together with the version tag being released. A fresh install therefore has the correct update source and reports its own version correctly from the very first launch, with no manual editing on each machine.

Edit `config/settings_template.yaml`:

```yaml
updater:
  repo: "your-username/your-repo-name"
  test_mode: false        # false queries the real GitHub API
  local_feed_path: null
```

Keeping `test_mode: true` (the default) lets you validate the pipeline with no network calls first; see [§11](#11-offline-testing-test_mode). Most people should do that, then switch to `false` once the pipeline is trusted. Whatever this file contains when you run `build_release.py` ([§6](#6-build-the-release-artifacts)) is what ships in that release. It is a build input and does not update itself, so a later edit only takes effect in your *next* release.

On a machine that is already installed, a developer can also change the update source from **Settings → Developer options → GitHub → Repository**, including the test mode checkbox. That change applies to that machine only.

---

## 5. GitHub Personal Access Token

A token is required only if the release repository is private, or to push from Developer options.

1. On GitHub, open **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Limit it to the target repository, with these permissions:
   - **Contents: Read**, required to read releases.
   - **Contents: Read and write**, required only for pushing from Developer options.
3. Copy the token. It is shown only once; if you lose it, generate a new one.
4. In the app, open **Settings → Developer options → GitHub → Access token**, click **Edit**, paste the token and click **Save**.

The token is stored only in the OS keychain (Windows Credential Manager) and is never written to `settings.yaml` or any other file. If no keychain backend is available, saving fails with a clear error rather than silently doing nothing. Replacing an existing token asks for confirmation.

> A public repository used only for update checks (not for pushing) does not need a token. Update checks work without authentication, subject to GitHub's lower rate limit for unauthenticated requests.
>
> For a private repository, **every installed machine** needs the token saved in its keychain, or its launcher can neither see nor download releases. Launchers from v1.1.0 and earlier cannot download from a private repository even with a token, and must be replaced by hand once; see [§14](#14-resolved-issues-reference).

---

## 6. Build the Release Artifacts

This step turns the Python source into standalone Windows executables that do not need Python on the end user's machine. Run it from the repository root, **on Windows**, with the project's virtual environment active (`.venv\Scripts\activate`).

```powershell
# Launcher (rebuild when launcher.py or anything it imports changes)
pyinstaller packaging/launcher.spec --distpath dist --workpath build --noconfirm

# Application (rebuild for every release)
pyinstaller packaging/build.spec --distpath dist --workpath build --noconfirm

# Assemble the release zips
python packaging/build_release.py v1.0.0
```

What each step does:

- **`pyinstaller ... launcher.spec`** reads `launcher.py`, follows every module it imports, and bundles them with a Python interpreter into a single file, `dist/CANDecoderLauncher.exe`. The spec excludes the heavy app libraries (PySide6, pyqtgraph, asammdf, cantools, reportlab, numpy, GitPython, plus matplotlib and tkinter in case an old environment still has them), which the launcher never uses, so it stays small and starts instantly. The launcher's only third-party imports are PyYAML, Pydantic, bcrypt, packaging and keyring; its HTTP requests use the standard library. It is built with `console=True` because the update prompt is currently a console prompt.
- **`pyinstaller ... build.spec`** does the same for `main.py`, but as a folder (`dist/CANDecoder-app/`) rather than a single file, because the app's dependencies (especially PySide6 and Qt) are large and a folder starts faster than unpacking a single-file archive on every launch. Everything besides the executable lands in `dist/CANDecoder-app/_internal/`, including the bundled `config/defaults/`. The spec also excludes Qt modules the app never uses (WebEngine, QML, Quick, Multimedia, 3D and others). PyInstaller's PySide6 hooks include them by default, and WebEngine alone adds more than 200 MB; excluding them shrinks the package from about 800 MB to a fraction of that. If a future feature needs one of them, remove it from `QT_UNUSED_EXCLUDES` in `build.spec`. `UNUSED_EXCLUDES` does the same for `matplotlib` and `tkinter`, which the app does not use but which PyInstaller could otherwise pick up through optional imports. Both spec files use PyInstaller 6 syntax and pass only the options that differ from PyInstaller's defaults. The old `cipher=None` arguments were removed: PyInstaller 6 dropped bytecode encryption, and any value other than `None` now stops the build.
- **`build_release.py v1.0.0`** repackages both build outputs into the two zips that end users and the auto updater use. It does not rebuild anything, and it stops with a clear error if the two PyInstaller commands have not been run first. It also bakes `data/config/settings.yaml` into the Setup zip ([§4](#4-configure-the-update-source)) and warns if `test_mode` is false while no repository is set.

Output, in `dist/release/`:

| Artifact | Contents | Used for |
|---|---|---|
| `CANDecoder-Setup-<tag>.zip` | The launcher, this version pre-staged in `versions/<tag>/`, `versions/current.txt`, and a pre-built `data/config/settings.yaml` | First-time installs |
| `CANDecoder-app-<tag>.zip` | The application, with its files at the zip's root, plus the launcher in `launcher/` | Every later update |

You do not need to rebuild the launcher for every release, only when `launcher.py` or a module it imports (`utils/github_updater.py`, `utils/keyring_bridge.py`, `core/config_loader.py`, `utils/file_utils.py`) changes. A normal release reruns the `build.spec` command and `build_release.py` with a new tag. `build_release.py` always needs `dist/CANDecoderLauncher.exe` to exist, because both zips include it; installs from v1.1.1 on replace their launcher with it automatically when they update ([`ARCHITECTURE.md` §16](ARCHITECTURE.md#16-launcher)).

### Asset naming

A release attaches both zips. `utils/github_updater.py::_select_app_asset()` picks the app-only zip by its file name prefix (`ASSET_NAME_PREFIX = "CANDecoder-app-"`) and falls back to the first asset if none matches. If the app-only zip's name changes, `ASSET_NAME_PREFIX` must change to match.

The app-only zip's files sit at the root of the archive, not inside a wrapper folder, because the updater extracts it directly into `versions/<tag>/`. The launcher is the one exception: it goes in a `launcher/` subfolder so that it is never mistaken for the app executable.

---

## 7. Verify the Packaging Worked

A build that finishes without errors does not guarantee the packaged app runs correctly, so verify it before publishing. **Test from a clean folder, not your development checkout;** your development folder already contains config files that could hide a real problem.

```powershell
Expand-Archive "dist\release\CANDecoder-Setup-v1.0.0.zip" -DestinationPath "$env:USERPROFILE\Desktop\CAN-Test-Install"
cd "$env:USERPROFILE\Desktop\CAN-Test-Install"
.\CANDecoderLauncher.exe
```

Checklist:

| Check | What you should see | If it fails |
|---|---|---|
| Launcher runs | No console error before the app window appears | See [§13](#13-troubleshooting) |
| App window opens with a theme | A styled window with the navigation rail, not a plain grey Qt window | Bundled theme files are missing. Check that `dist\CANDecoder-app\_internal\config\defaults\` exists and contains `dark_theme.yaml` and `light_theme.yaml`. |
| `data\` folder exists | Next to `CANDecoderLauncher.exe`, a `data\` folder with `config\settings.yaml` inside | The data root split is not working. This is a real bug; do not publish. |
| `versions\` folder is correct | `versions\v1.0.0\` contains `CANDecoder-app.exe` and `_internal\`, and `versions\current.txt` contains `v1.0.0` | The Setup zip was not staged correctly by `build_release.py`. |
| A real `.mf4` log opens | It decodes and plots without errors | A dependency (asammdf or cantools) was not bundled correctly. |
| Developer options unlock | **Settings → Developer options → Unlock…** accepts `changeme` | Settings were not created. Check that `data\config\settings.yaml` exists and has a `dev_password_hash`. |

Once every row checks out, delete the test folder and continue to publishing.

---

## 8. Publish a Release

This step happens entirely on GitHub's website, with no git commands. A release is a tag plus attached files.

1. On your repository's GitHub page, click **Releases** in the right sidebar, then **Draft a new release**.
2. Under **Choose a tag**, type a new tag name such as `v1.0.0` and select **Create new tag: v1.0.0 on publish**. GitHub creates the tag when you publish, pointing at the latest commit on `main`; you do not need to create it with `git tag`.
3. **Target** should show `main`. Leave it.
4. **Release title** can simply be `v1.0.0`.
5. Drag both zips from `dist/release/` into the **Attach binaries** box.
6. Click **Publish release**.

The tag must start with `v` and be a valid version number (`v1.0.0`, `v1.2.3`). Plain semantic versioning is safest, because the app parses the tag with the `packaging` library to compare versions.

No GitHub Actions or webhooks are needed. The updater calls `GET /repos/<repo>/releases/latest` on launch, and that is all.

---

## 9. Distribute the First Install

Send `CANDecoder-Setup-<tag>.zip` to the end user, who then:

1. Unzips it anywhere.
2. Runs `CANDecoderLauncher.exe`.

`data/` already contains the pre-built settings, and `versions/<tag>/` is already staged, so the first launch needs no network access.

---

## 10. Cutting Subsequent Releases

1. Commit and push the code first (`git add .`, `git commit -m "..."`, `git push`; see [§3.5](#35-making-changes-later)). Publishing a release creates its tag at the tip of the branch at that moment, so push before you build; otherwise the tag will not match what you actually packaged.
2. Rebuild the app: `pyinstaller packaging/build.spec --distpath dist --workpath build --noconfirm`. Rebuild the launcher too if `launcher.py` or a module it imports changed.
3. Run `python packaging/build_release.py v<new-tag>`.
4. Repeat [§7](#7-verify-the-packaging-worked). Verify before publishing, every time.
5. Publish a new GitHub release with both new zips attached ([§8](#8-publish-a-release)).

Not every commit needs a release. Push to GitHub as often as you like to keep the source in sync, and only run steps 2 to 5 when you want a batch of changes to reach installed copies.

On their next launch, existing installs show this prompt:

```
A new version (v1.1.2) is available.
Update now and restart? [y/N/queue]: y
Downloading v1.1.2  [############------------]   52%  61.2 / 117.9 MB
Installing  [########################]  100%  1432 / 1432 files
Updated to v1.1.2. Launching...
```

| Response | Behavior |
|---|---|
| `y` | Downloads and switches to the new version immediately, showing a progress bar for the download and the installation, then launches it. Launchers from v1.1.2 on show the progress bar. |
| `N` | Launches the current version and asks again next time. |
| `queue` | Launches the current version now and applies the update automatically when the app is closed. |

Only new installs need the Setup zip. Existing installs update from the app-only zip.

---

## 11. Offline Testing (`test_mode`)

The whole download, stage, repoint and relaunch pipeline can be tested with no network access by using a local mock release feed.

`config/settings.yaml` (or the Repository row in Developer options, with **Test mode** checked):

```yaml
updater:
  repo: ""
  test_mode: true
  local_feed_path: "C:\\path\\to\\feed.json"
```

`feed.json`:

```json
{
  "tag": "v2.0.0",
  "asset_path": "C:\\path\\to\\CANDecoder-app-v2.0.0.zip"
}
```

In test mode, `asset_path` is a local file path, and `download_and_stage()` copies the file from disk instead of downloading it. This is how the pipeline was validated during development: a full fresh install, update detection, update, relaunch and data-survival check, run entirely offline against real PyInstaller-built binaries.

---

## 12. Automated Tests

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

| Test file | Covers |
|---|---|
| `tests/test_github_updater.py` | Asset selection, zip extraction, permission restoration, the full check, stage and pointer cycle |
| `tests/test_launcher.py` | Entry point resolution, data root handoff, version update after an applied update |
| `tests/test_main_entry.py` | Data root and code root resolution, bundled defaults sync |
| `tests/test_build_release.py` | The settings baked into the Setup zip |

Any change to `launcher.py`, `main.py` or `utils/github_updater.py` should also be validated against real PyInstaller binaries through a full fresh install, update and relaunch cycle ([§7](#7-verify-the-packaging-worked)). Several issues in this pipeline (see [§14](#14-resolved-issues-reference)) were only found that way, not by unit tests. See [`DEVELOPMENT.md` §6](DEVELOPMENT.md#6-testing) for the full test list.

---

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `git: The term 'git' is not recognized...` | Git is not installed, or was installed after this terminal was opened | Install it from [git-scm.com/download/win](https://git-scm.com/download/win), then open a **new** terminal. |
| `python: The term 'python' is not recognized...` | Python is not on PATH | Reinstall Python with "Add python.exe to PATH" checked, or use `py` instead of `python` if the Python launcher is installed. |
| `git push` fails with `File ... exceeds GitHub's file size limit` or `remote rejected` | `dist/`, `build/` or your virtual environment was committed; these hold PyInstaller output of hundreds of megabytes | Confirm `.gitignore` includes `dist/`, `build/` and `.venv/`. Run `git rm -r --cached dist` (and `build` or `.venv` if needed), commit and push again. If this was your first push and it was rejected, use `git commit --amend` instead of a new commit so the large files do not stay in history. |
| `build_release.py` stops with `Missing build output: dist\CANDecoderLauncher.exe` (or similar) | The PyInstaller commands were not run first, or used a different `--distpath` | Run both PyInstaller commands from [§6](#6-build-the-release-artifacts) before `build_release.py`. |
| The packaged app shows a blank, unstyled window | The bundled theme files are not where the code expects them | Confirm `dist\CANDecoder-app\_internal\config\defaults\` contains `dark_theme.yaml` and `light_theme.yaml`. If not, check that the `datas` entry in `packaging/build.spec` still points at `config/defaults`. |
| The launcher prints `Error: No application version is installed` | `versions\current.txt` is missing, empty, or names a folder that does not exist | Rerun `build_release.py`, which creates this file inside the Setup zip. If building by hand, the file must contain exactly the tag (for example `v1.0.0`) with no extra whitespace. |
| The app offers the same update on every launch | `settings.version` in `data\config\settings.yaml` was not advanced after the last update | This was a fixed bug ([§14](#14-resolved-issues-reference)). If it happens again, check that `data\config\settings.yaml` is writable (not read-only and not on a locked or syncing drive). |
| The app closes immediately on a fresh install, before any window appears | Often a malformed config file or a missing bundled dependency | Run the unpacked `CANDecoder-app.exe` from a terminal (not by double-clicking) so any error message stays visible. |
| Pull or Push in Developer options fails | The repository is not set, git has no credentials for it, or the network is unavailable | Check the repository under **Developer options → GitHub**, make sure git can reach it from a terminal (`git ls-remote <url>`), and read the error shown in the app. |

---

## 14. Resolved Issues Reference

Issues found while building and validating this pipeline against real PyInstaller binaries. All are fixed in this codebase and listed here for context when changing the related code. [`ARCHITECTURE.md`](ARCHITECTURE.md) explains the current design in each area.

| Issue | Cause | Fix |
|---|---|---|
| The frozen launcher hung forever when no version was staged | Inside a frozen app, `sys.executable` is the launcher's own binary, not a Python interpreter, so the fallback relaunched the launcher itself | `resolve_entry_point()` raises `RuntimeError` instead of falling back to `sys.executable` when frozen |
| Downloaded update zips were never extracted | `download_and_stage()` saved the archive but did not open it | The zip is extracted and then removed after download |
| The wrong asset was chosen from a release with several attachments | The code always took `assets[0]` | `_select_app_asset()` matches by file name prefix (`ASSET_NAME_PREFIX`) |
| `config/defaults/` was not found after freezing | PyInstaller onedir builds put bundled data under `_internal/`, not next to the executable | `_bundled_defaults_dir()` resolves through `sys._MEIPASS` when frozen |
| The app offered the same update forever | `settings.version` was never advanced after an update was applied | `launcher.py` updates and saves `settings.version` after every applied update |
| Updating from a private repository failed with `404 Client Error: Not Found` and the launcher closed without starting the app (v1.0.3 and v1.1.0 launchers) | The release check sent the token, but the asset was downloaded from its `browser_download_url`, which returns 404 for private repositories, and the error was not caught | The asset is downloaded from its API URL with the token as an unredirected header, and `launcher._apply_update()` catches download failures and starts the current version. Launchers from v1.1.1 on also replace themselves when they update. An install still on an older launcher must have `CANDecoderLauncher.exe` replaced once with the one from a newer Setup zip (keep its `data\` and `versions\` folders). If `queue` was chosen on an older launcher, also delete `versions\queued_update.json`, or it retries and fails after every session. |
| One malformed platform or theme YAML file crashed the whole app at startup | Valid YAML with the wrong shape (for example a bare string) raised an uncaught `TypeError` in `model(**raw)` | `_load_yaml_model()` checks that the parsed YAML is a mapping before building the model, and raises `ConfigLoadError` otherwise |
| The update source never reached real installs, so self-updating silently did nothing for every end user | This guide used to say to edit the `config/settings.yaml` created by `python main.py`. That file is gitignored, belongs to the development checkout only and is never bundled. On a real install, `data/config/settings.yaml` was created on first launch by `ensure_default_settings()`, which always used the schema defaults (`repo: ""`, `test_mode: true`). | `packaging/build_release.py` now bakes `config/settings_template.yaml` (tracked, used only at build time) into `data/config/settings.yaml` inside the Setup zip through `core.config_loader.bootstrap_settings()`, so a fresh install has the right update source before it first runs |
| A fresh install could immediately offer to "update" to the version it had just installed | `settings.version` stayed at the schema default `"0.1.0"` until the first applied update, so `check_for_update()` always saw the installed release as newer | The same build-time bake sets `settings.version` to the tag being released, so a fresh install reports its real version from the first launch |
| Help text showed garbled characters such as `â€"` | Help files are UTF-8, but were read with the Windows default encoding (cp1252) | `load_help_text()` reads UTF-8 and falls back to the locale encoding for older copies; `save_help_text()` writes UTF-8 |
