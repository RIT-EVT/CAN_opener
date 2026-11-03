#--------------------#
# launcher.py
# permanent entry point, checks for updates then starts the current app version
# see docs/ARCHITECTURE.md, launcher
#--------------------#
from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from core.config_loader import load_app_settings, save_app_settings
from utils.github_updater import LAUNCHER_DIR, GithubUpdater


# -- paths --

# folder the launcher lives in, data/ and versions/ sit beside it
def resolve_install_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# what to run: the staged exe, a staged main.py, or the repo main.py in dev
# a frozen launcher with nothing staged raises instead of relaunching itself forever
def resolve_entry_point(install_root: Path, versions_dir: Path) -> Tuple[Path, List[str]]:
    current_file = versions_dir / "current.txt"
    if current_file.exists():
        tag = current_file.read_text().strip()
        if tag:
            version_dir = versions_dir / tag
            exe_candidates = sorted(version_dir.glob("*.exe"))
            if exe_candidates:
                return exe_candidates[0], []
            main_py = version_dir / "main.py"
            if main_py.exists():
                return Path(sys.executable), [str(main_py)]

    if getattr(sys, "frozen", False):
        raise RuntimeError(
            "No application version is installed "
            "(versions/current.txt is missing or empty). Reinstall CAN Decoder."
        )
    # unfrozen dev fallback
    return Path(sys.executable), [str(install_root / "main.py")]


# -- launcher self-update (see docs/ARCHITECTURE.md, launcher) --

# the running launcher exe, or nothing for a dev run from source
def _running_launcher() -> Optional[Path]:
    return Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None


def _old_copy(launcher: Path) -> Path:
    return launcher.with_name(launcher.name + ".old")


# swaps in the launcher a staged version ships with, windows allows renaming a running exe
# returns true if it was replaced, a failed copy puts the original back
def update_launcher(version_dir: Path, launcher: Optional[Path]) -> bool:
    if launcher is None:
        return False
    shipped = next((version_dir / LAUNCHER_DIR).glob("*.exe"), None)
    if shipped is None or filecmp.cmp(shipped, launcher, shallow=False):
        return False
    old = _old_copy(launcher)
    try:
        old.unlink(missing_ok=True)
        launcher.rename(old)
        shutil.copy2(shipped, launcher)
    except OSError as exc:
        if not launcher.exists() and old.exists():
            old.rename(launcher)
        print(f"Couldn't update the launcher: {exc}")
        return False
    return True


# the replaced launcher can only be deleted once it has stopped running
def remove_old_launcher(launcher: Optional[Path]) -> None:
    if launcher is None:
        return
    try:
        _old_copy(launcher).unlink(missing_ok=True)
    except OSError:
        pass  # still locked, try again next start


# -- console progress --

# one self-overwriting console line per phase, for example
# Downloading v1.1.2  [############------------]   52%  61.2 / 117.9 MB
class ConsoleProgress:
    BAR_WIDTH = 24

    def __init__(self, tag: str):
        self.tag = tag
        self._phase: Optional[str] = None
        self._last: Optional[str] = None

    def __call__(self, phase: str, done: int, total: Optional[int]) -> None:
        if phase != self._phase:
            self.finish()
            self._phase = phase
        line = self._line(phase, done, total)
        if line != self._last:  # only redraw when the text changes
            print("\r" + line, end="", flush=True)
            self._last = line

    def _line(self, phase: str, done: int, total: Optional[int]) -> str:
        if phase == "download":
            label = f"Downloading {self.tag}"
            amount = f"{done / 1e6:.1f} / {total / 1e6:.1f} MB" if total else f"{done / 1e6:.1f} MB"
        else:
            label, amount = "Installing", f"{done} / {total} files"
        if not total:
            return f"{label}  {amount}"
        filled = self.BAR_WIDTH * done // total
        bar = "#" * filled + "-" * (self.BAR_WIDTH - filled)
        return f"{label}  [{bar}]  {done / total:4.0%}  {amount}"

    # ends the current line so the next message starts on its own
    def finish(self) -> None:
        if self._last is not None:
            print()
        self._last = None


# console prompt for now, a gui dialog could replace it later
def _prompt_update(tag: str) -> str:
    print(f"A new version ({tag}) is available.")
    return input("Update now and restart? [y/N/queue]: ").strip().lower()


# -- launch flow --

# stages a release, records it and swaps in its launcher
# a failed download prints why and returns false so the current version still launches
def _apply_update(updater: GithubUpdater, release, settings, settings_path: Path,
                  launcher: Optional[Path]) -> bool:
    progress = ConsoleProgress(release.tag)
    progress("download", 0, None)  # shows the line straight away, before the first chunk
    try:
        version_dir = updater.download_and_stage(release, progress)
    except Exception as exc:
        progress.finish()
        print(f"Couldn't download {release.tag}: {exc}")
        print("Keeping the current version.")
        return False
    progress.finish()
    updater.set_current_pointer(version_dir)
    # record the new version or the next launch offers the same update again
    settings.version = release.tag.lstrip("v")
    save_app_settings(settings_path, settings)
    if update_launcher(version_dir, launcher):
        print("Launcher updated, the new one runs from the next start.")
    return True


def main(install_root: Optional[Path] = None) -> int:
    if install_root is None:
        install_root = resolve_install_root()

    data_root = install_root / "data"
    versions_dir = install_root / "versions"
    data_root.mkdir(parents=True, exist_ok=True)
    versions_dir.mkdir(parents=True, exist_ok=True)
    launcher = _running_launcher()
    remove_old_launcher(launcher)

    settings_path = data_root / "config" / "settings.yaml"
    settings = load_app_settings(settings_path)
    updater = GithubUpdater.from_settings(settings, versions_dir)

    # update check (never raises, gives nothing back when offline)
    release = updater.check_for_update()
    already_queued = updater.pending_queued_release()

    if release is not None and already_queued is None:
        choice = _prompt_update(release.tag)
        if choice == "y":
            if _apply_update(updater, release, settings, settings_path, launcher):
                print(f"Updated to {release.tag}. Launching...")
        elif choice == "queue":
            updater.queue_update(release)
            print(f"Update to {release.tag} queued for after this session exits.")

    try:
        executable, args = resolve_entry_point(install_root, versions_dir)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return 1

    # run the app, the data root is passed by env var since it may be another version's code
    env = os.environ.copy()
    env["CAN_DECODER_DATA_ROOT"] = str(data_root)
    exit_code = subprocess.call([str(executable), *args], env=env)

    # apply a queued update now that the app has exited, a failed one stays queued for next time
    queued = updater.pending_queued_release()
    if queued is not None and _apply_update(updater, queued, settings, settings_path, launcher):
        updater.clear_queued_release()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
