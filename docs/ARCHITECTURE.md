# Architecture and Design Notes

How each part of the CAN Decoder App works, and why it was built that way. Code comments in the repository are deliberately brief; this document holds the full explanations they point to. For day-to-day development see [`DEVELOPMENT.md`](DEVELOPMENT.md), for UI work see [`UI_GUIDE.md`](UI_GUIDE.md), and for packaging and releases see [`DEVELOPER_SETUP.md`](DEVELOPER_SETUP.md).

## Contents

1. [Overview](#1-overview)
2. [Data Root](#2-data-root)
3. [Configuration](#3-configuration)
4. [Settings Bootstrap](#4-settings-bootstrap)
5. [Password Hashing](#5-password-hashing)
6. [DBC Handling](#6-dbc-handling)
7. [Log Parsing](#7-log-parsing)
8. [Plotting](#8-plotting)
9. [Trace View](#9-trace-view)
10. [Reports](#10-reports)
11. [Sessions](#11-sessions)
12. [Help Content](#12-help-content)
13. [Theming](#13-theming)
14. [Developer Options](#14-developer-options)
15. [Auto Update](#15-auto-update)
16. [Launcher](#16-launcher)
17. [File Utilities](#17-file-utilities)
18. [Startup](#18-startup)

---

## 1. Overview

The app has three layers:

| Layer | Folder | Responsibility |
|---|---|---|
| Core | `core/` | Configuration, DBC and log decoding, plotting, reports, themes, help storage. No knowledge of windows or dialogs, except the plot widget and glyph rendering, which need Qt. |
| UI | `ui/` | All windows, pages, dialogs and shared widgets. |
| Utilities | `utils/` | File helpers, OS keychain access, the end-user auto updater. |

Two entry points sit at the repository root:

- `launcher.py` is the permanent program end users start. It checks for updates, then starts the current version of the app. See [§16](#16-launcher).
- `main.py` is the application itself. It prepares the data folder, loads settings and the theme, and opens the main window. During development it can be run directly.

Heavy third-party libraries each have one owner: `asammdf` is used only by `core/log_parser.py`, `cantools` by `core/dbc_handler.py` and `core/log_parser.py`, `pyqtgraph` by `core/plot_engine.py`, `reportlab` by `core/report_builder.py`, `keyring` by `utils/keyring_bridge.py`, and `GitPython` by `ui/dev_panel.py`. None of them is imported at startup; each loads the first time it is needed ([§18](#18-startup)).

---

## 2. Data Root

The app separates the **code root** from the **data root**, and keeping them apart is what lets updates happen without losing anyone's data.

- **Code root** (`main.CODE_ROOT`) is where this copy of the code lives. On an installed machine it is `versions/<tag>/`, a brand new folder for every release that is replaced as a whole on each update. In a frozen build it is resolved from the executable's location, not from the working directory, because the launcher can start the app from anywhere.
- **Data root** (`main.APP_ROOT`) is where user data lives: platform configs, themes, help text, imported DBC files, cached logs and `settings.yaml`. It must be the same folder across every version, or each update would wipe every user's platforms, DBC files and Developer password. The launcher passes it to the app through the `CAN_DECODER_DATA_ROOT` environment variable, pointing at the stable `data/` folder beside `versions/`.

When `main.py` is run directly (no launcher), there is no environment variable, so the data root falls back to the code root. That is fine for development, where only one copy of the code exists.

### Bundled defaults

`config/defaults/` (built-in themes, help topics and the platform template) is bundled inside every release. On startup, `main._sync_defaults()` copies the running version's bundled defaults into `<data root>/config/defaults/`, so new default themes or help text from an update become available. It only ever writes inside `config/defaults/`, so user-edited copies elsewhere are never touched. In development the two roots are the same folder, so the sync is skipped.

A PyInstaller onedir build does not place bundled data next to the executable. It puts it in an `_internal/` subfolder that is reachable at runtime only through `sys._MEIPASS`. `main._bundled_defaults_dir()` therefore resolves the defaults through `sys._MEIPASS` when frozen. An earlier version assumed the files sat next to the executable; the mistake was only found by building and inspecting a real frozen binary.

---

## 3. Configuration

`core/config_loader.py` holds the Pydantic schemas and YAML loading for every configuration file:

| File | Schema | Notes |
|---|---|---|
| `config/platforms/<slug>.yaml` | `PlatformConfig` | One file per vehicle platform. The slug is the file name. |
| `config/themes/<name>.yaml` | `ThemeConfig`, `ThemeColors` | See [`UI_GUIDE.md` §4](UI_GUIDE.md#4-themes) for the fields. |
| `config/settings.yaml` | `AppSettings`, `UpdaterSettings` | See [`DEVELOPMENT.md` §4](DEVELOPMENT.md#4-settings-reference). |

Platform and theme files are edited by hand by people who do not write code, so validation errors must be readable. `_load_yaml_model()` converts every failure into a `ConfigLoadError` whose message names the file and lists each bad field with a plain description, rather than surfacing a raw Pydantic traceback.

`discover_platforms()` and `discover_themes()` return a dictionary of `{slug: config or ConfigLoadError}`. One broken file is reported as a per-file warning (the Platform Manager lists it in red), and every other file still loads.

YAML that is valid but has the wrong shape needs special handling. A file containing only `my platform` parses to a plain string, and `PlatformConfig(**"my platform")` raises a `TypeError` rather than a validation error. Before this was handled, a single such file crashed the whole app at startup. `_load_yaml_model()` now checks that the parsed document is a mapping before building the model.

All config writes go through `utils.file_utils.atomic_write_text()` ([§17](#17-file-utilities)).

### GitHub repo setting

`normalize_github_repo()` accepts whatever a person is likely to paste: `owner/name`, the browser URL, a clone URL ending in `.git`, an SSH URL (`git@github.com:owner/name.git`), or a link to a page inside the repo such as `/releases` or `/tree/main`. It returns the `owner/name` form that `updater.repo` stores, and raises `ValueError` for anything else, so a typo is rejected in Developer options instead of silently breaking update checks. `set_updater_repo()` saves the result (a blank value clears it) and can change `test_mode` in the same step. `github_remote_url()` builds the HTTPS clone URL used for the git remote ([§14](#14-developer-options)).

---

## 4. Settings Bootstrap

A fresh `settings.yaml` can come from two places:

1. **A development run or a deleted file.** `load_app_settings()` first calls `ensure_default_settings()`, which writes `bootstrap_settings()` with no arguments: schema defaults, a blank repo, `test_mode: true`, and the default Developer password already hashed.
2. **A real install.** `packaging/build_release.py` bakes `data/config/settings.yaml` into the Setup zip at build time by calling `bootstrap_settings(template=..., version=...)`. The template is the `updater` section of `config/settings_template.yaml`, and the version is the tag being released. Because the file already exists on first launch, `ensure_default_settings()` leaves it alone.

The build-time bake fixes two real problems:

- Without it, a fresh install never learned which repo to check, because the `settings.yaml` a developer edited locally is gitignored and never bundled. Self-updating was silently disabled on every distributed copy.
- Without the version seed, a fresh install reported itself as the schema default `0.1.0` until its first update, so it immediately offered to "update" to the very version it had just installed.

Only the `updater` key of the template is read, and the Developer password hash is always generated fresh, so a template in git can never carry a password hash into a release.

---

## 5. Password Hashing

The Developer password is stored only as a bcrypt hash (`AppSettings.dev_password_hash`), never in plain text. The app calls `bcrypt` directly rather than going through `passlib`, because `passlib` is unmaintained and incompatible with `bcrypt` 4.1 and later.

Developer Mode is a soft boundary for a trusted internal team. The hash exists so that an accidental glance at `settings.yaml` does not reveal the password, not to resist a determined attacker. Verification is fully local, so it works with no network connection at the track. The default password is `changeme`, and the Settings page warns after unlocking while it is still in use.

---

## 6. DBC Handling

`core/dbc_handler.py` owns everything shaped like a DBC file, using `cantools`. Its object model (`Message.signals`, `Signal.scale`, `offset`, `choices`) is much easier to inspect and write back out than the `canmatrix` objects `asammdf` uses internally.

- **Structure viewer:** `messages()` feeds the DBC structure table in Advanced Mode, and `signal_detail()` returns the name, unit, scale and offset that the signal editor shows.
- **Temporary edits:** `SignalEdit` describes one field-level override (name, scale, offset or unit). Scope is deliberately limited to those fields; message framing, timing and bus topology are out of scope, so this is a field editor, not a DBC authoring tool. `apply_temp_edit()` changes the in-memory database only. Each session has its own `DbcHandler`, so edits last exactly as long as the session's tab and are discarded when it closes.
- **Export:** `export_edited_dbc()` writes the edited database to a new file and refuses to overwrite the base DBC, so the file on disk is never modified.
- **Force decoding:** `force_map()` records that an unknown raw CAN ID should be decoded as an existing message. It raises `KeyError` if the message does not exist and never creates new signal definitions.

---

## 7. Log Parsing

`core/log_parser.py` reads MF4 files with `asammdf` and decodes them against the platform's DBC through `extract_bus_logging()`, so decoded values match what the DBC structure viewer shows.

- **Decoded signals** land in `LogParser.decoded` as `SignalSeries` (name, timestamps, values, unit). `load()` requests every decoded channel in a single `select()` call, which reads each channel group's data once, instead of calling `get()` once per channel, which reads the group again for every channel in it. The master (time) channel of each group is skipped by its index in `masters_db`. An earlier version skipped it by the name `timestamps`, which newer versions of `asammdf` no longer use (they name it `time`), so time appeared in the signal list as if it were a signal.
- **Not decoded IDs:** every arbitration ID in `CAN_DataFrame.ID` that has no matching DBC message is collected in `not_decoded_ids`. These feed the Unknown CAN IDs tab of the Advanced page and are the candidates for force decoding.
- **Summaries:** `_compute_summaries()` calculates maximum, minimum and average for each numeric signal. Error and anomaly counting was dropped from scope. Signals with a DBC value table decode to text labels (for example `b'OFF'` and `b'ON'`), and calling `np.max` on a text array raises `UFuncTypeError`. Before these signals were skipped, the first enum signal in a log crashed the entire load. They are still plotted, as integer codes (see `SessionWidget._plot_categorical()`), just without a numeric summary; the trace view turns the codes back into state names at the cursors.
- **Force decode:** after `DbcHandler.force_map()`, `apply_force_decode(raw_id)` takes every frame with that ID from `CAN_DataFrame.ID` and `CAN_DataFrame.DataBytes` and decodes each payload with the mapped message. `DataBytes` is a fixed-width array (8 bytes per frame, zero-padded past each frame's DLC), so each row is sliced to the message length before decoding. Frames that do not fit the layout are skipped. Values that are not numbers become `NaN`. The new signals are merged into `decoded` and summaries are computed for them (the existing summaries are unchanged, so they are not recomputed), so they behave exactly like natively decoded signals. This logic was validated against a real captured log. `SignalBrowser` then emits `signals_added`, and the session refreshes its signal lists, the table view's column picker and the data analysis table.

### Held values and statistics

`core/signal_stats.py` holds the lookups the cursors, Data analysis and Table view share, kept out of the UI so they can be tested on their own.

- **Held values:** a CAN signal only has a value when one of its frames arrives, so the value "at" a time is the most recent sample at or before it (`sample_index_at()`, a `searchsorted` on the timestamps). Before a signal's first frame there is no value, shown as a dash. Interpolating between frames was rejected: it invents values the bus never carried, which is misleading for states and step changes.
- **Statistics:** `compute_stats()` returns count, sample rate, minimum, maximum, mean, standard deviation and the times of the peaks, over the whole log or only the samples between two times (the graph cursors). `NaN` values from force decoding are ignored. Enum signals get a state count and the most common state instead of numbers.

---

## 8. Plotting

`core/plot_engine.py` provides two separate renderers:

- **`PlotEngine`** is the interactive plot, built on `pyqtgraph`. It is GPU-accelerated and designed for oscilloscope-style tools; cursor snapping and toggling many traces would be sluggish in `matplotlib` at CAN log data rates. Long logs use pyqtgraph's peak downsampling and clip-to-view instead of drawing every raw sample. `apply_colors()` matches the plot background, axes and cursors to the active theme (cursor A in the muted text color, cursor B in the accent color). There are two vertical cursors, A and B, hidden until placed; a left click in the plot area places A and Shift+click places B (pyqtgraph only reports a click when the mouse didn't drag, so panning never moves a cursor). `cursor_moved` and `cursor_toggled` report every change, and `set_cursor_markers()` draws a dot where a cursor crosses each trace. `snap_cursor_to_peak()` moves a chosen cursor to the maximum or minimum of a trace, over the whole log or only the visible window.
- **`render_static_snapshot()`** renders a static 1200 by 600 pixel PNG for PDF export with pyqtgraph's `ImageExporter`: dark text on white, the signal name as the title and `Time (s)` on the x axis. It gives cleaner print output than a screenshot of the interactive widget. The plot is laid out at 600 by 300 and exported at twice that size, so text and lines are scaled up with it and stay readable at the size the PDF prints them; laying it out at full size would leave the text about 4 pt high in the PDF. The off-screen widget is never shown, so its size is set on the plot item directly (a hidden widget does not apply `resize()` until it is shown). Peak downsampling keeps long logs fast, and `NaN` values leave gaps in the line. It needs a running `QApplication`, which the app always has. This replaced `matplotlib`, which was used for nothing else ([§18](#18-startup)).

---

## 9. Trace View

`ui/trace_view.py` hosts the plot, a toolbar (Fit to data, the Cursor A and B toggles, the cursor readout, Clear plot), a snap row and the **Plotted signals** table. The table replaces pyqtgraph's own legend, which solved two real usability problems:

- It was easy to plot a signal and then only be able to hide it, never remove it.
- The legend only reveals that an entry is clickable after it has already been hidden once (its eye icon appears only on invisible items).

Every plotted signal therefore gets a row with its name in the trace color, its value at each cursor, the change between the cursors, an always-visible Hide/Show button, and a separate Remove button that drops the trace and its cached data completely. The cursor columns are hidden while their cursor is. Trace colors are taken in order from the theme's `plot_palette` through `next_palette_color()`.

The cursor used to be a single hidden line that a Snap button moved to the peak of whichever trace was plotted last, with no readout, so it was hard to tell what it applied to or what it showed. It was reworked around three rules:

- **Every cursor shows its data.** The readout gives each cursor's time and Δt, and the table gives every trace's held value (see [§7](#held-values-and-statistics)) at each cursor.
- **Snapping names its target.** The snap row reads as a sentence (snap *cursor* to the *max or min* of *signal* in *range*), and selecting a table row picks that signal.
- **Placing a cursor is direct.** Click or Shift+click the plot, or toggle the buttons; dragging moves a cursor.

Signal names dragged onto the plot (see `SignalList` in [UI_GUIDE.md](UI_GUIDE.md#3-conventions)) arrive through an event filter on the plot's viewport, because a `QGraphicsView` hands drag events to its viewport rather than to the view itself; `signals_dropped` asks the session to plot them.

---

## 10. Reports

`core/report_builder.py` lays out the PDF with `reportlab`: a title, a summary table (maximum, minimum, average for each signal), then one snapshot image per signal from `render_static_snapshot()`. Callers pass the signals to include; the module has no signal-picking logic of its own. The Export PDF Report command includes the platform's Important signals, or every signal with a numeric summary if no Important Values are set. The snapshot images are written to a temporary folder that is deleted as soon as the PDF has been built.

---

## 11. Sessions

Each open log is a session shown in its own tab, so several logs can be compared side by side. Every session is a `SessionWidget` (`ui/session_view.py`) holding the log path, the platform, the session's `LogParser` and its `DbcHandler`, and one page per analysis view: graph, data analysis, table and advanced.

The session tabs sit in a strip above every page, including Help and Settings, so the open logs are always in view. The strip is a plain `QTabBar` rather than a `QTabWidget`, because a tab widget ties its tabs to the content below them and could not stay visible over the Help and Settings pages. Each tab's data holds its `SessionWidget`, and the widgets live in a separate `QStackedWidget`; since the widget travels with its tab, dragging tabs into a new order needs no index bookkeeping. The tab bar is the list of open sessions; a separate session registry (`core/session_manager.py`) used to duplicate it without anything reading from it, and was removed.

The navigation rail picks the view and the tab picks the session: `MainWindow.show_page()` calls `SessionWidget.show_view()` on every session, so switching tabs keeps the same view. Clicking a tab while Help or Settings is showing returns to the last analysis page. Closing a tab closes the MF4 file and deletes the widget, including any temporary DBC edits.

The Important signals list is edited on the graph page by dragging, and saved to the platform file (`important_values`) on every change. Names the current log doesn't contain stay in the list, shown dimmed, so opening one log never drops signals that another log on the same platform uses.

---

## 12. Help Content

Each help topic is a small Markdown file, so the "?" buttons and the Help page can show real formatting. Viewing help is available to everyone. Editing it (`ui/help_manager.py`) is a Developer action, at the same level as the Platform Manager, because content changes are treated as administrative.

- `config/defaults/help/` ships the built-in topics as part of the app.
- `config/help/` holds the user's editable copies. `bootstrap_default_help()` copies any missing topic there on startup and never overwrites an edited one. The Help Manager runs the same bootstrap when it opens, so a topic added since startup shows its real text straight away.
- `list_help_keys()` returns every topic from both folders.

Help files are read and written as UTF-8. The shipped topics contain characters outside ASCII, and reading them with the Windows default encoding (cp1252) produced garbled text. `load_help_text()` falls back to the locale encoding for older copies the app saved before this was fixed.

---

## 13. Theming

`core/theme_loader.py` turns a theme file into the app-wide Qt stylesheet:

1. `derived_colors()` blends the handful of base colors in the theme file into every shade the stylesheet needs.
2. `_render_glyph()` draws small PNG chevrons, checkmarks and close marks in the theme's colors, because styling a combo box, checkbox or menu with QSS removes the native glyphs and QSS can only reference image files. The images are cached in the system temp folder under `can_decoder_qss/`.
3. `build_stylesheet()` fills `QSS_TEMPLATE` with the colors, font sizes and glyph paths, and `apply_theme()` applies it to the application.

Only windows and dialogs paint a background. Every container inside is transparent, so rows nested inside a card show the card's color rather than dark patches.

Icons are drawn from the Windows icon font (Segoe Fluent Icons on Windows 11, Segoe MDL2 Assets on Windows 10), with Unicode fallbacks elsewhere. `ui/widgets._GlyphIconEngine` paints each icon at draw time in the current theme's text color, so a theme switch recolors icons already on screen without rebuilding any widget.

`load_active_theme()` loads the theme named in `settings.active_theme` and falls back to the first theme that loads if that one is missing or broken. See [`UI_GUIDE.md` §4](UI_GUIDE.md#4-themes) for the theme file format.

---

## 14. Developer Options

Developer options sit at the bottom of the Settings page, collapsed behind the Developer password. Entering the password imports and builds a `ui/dev_panel.DevPanel` inside the card; **Lock** destroys it again. The module is imported only at that point, so GitPython and keyring never load for people who do not unlock it ([§18](#18-startup)). **Help → Developer Options…** only scrolls to that card and never bypasses the password.

The panel is grouped into cards:

| Card | Contents |
|---|---|
| GitHub | Access token and repository, both locked behind **Edit** |
| Content | Platform Manager and Help Manager |
| Source control | Pull, Commit all and Push for the app's own git checkout, with a status view |
| Security | Change the Developer password |
| App folders | Read-only file tree of the data root |

### Protection against accidental changes

The token and repository fields are wrapped in `_LockableRow`: they stay disabled until **Edit** is clicked, and then show **Save** and **Cancel**. Cancel restores the saved value. Saving the repository shows the old and new values (and the git remote change, when relevant) and asks for confirmation. Replacing an existing token asks for confirmation, a blank token is refused, and saving the same value again does nothing. A single stray keystroke here would otherwise break updates and git for the whole install.

### One repo setting for everything

`updater.repo` drives both the end-user updater and git. When it is saved, `DevPanel._sync_git_remote()` points the checkout's `origin` remote at `https://github.com/<owner>/<name>.git`, creating `origin` if it is missing. An `origin` that already refers to the same repository (for example over SSH) is left alone rather than forced to HTTPS. Pull and Push call the same sync first, so a hand-edited `.git/config` cannot quietly send code to a different repository.

The token is stored only in the OS keychain through `utils/keyring_bridge.py` (Windows Credential Manager on the target machines), never in `settings.yaml` or any other file. Some environments, such as locked-down IT images or headless test machines, have no keyring backend. Reading then returns no token instead of crashing, and saving raises `KeyringUnavailableError`, which the panel shows as an error. Git operations use whatever credentials git itself is configured with; the token is not inserted into the remote URL.

The git controls are unrelated to the end-user update mechanism ([§15](#15-auto-update)). They exist for people editing the app's source, and do nothing on an installed build, which is not a git checkout.

---

## 15. Auto Update

`utils/github_updater.py` updates installed copies from GitHub Releases. It does not use git. A running frozen executable cannot overwrite its own files (the OS locks them), so a new release is downloaded into its own `versions/<tag>/` folder and the `versions/current.txt` pointer is moved to it, instead of patching files in place.

- **Checking:** `check_for_update()` asks the GitHub API for the latest release (using the token when one is stored) and compares its tag with `settings.version`. It never raises; an offline or failed check simply returns nothing, because connectivity on race day cannot be assumed and launch must never be blocked.
- **Asset selection:** a release carries both the Setup zip and the app-only update zip. `_select_app_asset()` picks the app-only zip by its `CANDecoder-app-` prefix (`ASSET_NAME_PREFIX`) and falls back to the first asset. Picking the first asset unconditionally, as an earlier version did, broke as soon as a release had both attached.
- **HTTP:** both requests (the release lookup and the asset download) use the standard library's `urllib.request`, which raises `HTTPError` for any 4xx or 5xx response. On Windows it verifies HTTPS against the system certificate store. The `requests` library was used before; it added five packages to the launcher for two GET requests.
- **Private repositories:** `_http_get()` sends the stored token on every request. The asset is downloaded from its API endpoint (`ReleaseInfo.api_url`, the asset's `url` field) with `Accept: application/octet-stream`, not from its `browser_download_url`. For a private repository the browser link returns 404 to anything but a signed-in browser, which is what broke updates from v1.0.3: the release check succeeded with the token, then the download failed. The API endpoint answers with a redirect to a short-lived signed URL on GitHub's file host, and the token must not be sent there, so it is added with `add_unredirected_header()`, which `urllib` drops when following a redirect (an ordinary header would be forwarded). Public repositories work the same way with or without a token. `ReleaseInfo.api_url` is optional, so queue files written by older launchers, which lack it, still load and fall back to the browser link.
- **Staging:** `download_and_stage()` streams the asset to disk in `versions/<tag>/` in 256 KB chunks (the zip is never held in memory), extracts it there one file at a time and deletes the archive. If the download or the extraction fails, the half-staged folder is removed and the error is raised to the launcher; the folder of the version `current.txt` points at is never removed, even if its tag is staged again. An earlier version downloaded the zip and stopped, leaving nothing runnable. Zip extraction does not restore Unix executable permissions, so they are restored from each entry after extraction; this does nothing on Windows but was needed when testing on Linux.
- **Progress:** `download_and_stage()` accepts an optional `progress(phase, done, total)` callback (the `Progress` type). It is called after every downloaded chunk with phase `"download"` and byte counts, then after every extracted file with phase `"extract"` and file counts. `total` is `None` when the server sends no `Content-Length`. The updater only reports numbers; drawing them is left to the caller, which is the launcher's console bar ([§16](#16-launcher)).
- **Queueing:** choosing `queue` at the prompt writes `versions/queued_update.json`, and the launcher applies the update after the app exits.
- **Test mode:** with `test_mode: true`, the updater reads a local JSON feed (`local_feed_path`) instead of the GitHub API, and copies the asset from a local path instead of downloading it. This lets the whole download, stage and relaunch cycle be validated with no network access. See [`DEVELOPER_SETUP.md` §11](DEVELOPER_SETUP.md#11-offline-testing-test_mode).

Because the repo is a setting rather than code, it can point at a personal test repository first and at the team repository later without code changes.

---

## 16. Launcher

`launcher.py` is what end users start, and it is meant to stay the same for the life of an install. All real app logic lives in the versioned code it launches.

On each start it:

1. Loads `data/config/settings.yaml` and checks for an update ([§15](#15-auto-update)).
2. If a newer release exists and none is queued, prompts `y`, `N` or `queue` in the console. On `y` it stages the release, moves the pointer and **records the new version in `settings.version`**. Without that last step, the next launch saw the just-installed release as newer than the recorded version and offered the same update forever; this was only found by running a full two-cycle update with real binaries.
3. Resolves what to run with `resolve_entry_point()`: the staged executable, a staged `main.py`, or (unfrozen development only) the repository's `main.py`.
4. Starts the app with `CAN_DECODER_DATA_ROOT` set to the stable data folder. An environment variable is used rather than a shared import because the child process may be a different version's code entirely.
5. After the app exits, applies any queued update.

While an update is being applied, `ConsoleProgress` shows its progress on a single console line that redraws itself (with `\r`), so the window never looks frozen during a download of more than 100 MB:

```
Downloading v1.1.2  [############------------]   52%  61.2 / 117.9 MB
Installing  [########################]  100%  1432 / 1432 files
```

The download line appears as soon as `y` is entered, before the first byte arrives. If the size is unknown it shows only the megabytes received. The line is redrawn only when its text changes, and it uses plain ASCII so it renders in any Windows console code page. The same bar is shown for a queued update applied after the app exits.

Every update goes through `_apply_update()`. If the download fails for any reason (offline, a revoked token, a missing asset), it prints the error, keeps the current version and returns, so the app still starts; a failed queued update stays queued and is retried after the next session. Before this, a failed download raised an unhandled exception and the launcher closed without starting the app.

### Launcher self-update

From v1.1.1 the launcher updates itself along with the app. Each app-only zip carries the launcher in a `launcher/` subfolder (`LAUNCHER_DIR` in `utils/github_updater.py`), so it is extracted to `versions/<tag>/launcher/CANDecoderLauncher.exe`. After a release is staged, `update_launcher()` compares that file with the running launcher and, if they differ, renames the running executable to `CANDecoderLauncher.exe.old` and copies the new one into its place. Windows does not allow a running executable to be overwritten or deleted, but it does allow it to be renamed, which is what makes this possible without a helper process. If the copy fails, the original is renamed back. The new launcher takes effect from the next start, and `remove_old_launcher()` deletes the `.old` file at that start, once nothing is running it.

The subfolder matters for older launchers: `resolve_entry_point()` runs the first `*.exe` directly inside `versions/<tag>/`, and a launcher placed next to the app executable could be picked instead of the app.

Launchers from v1.1.0 and earlier have no self-update, so an install that still runs one only gets a newer launcher when its `CANDecoderLauncher.exe` is replaced by hand with the one from a newer Setup zip. After that one replacement, every later release updates the launcher automatically.

If the launcher is frozen and no version has been staged, `resolve_entry_point()` raises a clear error. The earlier fallback used `sys.executable`, which inside a frozen app is the launcher's own binary, not a Python interpreter; the launcher relaunched itself forever. This was only found by running the real PyInstaller binary with nothing staged.

The update prompt is a console `input()` for now, which is why `packaging/launcher.spec` builds with `console=True`. A GUI prompt could replace `_prompt_update()` without changing anything else.

---

## 17. File Utilities

`utils/file_utils.py`:

- `ensure_directories()` creates the data root folders (`config/platforms`, `config/themes`, `config/help`, `dbc_store`, `logs_cache`). `versions/` is intentionally not among them: it lives beside the data root, managed by the launcher.
- `atomic_write_text()` writes to a temporary file and then swaps it into place, so a crash mid-write cannot leave a half-written config file that someone was editing by hand. An optional encoding is accepted (help files use UTF-8).
- `copy_default_if_missing()` copies a default file into place only if the destination does not exist, so user edits are never overwritten. Themes and help topics are bootstrapped this way.

---

## 18. Startup

Decoding a log needs several large libraries, but none of them is needed to show the main window. Loading them all up front made `import ui.main_window` take about 2.4 seconds before any window appeared: roughly 0.9 seconds for `asammdf` and `cantools` (which bring in `pandas` and `python-can`), 0.75 seconds for `pyqtgraph` and `matplotlib`, and 0.15 seconds for GitPython, which also runs `git version` in a subprocess when imported. Each is now imported the first time it is needed, and the same import takes about 0.35 seconds (Qt, PyYAML, Pydantic and the app's own modules).

| Library | Loaded when | Where the import sits |
|---|---|---|
| `asammdf`, `cantools`, `pyqtgraph` | A log is opened | `MainWindow._open_session()` imports `core.dbc_handler`, `core.log_parser` and `ui.session_view` (which brings in the plot and the session pages) |
| `reportlab`, pyqtgraph's image exporter | A PDF report is exported | `MainWindow._export_report()` imports `core.plot_engine` and `core.report_builder` |
| GitPython, `keyring`, Platform and Help Managers | Developer options are unlocked | `SettingsPage.try_unlock()` imports `ui.dev_panel` |
| `cantools` | A DBC file is imported in the Platform Manager | `PlatformManagerDialog._on_import_dbc()` |

New code should keep it that way: a module that is imported at startup must not import one of these libraries at the top of the file. Type hints can still name their classes through an `if TYPE_CHECKING:` import, which costs nothing at runtime. To check the effect of a change, run:

```bash
python -X importtime -c "import ui.main_window" 2> importtime.txt
```

and sort `importtime.txt` by its second (cumulative) column.

### Dependencies

Every package in `requirements.txt` is imported directly by the app, the tests or the build:

| Package | Used for |
|---|---|
| `PySide6` | The whole user interface |
| `PyYAML`, `pydantic` | Reading, validating and writing the YAML config files |
| `bcrypt` | Hashing the Developer password |
| `packaging` | Comparing release versions in the updater |
| `keyring` | Storing the GitHub token in the OS keychain |
| `asammdf` | Reading MF4 logs and decoding them against a DBC |
| `cantools` | DBC structure, signal edits, export and force decoding |
| `pyqtgraph` | The interactive plot and the PDF snapshot images |
| `reportlab` | Building the PDF report |
| `GitPython` | The Source control card in Developer options |
| `numpy` | Signal arrays, summaries and force decoding |
| `pytest`, `PyInstaller` | Development only: running the tests and building releases |

Two packages were removed because each was used for a single small job that an existing dependency already covers:

- **`matplotlib`** drew only the PDF snapshot, which `pyqtgraph` now renders ([§8](#8-plotting)). Removing it also removes `fontTools`, `contourpy`, `kiwisolver`, `cycler` and `pyparsing`, about 55 MB installed, from the environment and from the frozen app.
- **`requests`** made only the updater's two GET requests, which now use the standard library ([§15](#15-auto-update)). Removing it also removes `urllib3`, `charset_normalizer`, `idna` and `certifi` from the launcher.

`packaging/build.spec` also excludes `matplotlib` and `tkinter` explicitly, so a development environment that still has them installed cannot bundle them by accident (pyqtgraph contains an optional matplotlib exporter that PyInstaller would otherwise follow).
