#--------------------#
# test_launcher.py
# tests for launcher.py entry point resolution and the update flow
# main() runs as real subprocesses against a fake install layout
#--------------------#
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

import launcher
from core.config_loader import load_app_settings
from utils.github_updater import ASSET_NAME_PREFIX


# -- resolve_entry_point --

def test_resolve_entry_point_prefers_exe_when_present(tmp_path):
    install_root = tmp_path
    versions_dir = install_root / "versions"
    version_dir = versions_dir / "v1.0.0"
    version_dir.mkdir(parents=True)
    (version_dir / "current.txt")  # not used here
    (versions_dir / "current.txt").write_text("v1.0.0")
    (version_dir / "CANDecoder-app.exe").write_bytes(b"fake-exe")

    exe, args = launcher.resolve_entry_point(install_root, versions_dir)

    assert exe == version_dir / "CANDecoder-app.exe"
    assert args == []


def test_resolve_entry_point_falls_back_to_main_py_unfrozen(tmp_path):
    install_root = tmp_path
    versions_dir = install_root / "versions"
    version_dir = versions_dir / "v1.0.0"
    version_dir.mkdir(parents=True)
    (versions_dir / "current.txt").write_text("v1.0.0")
    (version_dir / "main.py").write_text("print('hi')\n")

    exe, args = launcher.resolve_entry_point(install_root, versions_dir)

    assert exe == Path(sys.executable)
    assert args == [str(version_dir / "main.py")]


# nothing staged in dev, run main.py from the repo root
def test_resolve_entry_point_unfrozen_dev_fallback_no_versions_staged(tmp_path):
    install_root = tmp_path
    versions_dir = install_root / "versions"  # deliberately not created

    exe, args = launcher.resolve_entry_point(install_root, versions_dir)

    assert exe == Path(sys.executable)
    assert args == [str(install_root / "main.py")]


# regression, a frozen launcher with nothing staged used to relaunch itself forever
def test_resolve_entry_point_frozen_with_nothing_staged_raises_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    install_root = tmp_path
    versions_dir = install_root / "versions"
    versions_dir.mkdir()  # exists, but current.txt does not

    with pytest.raises(RuntimeError, match="No application version is installed"):
        launcher.resolve_entry_point(install_root, versions_dir)


def test_resolve_entry_point_frozen_with_empty_current_txt_raises_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    install_root = tmp_path
    versions_dir = install_root / "versions"
    versions_dir.mkdir()
    (versions_dir / "current.txt").write_text("   \n")

    with pytest.raises(RuntimeError, match="No application version is installed"):
        launcher.resolve_entry_point(install_root, versions_dir)


# -- resolve_install_root --

def test_resolve_install_root_unfrozen_is_repo_root():
    root = launcher.resolve_install_root()
    assert (root / "launcher.py").exists()


# -- main(): data root env var and version bump --

_CHILD_SCRIPT = """
import os, sys
print("DATA_ROOT=" + os.environ.get("CAN_DECODER_DATA_ROOT", "<missing>"))
sys.exit(0)
"""


# the child app gets the stable data root through CAN_DECODER_DATA_ROOT
def test_main_propagates_data_root_env_var_to_child(tmp_path, monkeypatch, capfd):
    install_root = tmp_path
    versions_dir = install_root / "versions"
    version_dir = versions_dir / "v1.0.0"
    version_dir.mkdir(parents=True)
    (versions_dir / "current.txt").write_text("v1.0.0")
    child_script = version_dir / "main.py"
    child_script.write_text(_CHILD_SCRIPT)

    # no updater.repo, so check_for_update() does nothing
    exit_code = launcher.main(install_root=install_root)

    out, _ = capfd.readouterr()
    assert exit_code == 0
    assert f"DATA_ROOT={install_root / 'data'}" in out


# regression, settings.version must advance or the same update is offered forever
def test_main_advances_recorded_version_after_immediate_update(tmp_path, monkeypatch, capfd):
    install_root = tmp_path
    data_root = install_root / "data"
    versions_dir = install_root / "versions"
    versions_dir.mkdir(parents=True)

    # stage an initial installed version
    v1_dir = versions_dir / "v1.0.0"
    v1_dir.mkdir(parents=True)
    (v1_dir / "main.py").write_text(_CHILD_SCRIPT)
    (versions_dir / "current.txt").write_text("v1.0.0")

    # build the v2.0.0 release the local feed points at
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    zip_path = asset_dir / f"{ASSET_NAME_PREFIX}v2.0.0.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("main.py", _CHILD_SCRIPT)
    feed_path = tmp_path / "feed.json"
    feed_path.write_text(json.dumps({"tag": "v2.0.0", "asset_path": str(zip_path)}))

    settings_path = data_root / "config" / "settings.yaml"
    settings = load_app_settings(settings_path)
    settings.version = "1.0.0"
    settings.updater.test_mode = True
    settings.updater.local_feed_path = str(feed_path)
    from core.config_loader import save_app_settings
    save_app_settings(settings_path, settings)

    # auto-answer y to the update prompt
    monkeypatch.setattr("builtins.input", lambda *_: "y")

    exit_code = launcher.main(install_root=install_root)
    assert exit_code == 0
    out, _ = capfd.readouterr()
    assert "Downloading v2.0.0  [########################]  100%" in out

    updated_settings = load_app_settings(settings_path)
    assert updated_settings.version == "2.0.0"
    assert (versions_dir / "current.txt").read_text().strip() == "v2.0.0"

    # second run must not prompt again, the version was already advanced
    def _fail_if_called(*_a, **_k):
        raise AssertionError("should not prompt again -- version was not advanced")

    monkeypatch.setattr("builtins.input", _fail_if_called)
    exit_code_2 = launcher.main(install_root=install_root)
    assert exit_code_2 == 0


