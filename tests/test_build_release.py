#--------------------#
# test_build_release.py
# tests for the release builder and the settings.yaml baked into the setup zip
#--------------------#
from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


# loaded by path, the repo's packaging/ folder clashes with the pip packaging library
def _load_build_release():
    spec = importlib.util.spec_from_file_location(
        "can_decoder_build_release", REPO_ROOT / "packaging" / "build_release.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_release = _load_build_release()


# points every build path at tmp_path so the real dist/ is never touched
@pytest.fixture(autouse=True)
def _isolated_dist(tmp_path, monkeypatch):
    monkeypatch.setattr(build_release, "DIST_DIR", tmp_path / "dist")
    monkeypatch.setattr(build_release, "RELEASE_DIR", tmp_path / "dist" / "release")
    monkeypatch.setattr(build_release, "LAUNCHER_EXE", tmp_path / "dist" / "CANDecoderLauncher.exe")
    monkeypatch.setattr(build_release, "APP_DIR", tmp_path / "dist" / "CANDecoder-app")
    monkeypatch.setattr(build_release, "SETTINGS_TEMPLATE", tmp_path / "settings_template.yaml")
    yield


def _stage_fake_build(tmp_path):
    build_release.LAUNCHER_EXE.parent.mkdir(parents=True, exist_ok=True)
    build_release.LAUNCHER_EXE.write_bytes(b"fake-launcher")
    build_release.APP_DIR.mkdir(parents=True, exist_ok=True)
    (build_release.APP_DIR / "CANDecoder-app.exe").write_bytes(b"fake-app")


def test_baked_settings_yaml_defaults_to_safe_no_op_without_template():
    # no template file, same defaults as a plain dev run
    text = build_release.build_baked_settings_yaml("v1.0.0")
    data = yaml.safe_load(text)

    assert data["updater"]["repo"] == ""
    assert data["updater"]["test_mode"] is True
    assert data["version"] == "1.0.0"


def test_baked_settings_yaml_applies_template_and_strips_v_prefix():
    build_release.SETTINGS_TEMPLATE.write_text(
        "updater:\n  repo: acme/can-decoder\n  test_mode: false\n"
    )
    text = build_release.build_baked_settings_yaml("v2.3.1")
    data = yaml.safe_load(text)

    assert data["updater"]["repo"] == "acme/can-decoder"
    assert data["updater"]["test_mode"] is False
    assert data["version"] == "2.3.1"
    # a fresh dev password hash is always present
    assert data["dev_password_hash"]


def test_baked_settings_yaml_warns_on_test_mode_false_with_no_repo(capsys):
    build_release.SETTINGS_TEMPLATE.write_text("updater:\n  test_mode: false\n")
    build_release.build_baked_settings_yaml("v1.0.0")
    assert "WARNING" in capsys.readouterr().out


def test_setup_zip_bakes_settings_yaml_with_real_version(tmp_path):
    _stage_fake_build(tmp_path)
    build_release.SETTINGS_TEMPLATE.write_text(
        "updater:\n  repo: acme/can-decoder\n  test_mode: false\n"
    )

    out_path = build_release.build_setup_zip("v1.5.0")

    with zipfile.ZipFile(out_path) as zf:
        assert "data/config/settings.yaml" in zf.namelist()
        data = yaml.safe_load(zf.read("data/config/settings.yaml"))

    assert data["updater"]["repo"] == "acme/can-decoder"
    assert data["updater"]["test_mode"] is False
    # fresh installs report the real version, not the 0.1.0 default
    assert data["version"] == "1.5.0"


# the app zip carries the launcher in launcher/, so the only exe at its root is the app
def test_app_zip_ships_the_launcher_in_a_subfolder(tmp_path):
    _stage_fake_build(tmp_path)

    out_path = build_release.build_app_zip("v1.5.0")

    with zipfile.ZipFile(out_path) as zf:
        names = zf.namelist()
        assert zf.read("launcher/CANDecoderLauncher.exe") == b"fake-launcher"
    assert [n for n in names if n.endswith(".exe") and "/" not in n] == ["CANDecoder-app.exe"]
