# Development Guide

Running the app from source, the project layout, the settings reference, testing and code style. For making UI changes, see [`UI_GUIDE.md`](UI_GUIDE.md). For how each module works and why, see [`ARCHITECTURE.md`](ARCHITECTURE.md). For packaging and distributing releases, see [`DEVELOPER_SETUP.md`](DEVELOPER_SETUP.md).

## Contents

1. [Running from Source](#1-running-from-source)
2. [Project Structure](#2-project-structure)
3. [Data Folder Layout](#3-data-folder-layout)
4. [Settings Reference](#4-settings-reference)
5. [Platform Configs](#5-platform-configs)
6. [Testing](#6-testing)
7. [Code Style](#7-code-style)
8. [Key Design Notes](#8-key-design-notes)

---

## 1. Running from Source

### Requirements

- Python 3.11 or later.
- Windows is the packaging and deployment target. macOS and Linux work for development and testing.

### Setup

```bash
git clone <repo-url> can_decoder_app
cd can_decoder_app

python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

python main.py
```

Running `main.py` directly skips the launcher and its update check. On first run the app creates `config/settings.yaml` (with the default Developer password `changeme`), copies the default themes into `config/themes/` and the default help topics into `config/help/`. In a development checkout the data folder is the repository itself; see [`ARCHITECTURE.md` §2](ARCHITECTURE.md#2-data-root).

---

## 2. Project Structure

```
can_decoder_app/
├── main.py                       Application entry point
├── launcher.py                   Update check and relaunch wrapper (see ARCHITECTURE.md §16)
├── config/
│   ├── defaults/                 Built-in themes, platform template, default help topics
│   ├── platforms/                Per-vehicle YAML configs
│   ├── themes/                   User-editable theme copies (created on first run)
│   ├── help/                     User-editable help topics (created on first run)
│   ├── settings_template.yaml    Updater settings baked into releases at build time
│   ├── settings.example.yaml     Reference copy of settings.yaml (never read)
│   └── settings.yaml             Generated on first run (gitignored)
├── core/
│   ├── config_loader.py          Pydantic schemas, YAML loading, settings, Developer password, repo parsing
│   ├── theme_loader.py           Derived colors, glyph images, stylesheet
│   ├── help_content.py           Help topic storage and bootstrapping
│   ├── log_parser.py             MF4 decoding, summaries, force decode
│   ├── signal_stats.py           Values at a time and per-signal statistics
│   ├── dbc_handler.py            DBC structure, temporary edits, export, force mapping
│   ├── plot_engine.py            Interactive pyqtgraph plot (cursors A and B) and PDF snapshot images
│   └── report_builder.py         PDF report
├── ui/
│   ├── main_window.py            Main window, session tabs, Open Log dialog, Help page
│   ├── session_view.py           One open log: its four pages and the Important signals lists (loaded on first open)
│   ├── data_view.py              Data analysis page: statistics per signal
│   ├── tabular_view.py           Table view page: signals on one time axis, CSV export
│   ├── settings_page.py          Settings page and password-gated Developer options
│   ├── widgets.py                Shared UI pieces: icons, signal lists, cards, navigation rail, headers
│   ├── signal_browser.py         Advanced page: unknown CAN IDs, force decode, DBC structure
│   ├── trace_view.py             Plot toolbar, plot, cursors and Plotted signals table
│   ├── help_viewer.py            "?" button and help popup
│   ├── dev_panel.py              Developer options panel
│   ├── platform_manager.py       Platform config editor and DBC import
│   └── help_manager.py           Help topic editor
├── utils/
│   ├── github_updater.py         Release checks and versioned update staging
│   ├── keyring_bridge.py         OS keychain access for the GitHub token
│   └── file_utils.py             Atomic writes, folder setup, default copies
├── packaging/                    PyInstaller specs and the release build script
├── docs/
│   ├── DEVELOPMENT.md            This file
│   ├── ARCHITECTURE.md           Module-by-module design notes
│   ├── UI_GUIDE.md               UI structure, conventions and themes
│   └── DEVELOPER_SETUP.md        GitHub distribution and packaging guide
├── tests/                        pytest suite (see §6)
├── pytest.ini
└── requirements.txt
```

---

## 3. Data Folder Layout

Everything the app writes lives under the data root (the repository in development, `data/` beside the launcher on an installed machine):

| Path | Contents |
|---|---|
| `config/settings.yaml` | App settings (see [§4](#4-settings-reference)) |
| `config/platforms/*.yaml` | Vehicle platform configs (see [§5](#5-platform-configs)) |
| `config/themes/*.yaml` | Themes (see [`UI_GUIDE.md` §4](UI_GUIDE.md#4-themes)) |
| `config/help/*.md` | Help topics shown by the "?" buttons and the Help page |
| `config/defaults/` | Built-in defaults, refreshed from the running version on every start |
| `dbc_store/` | DBC files referenced by platform configs |
| `logs_cache/` | Reserved for cached log data |

The GitHub token is not stored in any of these files; it lives in the OS keychain.

---

## 4. Settings Reference

`config/settings.yaml` is gitignored because it holds the Developer password hash. `config/settings.example.yaml` shows its shape for reference only and is never read by the app.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `version` | string | `"0.1.0"` | The installed version. Releases seed it with the real tag, and the launcher advances it after each applied update. Update checks compare against it. |
| `active_theme` | string | `"dark"` | File name (without `.yaml`) of the theme in `config/themes/` to use. Changed from Settings or **View → Theme**. |
| `updater.repo` | string | `""` | `owner/name` of the GitHub repository releases are published to. Also used as the git `origin` for the Developer options Pull and Push buttons. Changed from **Developer options → GitHub**, which accepts any GitHub link. |
| `updater.test_mode` | bool | `true` | When true, update checks read the local feed below instead of the GitHub API. |
| `updater.local_feed_path` | string or null | `null` | Path to a JSON feed used in test mode. See [`DEVELOPER_SETUP.md` §11](DEVELOPER_SETUP.md#11-offline-testing-test_mode). |
| `dev_password_hash` | string | hash of `changeme` | bcrypt hash of the Developer password. Changed from **Developer options → Security**. |

A development run creates this file with the defaults above. A real install receives a pre-built copy from the Setup zip, with `updater` taken from `config/settings_template.yaml` and `version` set to the released tag; see [`ARCHITECTURE.md` §4](ARCHITECTURE.md#4-settings-bootstrap).

---

## 5. Platform Configs

A platform ties a vehicle to its DBC file and to the signals that matter most for it. The easiest way to manage platforms is **Settings → Developer options → Content → Manage platforms…**, which also imports and validates DBC files.

To add a platform by hand instead, copy `config/defaults/platform_template.yaml` into `config/platforms/`, name it after the platform's slug (for example `platform_a.yaml`), fill in the fields and place the DBC file in `dbc_store/`.

| Field | Required | Meaning |
|---|---|---|
| `name` | Yes | Display name, for example `2026 EV Chassis A`. |
| `description` | No | Short description shown in the Open Log dialog. |
| `dbc_path` | Yes | File name inside `dbc_store/`. |
| `image` | No | Path to a photo or diagram of the platform. |
| `important_values` | No | Signal names (exactly as in the DBC) shown in the Important signals list and included in PDF reports (every signal is included if this is empty). Edited in the app by dragging signals into the Important signals list on the Graph analysis page, or with its pencil button. |
| `metadata` | No | Free-form key and value pairs for notes. Not read by the app. |

A file that fails validation does not stop the app: it is reported as a per-file error and listed in red in the Platform Manager.

---

## 6. Testing

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

`QT_QPA_PLATFORM=offscreen` runs the Qt tests headlessly, with no display required. On Windows, `test_download_and_stage_restores_executable_permission_bits` fails because Windows does not support Unix permission bits; it passes on macOS and Linux.

| Test area | File(s) |
|---|---|
| Config loading, settings, repo parsing | `tests/test_config_loader.py` |
| Themes | `tests/test_theme_loader.py` |
| Log parsing, force decode | `tests/test_log_parser.py` |
| DBC handling | `tests/test_dbc_handler.py` |
| Reports | `tests/test_report_builder.py` |
| File helpers | `tests/test_file_utils.py` |
| Help content | `tests/test_help_content.py`, `tests/test_help_viewer.py`, `tests/test_help_manager.py` |
| Platform Manager | `tests/test_platform_manager.py` |
| Developer options panel | `tests/test_dev_panel.py` |
| Main window, including a full open, plot, export and close of a real log | `tests/test_main_window.py` |
| Plot and Plotted signals table | `tests/test_trace_view.py` |
| Auto-update pipeline | `tests/test_github_updater.py`, `tests/test_launcher.py`, `tests/test_main_entry.py`, `tests/test_build_release.py` |
| End-to-end UI flows against a real log | `tests/test_ui_integration.py` |

Tests that need the real sample log (`tests/fixtures/sample_log.mf4`) are skipped if it is missing.

### Regression tests

Several tests guard against real bugs. Keep them passing, and read the linked explanation before changing the code they cover.

| Test | Guards against | Details |
|---|---|---|
| `test_platform_config_wrong_shape_raises_config_load_error_not_typeerror` | A bare-string YAML file crashing startup | [`ARCHITECTURE.md` §3](ARCHITECTURE.md#3-configuration) |
| `test_load_handles_value_table_enum_signals_without_crashing` | Enum signals crashing the summary step | [`ARCHITECTURE.md` §7](ARCHITECTURE.md#7-log-parsing) |
| `test_categorical_signal_plots_as_coded_values_instead_of_silently_failing` | Enum signals doing nothing when clicked | [`ARCHITECTURE.md` §7](ARCHITECTURE.md#7-log-parsing) |
| `test_remove_button_actually_unplots_the_signal` | Signals that could be hidden but never removed | [`ARCHITECTURE.md` §9](ARCHITECTURE.md#9-trace-view) |
| `test_help_button_has_no_clipped_glyph_styling` | Global button padding clipping the "?" glyph | [`UI_GUIDE.md` §3](UI_GUIDE.md#3-conventions) |
| `test_select_app_asset_prefers_prefixed_name` | The updater picking the Setup zip | [`ARCHITECTURE.md` §15](ARCHITECTURE.md#15-auto-update) |
| `test_download_and_stage_extracts_zip_contents` | Update zips downloaded but never extracted | [`ARCHITECTURE.md` §15](ARCHITECTURE.md#15-auto-update) |
| `test_resolve_entry_point_frozen_with_nothing_staged_raises_cleanly` | The frozen launcher relaunching itself forever | [`ARCHITECTURE.md` §16](ARCHITECTURE.md#16-launcher) |
| `test_main_advances_recorded_version_after_immediate_update` | The same update being offered forever | [`ARCHITECTURE.md` §16](ARCHITECTURE.md#16-launcher) |
| `test_bundled_defaults_dir_frozen_uses_meipass` | Bundled defaults not found in frozen builds | [`ARCHITECTURE.md` §2](ARCHITECTURE.md#2-data-root) |
| `test_build_release.py` (version and template tests) | Fresh installs with no update source or the wrong version | [`ARCHITECTURE.md` §4](ARCHITECTURE.md#4-settings-bootstrap) |

### Writing tests

- Modal dialogs (`QMessageBox`, file dialogs) block headless runs. Monkeypatch them for the test; see [`UI_GUIDE.md` §6](UI_GUIDE.md#6-testing-a-ui-change).
- `tests/test_build_release.py` loads `packaging/build_release.py` by file path, because the repository's `packaging/` folder has the same name as the installed `packaging` library, which wins on `sys.path`.
- Any change to `launcher.py`, `main.py` or `utils/github_updater.py` should also be checked against real PyInstaller binaries through a full install, update and relaunch cycle; see [`DEVELOPER_SETUP.md` §7](DEVELOPER_SETUP.md#7-verify-the-packaging-worked).

---

## 7. Code Style

Comments in the code are kept short so the code stays easy to scan, and longer explanations live in these docs.

- Every file begins with a header block:

  ```
  #--------------------#
  # file_name.py
  # one-line description of what the file does
  #--------------------#
  ```

  A header may add one or two lines pointing to the relevant doc section. `main.py` has an extended header with a description, author and ASCII art.
- Comments are lowercase and use light punctuation. Commas and parentheses are fine, but sentences do not end with periods.
- Names of code items (classes, functions, variables, constants and Qt types such as `SessionWidget`, `_show_signal()` or `QAction`) keep their original case inside comments, so they can be searched for.
- Sections inside a file are marked with `# -- section name --`.
- A function or class gets a one-line comment above it when its purpose is not obvious from its name. Docstrings are not used.
- When the reasoning behind code needs more than a line, write it in the docs and point to it, for example `# see docs/ARCHITECTURE.md, data root`.
- Documentation is written in full sentences with normal punctuation and does not use em dashes.

---

## 8. Key Design Notes

A summary of the main decisions; each links to the full explanation.

- **Code root and data root are separate,** so updates replace code without touching user data ([`ARCHITECTURE.md` §2](ARCHITECTURE.md#2-data-root)).
- **Password hashing uses `bcrypt` directly,** not `passlib`, which is unmaintained and incompatible with `bcrypt` 4.1 and later ([§5](ARCHITECTURE.md#5-password-hashing)).
- **The GitHub token is stored only in the OS keychain,** never in `settings.yaml` ([§14](ARCHITECTURE.md#14-developer-options)).
- **One repository setting drives both the updater and git,** and it is locked against accidental edits ([§14](ARCHITECTURE.md#14-developer-options)).
- **Force decode maps a raw CAN ID to an existing DBC message;** it does not create new signals ([§6](ARCHITECTURE.md#6-dbc-handling)).
- **DBC edits made in the app are field-level and session-only,** and are exported to a new file; the base DBC on disk is never overwritten ([§6](ARCHITECTURE.md#6-dbc-handling)).
- **Trace colors come from the active theme's `plot_palette`,** not a hardcoded list ([§9](ARCHITECTURE.md#9-trace-view)).
- **Updates never use git on installed machines;** they download into versioned folders and move a pointer ([§15](ARCHITECTURE.md#15-auto-update)).
