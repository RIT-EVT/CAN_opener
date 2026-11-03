# UI Development Guide

How the UI is put together, and what to change for common kinds of work. For running the app from source, see [`DEVELOPMENT.md`](DEVELOPMENT.md). For the reasoning behind individual modules, see [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Contents

1. [Architecture](#1-architecture)
2. [File Map](#2-file-map)
3. [Conventions](#3-conventions)
4. [Themes](#4-themes)
5. [Common Changes](#5-common-changes)
6. [Testing a UI Change](#6-testing-a-ui-change)
7. [Checklist Before Shipping](#7-checklist-before-shipping)

---

## 1. Architecture

All UI is built with PySide6. The layout follows Windows 11 Task Manager: a collapsible navigation rail on the left, one page at a time on the right, and a header at the top of each page holding that page's main actions. Open logs are tabs in a strip across the top of every page, like browser tabs: the rail picks *what* to look at, the tab picks *which log*.

```
MainWindow (ui/main_window.py)
├── Menu bar: File / View / Help     shared QAction objects (see §3)
├── NavRail (ui/widgets.py)           analysis pages at the top; Help, then Settings, pinned at the bottom
├── Session strip                     QTabBar, one tab per open log, plus a "+" open button; above every page
└── QStackedWidget of pages
    ├── Analysis page                 shared by Graph analysis, Data analysis, Table view and Advanced
    │   ├── PageHeader                title follows the rail; Export PDF Report, Open Log
    │   ├── EmptyState                shown while no log is open
    │   └── QStackedWidget            one SessionWidget per tab (the tab's data points at it)
    │       └── SessionWidget (ui/session_view.py), one view per rail page:
    │           ├── graph:    sidebar (Important signals and All signals lists, drag and drop)
    │           │             and TraceView (ui/trace_view.py): plot, cursors A and B, snap row,
    │           │             "Plotted signals" table with values at the cursors
    │           ├── data:     DataAnalysisView (ui/data_view.py): statistics table and detail pane
    │           ├── table:    TabularView (ui/tabular_view.py): signals on one time axis, CSV export
    │           └── advanced: SignalBrowser (ui/signal_browser.py): unknown CAN IDs, force decode, DBC
    ├── HelpPage (ui/main_window.py)  every help topic, searchable
    └── SettingsPage (ui/settings_page.py)
        ├── Appearance, Mode, Updates and About cards
        └── Developer options card    password entered inline, unlocks:
            └── DevPanel (ui/dev_panel.py), which opens:
                ├── PlatformManagerDialog (ui/platform_manager.py)
                └── HelpContentManagerDialog (ui/help_manager.py)
```

`OpenLogDialog` (in `ui/main_window.py`) picks the log file and the vehicle platform in a single step.

Three access tiers control what is visible, not what is loaded:

| Tier | Gate | Controls it affects |
|---|---|---|
| Simple | None (the default) | Graph analysis, Data analysis and Table view pages, including editing the Important signals |
| Advanced | `MainWindow.advanced_action`, a checkable toggle with no password. It lives in the View menu and is bound both ways to the checkbox on the Settings page. | The Advanced page (`SignalBrowser`): its rail button and its View menu entry |
| Developer | Password (`core.config_loader.verify_dev_password`), entered in `SettingsPage.try_unlock()` | `DevPanel` (created on unlock, destroyed on Lock) and everything opened from it |

`MainWindow._on_advanced_toggled` shows or hides the Advanced rail button and enables or disables its View menu action. Turning Advanced Mode off while the Advanced page is showing falls back to Graph analysis, and `show_page()` refuses the Advanced page while the mode is off. Nothing is reloaded or rebuilt: every session builds its Advanced page when it opens, and only the way to reach it changes.

---

## 2. File Map

| File | Owns |
|---|---|
| `ui/main_window.py` | `MainWindow` (menu bar, navigation rail, session strip, pages, mode and theme switching), `OpenLogDialog`, `HelpPage`. The page keys (`PAGE_GRAPH` and so on) and their titles are in `_PAGE_INFO` |
| `ui/session_view.py` | `SessionWidget` (per-tab content: the four views, the graph page sidebar and Important signals editing) and `ImportantValuesDialog`. Imported only when the first log is opened, see [`ARCHITECTURE.md` §18](ARCHITECTURE.md#18-startup) |
| `ui/data_view.py` | `DataAnalysisView`: per-signal statistics table, whole log or between the cursors, with a detail pane and distribution chart |
| `ui/tabular_view.py` | `TabularView` and `TimeAlignedModel`: chosen signals on one time axis, looked up per cell as drawn; `write_csv()` |
| `ui/widgets.py` | Shared building blocks: `icon()` (themed Segoe Fluent glyphs), `label()`, `button()`, `action_button()`, `search_field()`, `filter_list()`, `SignalList` and its drag helpers, `Card`, `SettingRow`, `StatTile`, `PageHeader`, `NavRail`, `EmptyState` |
| `ui/settings_page.py` | `SettingsPage`: Appearance, Mode, Updates and About cards, plus the password-gated Developer options card |
| `ui/trace_view.py` | `TraceView`: plot toolbar, plot, cursors A and B with their readout and snap row, and the "Plotted signals" table (values at the cursors; hide, show and remove traces) |
| `ui/signal_browser.py` | `SignalBrowser`, the Advanced page: Unknown CAN IDs and the force-decode workflow, the DBC structure table; `SignalEditDialog` |
| `ui/dev_panel.py` | `DevPanel`: GitHub token and repo (locked behind Edit), content managers, git controls, Developer password change, data folder tree |
| `ui/platform_manager.py` | `PlatformManagerDialog`: create, edit and delete platform configs; DBC import |
| `ui/help_manager.py` | `HelpContentManagerDialog`: Markdown source and live preview editor for help topics |
| `ui/help_viewer.py` | `HelpViewerDialog`, `make_help_button()`: the read-only "?" popup used throughout the app |
| `core/theme_loader.py` | Derived colors, glyph images and QSS generation from a `ThemeConfig`; `apply_theme()`, `next_palette_color()` |
| `core/help_content.py` | Help topic storage (load, save, list) and default bootstrapping |
| `core/signal_stats.py` | Held value lookups and per-signal statistics shared by the cursors, Data analysis and Table view |
| `core/config_loader.py` | Pydantic schemas for settings, platforms and themes; YAML load and save |

---

## 3. Conventions

**Menu and on-page commands share one `QAction`.** Create it once in `MainWindow._build_actions()`, add it to a menu in `_build_menu()`, and place it on a page with `ui.widgets.action_button(action)`. Never create two `QAction` objects wired to the same slot. Duplicated actions drift apart (different text, shortcut or enabled state) and were a real bug in an earlier version of the app.

**Build screens from `ui/widgets.py`.** Group related controls in a `Card`. Use `SettingRow` for a row with a title and description on the left and controls on the right. Use `button(text, variant=..., icon_name=...)` rather than a bare `QPushButton`. A search or filter box is `search_field(placeholder, on_change)`, and `filter_list(list_widget, text)` hides the rows of a list that do not match. Icons come from `icon(name)`; new icon names are added to `_GLYPHS` in `ui/widgets.py`.

**Signals are dragged as names.** A `SignalList` (in `ui/widgets.py`) puts the selected names on the drag as `SIGNAL_MIME`. Any widget that should accept them reads them back with `signal_names_from_mime()`. A `SignalList` never edits itself on a drop: it emits `names_dropped(names, row, source)` and its owner decides what the drop means and rebuilds the list (see `SessionWidget._on_dropped_on_important()`). Set `drop_sources` to limit which widgets a list accepts drops from; the All signals list only accepts drops from the Important signals list, which it treats as a removal.

**Widgets opt into styles through Qt properties,** which the stylesheet matches with attribute selectors:

| Property | Set on | Values |
|---|---|---|
| `variant` | `QPushButton`, `QToolButton` | `primary` (the one main action on a screen), `danger` (destructive), `subtle` (borderless, for toolbars and table rows). A checkable `QPushButton` of any variant gets an accent outline while checked, as the cursor toggles do |
| `role` | `QLabel` | `title`, `subtitle`, `section`, `muted`, `stat`, `statLabel`, `error` |
| `card` | `QFrame` | `true` for a rounded card surface |

If a property is changed after the widget is shown, unpolish and polish the widget (`widget.style().unpolish(widget)`, then `polish(widget)`) so the new style applies.

**A widget-specific style override** uses `setObjectName()` together with a scoped rule such as `QPushButton#helpButton { ... }`. An ID selector is more specific than the app-wide type selector, so it wins the cascade without affecting any other widget. The "?" help button uses this to remove the global button padding, which otherwise clips the glyph on a 22 px button.

**Help content is data, not code.** Every "?" button is created with `make_help_button(help_dir, key, title, parent)`. The `key` maps to a Markdown file (`config/help/<key>.md`, bootstrapped from `config/defaults/help/<key>.md`); the button code never contains help text.

**Developer-only features live in `DevPanel`.** Do not gate a feature by hiding a button elsewhere in the main window. Add it as a `Card` in `DevPanel.__init__()` instead (see `_platform_manager_section()` for the pattern: a `SettingRow` with a button that opens a dialog). Settings that would break the install if changed by accident, such as the GitHub repo and token, go in a `_LockableRow`: the field is read-only until **Edit** is clicked, and saving asks for confirmation.

**Config-editing dialogs follow the Platform Manager and Help Manager pattern:** a `QDialog` subclass that reads the relevant files when it opens, edits in memory, and writes back through the matching `core/` save function (`save_platform_config`, `save_help_text` and so on). UI code never writes YAML or Markdown files directly.

**Code comments** are short and lowercase, with no sentence-ending periods. Every file starts with a header of this form:

```
#--------------------#
# file_name.py
# one-line description of what the file does
#--------------------#
```

Section comments inside a file use `# -- section name --`. Longer explanations belong in the docs, and a comment can point to them (for example `# see docs/ARCHITECTURE.md, data root`).

---

## 4. Themes

Themes are YAML files in `config/themes/`. The built-in `dark` and `light` themes are copied there from `config/defaults/` on first run, and any additional `.yaml` file placed in that folder appears in the theme picker automatically.

### Theme file fields

| Field | Required | Meaning |
|---|---|---|
| `name` | Yes | Theme name. The file name (without `.yaml`) is what the settings store and the picker display. |
| `mode` | No | `light`, `dark` or `custom` (the default). Informational only. |
| `font_scale` | No | Multiplier for the base 10 pt font size. Defaults to `1.0`. |
| `colors.background` | Yes | Window and page background. |
| `colors.surface` | Yes | Cards, inputs, lists and the plot background. |
| `colors.text` | Yes | Main text color; icons are drawn in this color as well. |
| `colors.accent` | Yes | Primary buttons, selection, focus underline and the active tab. |
| `colors.border` | Yes | Input and control borders. |
| `colors.error` | No | Error text and destructive buttons. Defaults to `#e05a4e`. |
| `colors.plot_palette` | No | List of trace colors, assigned in order as signals are plotted. If empty, a three-color fallback is used. |

### Derived colors

A theme only defines the base colors above. `core/theme_loader.derived_colors()` computes every other shade the stylesheet needs by blending the base colors: muted and disabled text, a softer border, hover, pressed and selected fills, alternating table rows, the navigation rail background, input backgrounds, the accent hover color, and the text color used on top of the accent (black or white, whichever contrasts better). A hand-made theme therefore still gets a complete and consistent look.

### Glyph images

Styling a `QComboBox`, `QCheckBox` or `QMenu` with QSS removes its native arrow and check glyphs, and QSS cannot draw shapes itself; it can only reference image files. `core/theme_loader._render_glyph()` therefore draws small PNG chevrons, checkmarks and close marks in the theme's colors and caches them in the system temp folder (`can_decoder_qss/`). When no Qt application is running (for example in plain unit tests), the glyphs are skipped and the stylesheet is built without them.

---

## 5. Common Changes

Each entry lists the UI work and, where one exists, the system-level change it depends on.

### Add a menu command

In `MainWindow._build_actions()`, create a `QAction` (with `icon(...)`, and a shortcut if it warrants one), then add it to the appropriate menu in `_build_menu()`. Connect `.triggered` to a new `MainWindow` method. If it is a main action for a page, also add `action_button(action)` to that page's `PageHeader`.

### Add a page to the navigation rail

There are two kinds of page:

- **An analysis page** works on the selected session (like Data analysis). Add its key and an entry in `_PAGE_INFO` (title, icon, shortcut, header subtitle) and add the key to `ANALYSIS_PAGES`, both in `ui/main_window.py`. Build the view as its own widget, create it in `SessionWidget.__init__()` and register it in `self._view_index` under the same key. The shared analysis page header, the rail button and the View menu entry follow from `_PAGE_INFO`.
- **An app page** does not depend on a log (like Help). Build it as a `QWidget` whose layout starts with a `PageHeader`, add an entry in `_PAGE_INFO`, then in `MainWindow._build_pages()` call `self.nav.add_page(key, "Title", "icon_name", bottom=True)` and register it with `self._page_index[key] = self.pages.addWidget(page)`.

### Add a setting

Add a `SettingRow` to the appropriate card in `ui/settings_page.py`, or create a new `Card`. If the setting persists, route it through `core/config_loader.py` as the theme setting does (see the next section).

### Add a new field to a platform, theme or settings config

This change always reaches beyond the UI:

1. **`core/config_loader.py`:** add the field to the relevant Pydantic model (`PlatformConfig`, `ThemeColors`, `ThemeConfig` or `AppSettings`) with a default value, so existing YAML files without it still load.
2. **`config/defaults/*.yaml`:** add the field to the shipped default files so fresh installs and the template include it.
3. **UI:** add the control that reads and writes it (for example a new field in `PlatformManagerDialog`), following the existing read-on-open, write-through-`save_*` pattern.
4. **Tests:** extend `tests/test_config_loader.py` for the schema change and the relevant UI test file for the new control.

Leaving out the default value in step 1 is the most common way to break this: every existing YAML file without the new key will fail validation and appear as a `ConfigLoadError` for that platform or theme.

### Add a new theme color

1. **`core/config_loader.ThemeColors`:** add the field with a default.
2. **`core/theme_loader.derived_colors()`:** add it to the returned dictionary; it is then available as `{name}` in `QSS_TEMPLATE`.
3. **`config/defaults/dark_theme.yaml` and `light_theme.yaml`:** add a value, otherwise existing themes fall back to the schema default.
4. Themes a team member has already customized in `config/themes/` do not receive the new color automatically, because bootstrapping only copies missing files, not missing fields inside an existing file. Document the new color in [§4](#4-themes) so custom themes can be updated by hand.

Prefer deriving a new shade in `derived_colors()` over adding a new theme field, so existing themes keep working unchanged.

### Add a help topic ("?" button) to a new UI element

No schema change is needed.

1. Call `make_help_button(help_dir, "new_topic_key", "Display Title", self)` where the button should appear.
2. Add `config/defaults/help/new_topic_key.md` with the default content. It is picked up automatically: `list_help_keys()` scans the defaults folder, and `bootstrap_default_help()` copies it into the user's `config/help/` on the next startup or the next time the Help Manager opens.
3. No code change is needed to make it editable: `HelpContentManagerDialog` lists whatever `list_help_keys()` returns, and the Help page lists the same topics.

### Add a control to the Plotted signals table

`TraceView._add_table_row()` builds six columns, numbered by the `COL_*` constants: signal name, the values at cursors A and B, the change between them, a Hide/Show toggle and a Remove button. To add another (for example a line-style picker):

1. Add a `COL_*` constant, change the column count in `TraceView.__init__()` (`QTableWidget(0, 6)` becomes `7`) and update `setHorizontalHeaderLabels`.
2. Add the corresponding widget or item in `_add_table_row()`.
3. If the control changes how the trace looks, add a `TraceView` method that updates its own state (such as `_colors`) and then the trace through `PlotEngine`, rather than calling `PlotEngine` from the row's callback. This keeps `TraceView` as the single place where table state and plot state are reconciled.

### Add a new Developer dialog (a "manager")

Follow `PlatformManagerDialog` or `HelpContentManagerDialog`:

1. Create a new `QDialog` subclass in its own `ui/` file, constructed with `app_root` (or the paths it needs) and a `parent`.
2. Read the relevant files in `__init__`, provide editing controls, and write back through a `core/` function on save. Never write files directly from the dialog.
3. In `DevPanel`, add a `SettingRow` with a button that opens it: `SomeDialog(self.app_root, self).exec()`.
4. If it manages a new kind of config, see "Add a new field" above for the schema side.

### Add an Advanced-Mode-only control

Put it on the Advanced page (`SignalBrowser`), which is only reachable in Advanced Mode, rather than hiding a control on another page. For a whole new Advanced-only page, follow `PAGE_ADVANCED` in `MainWindow._on_advanced_toggled()` and `show_page()`. Build it when the session opens and only change how it is reached; creating widgets lazily on toggle makes toggling slow and loses their state.

### Change how a signal is plotted

`SessionWidget._show_signal()` is the single code path that calls `trace_view.add_signal()`. Clicks in either sidebar list, drops on the plot, and plot requests from Data analysis and the Advanced page (their `plot_requested` signals) all go through it. Enum and value-table signals, which decode to text labels, branch into `_plot_categorical()`, which plots integer codes and passes the state names as `labels` so the cursors can show them.

### Use the cursors from another page

`TraceView.cursor_range()` returns cursor A and B's times while both are shown, and `TraceView.plot.cursor_pos(key)` returns one cursor's time. Pass these into a new view as callables, as `SessionWidget` does for `DataAnalysisView` and `TabularView`, and listen to `TraceView.cursors_changed` to refresh. Compute values with `core/signal_stats.py` so every page agrees on what a signal's value at a time is.

---

## 6. Testing a UI Change

All UI tests run headless:

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

Existing test files to follow when adding tests for a new UI piece:

| Testing | Reference file |
|---|---|
| Main window: menus, navigation rail, pages, Settings and Developer unlock, themes | `tests/test_main_window.py` |
| `TraceView` (plot, cursors, Plotted signals table) | `tests/test_trace_view.py` |
| Session pages: Important signals drag and drop, Data analysis, Table view | `tests/test_session_pages.py` (stand-in log data, no fixture file needed) |
| Held values and statistics | `tests/test_signal_stats.py` |
| `DevPanel` | `tests/test_dev_panel.py` |
| `PlatformManagerDialog` | `tests/test_platform_manager.py` |
| Help viewer and help manager | `tests/test_help_viewer.py`, `tests/test_help_manager.py` |
| End-to-end flows (open a real log, force-decode, plot) | `tests/test_ui_integration.py` |

**Modal dialogs block headless tests.** `QMessageBox.information`, `warning`, `critical` and `question` wait forever for a click that never comes in an automated run. Every test that triggers one monkeypatches `QMessageBox` for that test only. Follow the same pattern rather than removing the dialog.

**Monkeypatch order matters** when a test uses a shared stub helper (such as `_stub_dialogs()` or the `dialogs` fixture) together with its own patch of the same method: the patch applied last wins. Apply the shared stub first, then the test-specific patch if the test needs to capture what was shown.

---

## 7. Checklist Before Shipping

- [ ] Each new command is one shared `QAction` in the menu bar (and in the page header, if it is a main action).
- [ ] New screens are built from `ui/widgets.py` pieces (cards, rows, variant buttons), with one primary action per screen.
- [ ] Each new config field has a default value and was added to `config/defaults/*.yaml`.
- [ ] New colors and styles come from the active theme, not hardcoded values.
- [ ] Each new "?" help button has a matching `config/defaults/help/<key>.md`.
- [ ] New Developer-only features are reachable only through `DevPanel`.
- [ ] New files have the standard header, and comments follow the style in [§3](#3-conventions).
- [ ] `QT_QPA_PLATFORM=offscreen pytest -q` passes, including a new or updated test for the change.
- [ ] If the change touches schemas in `config_loader.py`, `tests/test_config_loader.py` covers the new or changed field.