# regression, a failed download (private repo 404) crashed the launcher before the app started
def test_main_keeps_current_version_when_the_download_fails(tmp_path, monkeypatch, capfd):
    install_root = tmp_path
    versions_dir = install_root / "versions"
    v1_dir = versions_dir / "v1.0.0"
    v1_dir.mkdir(parents=True)
    (v1_dir / "main.py").write_text(_CHILD_SCRIPT)
    (versions_dir / "current.txt").write_text("v1.0.0")

    # the feed points at an asset that doesn't exist, so staging raises
    feed_path = tmp_path / "feed.json"
    feed_path.write_text(json.dumps({"tag": "v2.0.0", "asset_path": str(tmp_path / "missing.zip")}))
    settings_path = install_root / "data" / "config" / "settings.yaml"
    settings = load_app_settings(settings_path)
    settings.version = "1.0.0"
    settings.updater.test_mode = True
    settings.updater.local_feed_path = str(feed_path)
    from core.config_loader import save_app_settings
    save_app_settings(settings_path, settings)
    monkeypatch.setattr("builtins.input", lambda *_: "y")

    exit_code = launcher.main(install_root=install_root)

    out, _ = capfd.readouterr()
    assert exit_code == 0
    assert "Couldn't download v2.0.0" in out
    assert "DATA_ROOT=" in out  # the current version still launched
    assert load_app_settings(settings_path).version == "1.0.0"
    assert (versions_dir / "current.txt").read_text().strip() == "v1.0.0"
    assert not (versions_dir / "v2.0.0").exists()  # no half-staged folder left behind


# -- launcher self-update --

def _staged_version_with_launcher(tmp_path: Path, launcher_bytes: bytes) -> Path:
    version_dir = tmp_path / "versions" / "v2.0.0"
    (version_dir / "launcher").mkdir(parents=True)
    (version_dir / "launcher" / "CANDecoderLauncher.exe").write_bytes(launcher_bytes)
    (version_dir / "CANDecoder-app.exe").write_bytes(b"app")
    return version_dir


def test_update_launcher_swaps_in_the_shipped_launcher(tmp_path):
    running = tmp_path / "CANDecoderLauncher.exe"
    running.write_bytes(b"old launcher")
    version_dir = _staged_version_with_launcher(tmp_path, b"new launcher")

    assert launcher.update_launcher(version_dir, running) is True
    assert running.read_bytes() == b"new launcher"
    assert (tmp_path / "CANDecoderLauncher.exe.old").read_bytes() == b"old launcher"

    # the next start removes the replaced copy
    launcher.remove_old_launcher(running)
    assert not (tmp_path / "CANDecoderLauncher.exe.old").exists()


def test_update_launcher_skips_identical_missing_or_dev_runs(tmp_path):
    running = tmp_path / "CANDecoderLauncher.exe"
    running.write_bytes(b"same")
    version_dir = _staged_version_with_launcher(tmp_path, b"same")

    assert launcher.update_launcher(version_dir, running) is False  # identical
    assert launcher.update_launcher(tmp_path / "nothing", running) is False  # none shipped
    assert launcher.update_launcher(version_dir, None) is False  # running from source
    assert not (tmp_path / "CANDecoderLauncher.exe.old").exists()


# the shipped launcher sits in launcher/, so every launcher still runs the app exe
def test_resolve_entry_point_ignores_the_shipped_launcher(tmp_path):
    version_dir = _staged_version_with_launcher(tmp_path, b"new launcher")
    (tmp_path / "versions" / "current.txt").write_text("v2.0.0")

    executable, _ = launcher.resolve_entry_point(tmp_path, tmp_path / "versions")
    assert executable == version_dir / "CANDecoder-app.exe"


# -- console progress --

def test_console_progress_draws_a_bar_per_phase(capsys):
    progress = launcher.ConsoleProgress("v2.0.0")
    progress("download", 0, None)
    progress("download", 50_000_000, 100_000_000)
    progress("download", 100_000_000, 100_000_000)
    progress("extract", 3, 3)
    progress.finish()

    out = capsys.readouterr().out
    assert "Downloading v2.0.0  0.0 MB" in out
    assert "[############------------]   50%  50.0 / 100.0 MB" in out
    assert " 100%  100.0 / 100.0 MB" in out
    assert "Installing  [########################]  100%  3 / 3 files" in out
    assert out.endswith("\n")  # the last line is closed so later messages start fresh
