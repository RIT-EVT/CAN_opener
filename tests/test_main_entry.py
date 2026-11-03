#--------------------#
# test_main_entry.py
# tests for main.py's data root vs code root split and default syncing
# see docs/ARCHITECTURE.md, data root
#--------------------#
from __future__ import annotations

import sys

import main


# -- resolve_data_root --

def test_resolve_data_root_uses_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CAN_DECODER_DATA_ROOT", str(tmp_path))
    assert main.resolve_data_root() == tmp_path


def test_resolve_data_root_falls_back_to_code_root_when_unset(monkeypatch):
    monkeypatch.delenv("CAN_DECODER_DATA_ROOT", raising=False)
    assert main.resolve_data_root() == main._code_root()


# -- _bundled_defaults_dir --

def test_bundled_defaults_dir_unfrozen_is_code_root_relative(tmp_path):
    assert main._bundled_defaults_dir(tmp_path) == tmp_path / "config" / "defaults"


# regression, frozen onedir builds keep bundled data under sys._MEIPASS
def test_bundled_defaults_dir_frozen_uses_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    fake_meipass = tmp_path / "_internal"
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_meipass), raising=False)

    code_root = tmp_path  # e.g. the folder the exe sits in, irrelevant here
    result = main._bundled_defaults_dir(code_root)

    assert result == fake_meipass / "config" / "defaults"


def test_bundled_defaults_dir_frozen_without_meipass_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    result = main._bundled_defaults_dir(tmp_path)
    assert result == tmp_path / "config" / "defaults"


# -- _sync_defaults --

def test_sync_defaults_noop_when_app_root_equals_code_root(tmp_path):
    # no-op in dev even without config/defaults
    main._sync_defaults(tmp_path, tmp_path)


def test_sync_defaults_copies_bundled_defaults_into_data_root(tmp_path):
    code_root = tmp_path / "code"
    app_root = tmp_path / "data"
    defaults_src = code_root / "config" / "defaults"
    defaults_src.mkdir(parents=True)
    (defaults_src / "dark_theme.yaml").write_text("name: dark\n")

    main._sync_defaults(app_root, code_root)

    copied = app_root / "config" / "defaults" / "dark_theme.yaml"
    assert copied.exists()
    assert copied.read_text() == "name: dark\n"


# new bundled defaults replace old ones, user files outside config/defaults are untouched
def test_sync_defaults_overwrites_stale_bundled_defaults_but_not_user_files(tmp_path):
    code_root = tmp_path / "code"
    app_root = tmp_path / "data"
    defaults_src = code_root / "config" / "defaults"
    defaults_src.mkdir(parents=True)
    (defaults_src / "dark_theme.yaml").write_text("name: dark-v2\n")

    # a stale bundled default plus unrelated user data
    existing_defaults = app_root / "config" / "defaults"
    existing_defaults.mkdir(parents=True)
    (existing_defaults / "dark_theme.yaml").write_text("name: dark-v1\n")
    user_platform = app_root / "config" / "platforms" / "my_car.yaml"
    user_platform.parent.mkdir(parents=True)
    user_platform.write_text("name: My Car\ndbc_path: my_car.dbc\n")

    main._sync_defaults(app_root, code_root)

    assert (existing_defaults / "dark_theme.yaml").read_text() == "name: dark-v2\n"
    assert user_platform.read_text() == "name: My Car\ndbc_path: my_car.dbc\n"
