# CAN Decoder App

A desktop application for decoding and analyzing CAN bus signals from post-race MDF4 (`.mf4`) vehicle logs. It takes a raw log to plotted signals and a shareable PDF report.

## Features

- **Three access tiers:** Simple, Advanced and Developer modes.
- **MF4 log decoding** against DBC definitions, with force-decode for logs captured outside the expected bus configuration.
- **Graph analysis:** interactive plotting with two cursors that show every signal's value and the change between them, and drag-and-drop Important signals per platform.
- **Data analysis and Table view:** statistics for every signal (whole log or between the cursors), and signals side by side on one time axis with CSV export.
- **PDF report export** of the important signals.
- **Platform Manager:** add or edit vehicle configurations and import `.dbc` files from the UI, with no hand-editing of files.
- **In-app help,** viewable by everyone and editable in Developer Mode.
- **Multi-tab sessions** for comparing several logs, with the open logs shown as tabs above every page.
- **Self-updating:** installed copies check for a new version on launch.

## Quickstart

1. Download `CANDecoder-Setup-<version>.zip` from the [Releases](../../releases) page.
2. Unzip it anywhere.
3. Run `CANDecoderLauncher.exe`.

No installation, Python or terminal is required.

## Basic Usage

| Task | Where |
|---|---|
| Open a log | **Open Log** in the page header, **+** after the session tabs, **File → Open Log…** (Ctrl+O), or drag an `.mf4` file onto the window |
| Switch page | The navigation rail on the left, or **View** (Ctrl+1 Graph analysis, Ctrl+2 Data analysis, Ctrl+3 Table view, Ctrl+4 Advanced) |
| Mark a signal as important | Drag it from **All signals** into **Important signals** on the Graph analysis page |
| Read values off the graph | Click the plot to place cursor A, Shift+click for cursor B |
| Turn on Advanced Mode (adds the Advanced page) | **Settings → Mode**, or **View → Advanced Mode** (Ctrl+Shift+A) |
| Change the theme | **Settings → Appearance**, or **View → Theme** |
| Default Developer Mode password | `changeme` |
| Unlock Developer options | **Settings**, scroll to **Developer options**, then **Unlock…** |
| Change the Developer password | Developer options → **Security** → **Change password** |
| Set the GitHub repo or token | Developer options → **GitHub** → **Edit** |
| Add or edit a vehicle platform | Developer options → **Content** → **Manage platforms…** |
| Edit help content | Developer options → **Content** → **Manage help…** |

## Documentation

| Document | Audience and contents |
|---|---|
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Developers: running from source, project layout, settings reference, testing |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Developers: how each module works and why it was built that way |
| [`docs/UI_GUIDE.md`](docs/UI_GUIDE.md) | Developers: making UI changes, themes and conventions |
| [`docs/DEVELOPER_SETUP.md`](docs/DEVELOPER_SETUP.md) | Maintainers: packaging and publishing releases |
