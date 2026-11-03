#--------------------#
# test_github_updater.py
# tests for the auto updater: asset choice, staging, test feed cycle and queueing
# regression history in docs/DEVELOPER_SETUP.md, resolved issues
#--------------------#
from __future__ import annotations

import io
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from core.config_loader import AppSettings, UpdaterSettings
from utils.github_updater import ASSET_NAME_PREFIX, GithubUpdater, ReleaseInfo


def _make_updater(tmp_path: Path, **kwargs) -> GithubUpdater:
    versions_dir = tmp_path / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    defaults = dict(
        repo="",
        current_version="0.1.0",
        versions_dir=versions_dir,
        test_mode=True,
    )
    defaults.update(kwargs)
    return GithubUpdater(**defaults)


# -- asset selection --

# releases carry both zips, the app-only one must win over assets[0]
def test_select_app_asset_prefers_prefixed_name():
    assets = [
        {"name": "CANDecoder-Setup-v1.2.0.zip", "browser_download_url": "http://x/setup.zip"},
        {"name": f"{ASSET_NAME_PREFIX}v1.2.0.zip", "browser_download_url": "http://x/app.zip"},
    ]
    selected = GithubUpdater._select_app_asset(assets)
    assert selected["name"] == f"{ASSET_NAME_PREFIX}v1.2.0.zip"


def test_select_app_asset_falls_back_to_first_when_no_match():
    assets = [{"name": "something-else.zip", "browser_download_url": "http://x/y.zip"}]
    selected = GithubUpdater._select_app_asset(assets)
    assert selected["name"] == "something-else.zip"


def test_select_app_asset_empty_list_returns_none():
    assert GithubUpdater._select_app_asset([]) is None


# -- download_and_stage: zip extraction --

# regression, the zip used to be downloaded but never extracted
def test_download_and_stage_extracts_zip_contents(tmp_path):
    updater = _make_updater(tmp_path)

    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    zip_path = asset_dir / f"{ASSET_NAME_PREFIX}v1.0.0.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("main.py", "print('hello')\n")
        zf.writestr("config/defaults/dark_theme.yaml", "name: dark\n")

    release = ReleaseInfo(tag="v1.0.0", asset_url=str(zip_path))
    version_dir = updater.download_and_stage(release)

    assert (version_dir / "main.py").exists()
    assert (version_dir / "config" / "defaults" / "dark_theme.yaml").exists()
    # the archive itself is removed after extracting
    assert not any(p.suffix == ".zip" for p in version_dir.iterdir())


# extractall drops unix exec bits, they must be restored (meaningless on windows)
def test_download_and_stage_restores_executable_permission_bits(tmp_path):
    updater = _make_updater(tmp_path)

    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    zip_path = asset_dir / f"{ASSET_NAME_PREFIX}v1.0.0.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        info = zipfile.ZipInfo("run.sh")
        info.external_attr = (0o755 & 0xFFFF) << 16
        zf.writestr(info, "#!/bin/sh\necho hi\n")

    release = ReleaseInfo(tag="v1.0.0", asset_url=str(zip_path))
    version_dir = updater.download_and_stage(release)

    mode = stat.S_IMODE(os.stat(version_dir / "run.sh").st_mode)
    assert mode & stat.S_IXUSR


# a non-zip asset is copied in as-is
def test_download_and_stage_non_zip_asset_left_as_is(tmp_path):
    updater = _make_updater(tmp_path)
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    lone_file = asset_dir / "readme.txt"
    lone_file.write_text("hi")

    release = ReleaseInfo(tag="v1.0.0", asset_url=str(lone_file))
    version_dir = updater.download_and_stage(release)

    assert (version_dir / "readme.txt").read_text() == "hi"


# -- full check, stage, pointer cycle through the local test feed --

# whole pipeline minus the network: detect, stage and point at a newer local release
def test_full_update_cycle_via_local_feed(tmp_path):
    versions_dir = tmp_path / "versions"
    versions_dir.mkdir()

    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    zip_path = asset_dir / f"{ASSET_NAME_PREFIX}v2.0.0.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("main.py", "print('v2')\n")

    feed_path = tmp_path / "feed.json"
    feed_path.write_text(json.dumps({"tag": "v2.0.0", "asset_path": str(zip_path)}))

    updater = GithubUpdater(
        repo="",
        current_version="1.0.0",
        versions_dir=versions_dir,
        test_mode=True,
        local_feed_path=feed_path,
    )

    release = updater.check_for_update()
    assert release is not None
    assert release.tag == "v2.0.0"

    version_dir = updater.download_and_stage(release)
    updater.set_current_pointer(version_dir)

    assert (version_dir / "main.py").exists()
    assert (versions_dir / "current.txt").read_text().strip() == "v2.0.0"


def test_check_for_update_returns_none_when_not_newer(tmp_path):
    versions_dir = tmp_path / "versions"
    versions_dir.mkdir()
    feed_path = tmp_path / "feed.json"
    feed_path.write_text(json.dumps({"tag": "v1.0.0", "asset_path": "/dev/null"}))

    updater = GithubUpdater(
        repo="", current_version="1.0.0", versions_dir=versions_dir,
        test_mode=True, local_feed_path=feed_path,
    )
    assert updater.check_for_update() is None


# a broken or offline check must never block launch
def test_check_for_update_never_raises_on_missing_feed(tmp_path):
    versions_dir = tmp_path / "versions"
    versions_dir.mkdir()
    updater = GithubUpdater(
        repo="", current_version="1.0.0", versions_dir=versions_dir,
        test_mode=True, local_feed_path=tmp_path / "does_not_exist.json",
    )
    assert updater.check_for_update() is None


def test_from_settings_round_trip(tmp_path):
    settings = AppSettings(
        version="1.0.0",
        updater=UpdaterSettings(repo="octocat/hello-world", test_mode=True, local_feed_path=None),
    )
    updater = GithubUpdater.from_settings(settings, tmp_path / "versions")
    assert updater.repo == "octocat/hello-world"
    assert updater.current_version == "1.0.0"
    assert updater.test_mode is True


# -- queueing --

def test_queue_and_clear_release(tmp_path):
    updater = _make_updater(tmp_path)
    release = ReleaseInfo(tag="v1.5.0", asset_url="http://x/y.zip")

    assert updater.pending_queued_release() is None
    updater.queue_update(release)
    queued = updater.pending_queued_release()
    assert queued is not None
    assert queued.tag == "v1.5.0"

    updater.clear_queued_release()
    assert updater.pending_queued_release() is None


# -- private repos (github api downloads) --

class _FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, content_length=None):
        super().__init__(body)
        self.headers = {"Content-Length": str(content_length)} if content_length else {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _capture_urlopen(monkeypatch, body: bytes, content_length=None) -> list:
    import utils.github_updater as gu
    requests_seen = []

    def fake_urlopen(request, timeout=None):
        requests_seen.append(request)
        return _FakeResponse(body, content_length)

    monkeypatch.setattr(gu.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gu, "get_github_token", lambda: "tok123")
    return requests_seen


# the release check keeps the api asset url, which is the only one a private repo serves
def test_fetch_latest_release_keeps_api_url_and_sends_token(tmp_path, monkeypatch):
    release_json = json.dumps({"tag_name": "v2.0.0", "assets": [{
        "name": f"{ASSET_NAME_PREFIX}v2.0.0.zip",
        "browser_download_url": f"https://github.com/o/r/releases/download/v2.0.0/{ASSET_NAME_PREFIX}v2.0.0.zip",
        "url": "https://api.github.com/repos/o/r/releases/assets/42",
    }]}).encode()
    seen = _capture_urlopen(monkeypatch, release_json)
    updater = _make_updater(tmp_path, repo="o/r", test_mode=False)

    release = updater.check_for_update()

    assert release.api_url == "https://api.github.com/repos/o/r/releases/assets/42"
    assert seen[0].get_header("Authorization") == "Bearer tok123"


# regression, the plain download link 404s for private repos, and the token must not
# follow github's redirect to the file host (unredirected header)
def test_download_uses_api_url_with_unredirected_token(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("CANDecoder-app.exe", b"fake exe")
    seen = _capture_urlopen(monkeypatch, buffer.getvalue())
    updater = _make_updater(tmp_path, repo="o/r", test_mode=False)
    release = ReleaseInfo(
        tag="v2.0.0",
        asset_url=f"https://github.com/o/r/releases/download/v2.0.0/{ASSET_NAME_PREFIX}v2.0.0.zip",
        api_url="https://api.github.com/repos/o/r/releases/assets/42",
    )

    target = updater.download_and_stage(release)

    request = seen[0]
    assert request.full_url == release.api_url
    assert request.get_header("Accept") == "application/octet-stream"
    assert request.unredirected_hdrs.get("Authorization") == "Bearer tok123"
    assert "Authorization" not in request.headers  # would be forwarded on redirect
    assert (target / "CANDecoder-app.exe").read_bytes() == b"fake exe"
    assert not (target / f"{ASSET_NAME_PREFIX}v2.0.0.zip").exists()


def test_failed_download_removes_the_half_staged_folder(tmp_path, monkeypatch):
    import utils.github_updater as gu

    def fail(*_a, **_k):
        raise OSError("HTTP Error 404: Not Found")

    monkeypatch.setattr(gu.urllib.request, "urlopen", fail)
    monkeypatch.setattr(gu, "get_github_token", lambda: None)
    updater = _make_updater(tmp_path, repo="o/r", test_mode=False)
    release = ReleaseInfo(tag="v2.0.0", asset_url="https://github.com/o/r/x.zip")

    with pytest.raises(OSError):
        updater.download_and_stage(release)
    assert not (updater.versions_dir / "v2.0.0").exists()


# queue files written by older launchers have no api_url
def test_legacy_queue_file_without_api_url_still_loads(tmp_path):
    updater = _make_updater(tmp_path)
    (updater.versions_dir / "queued_update.json").write_text(
        json.dumps({"tag": "v2.0.0", "asset_url": "https://github.com/o/r/x.zip"})
    )
    queued = updater.pending_queued_release()
    assert queued.tag == "v2.0.0" and queued.api_url is None


# -- progress reporting --

# the launcher's progress bar is driven by these calls, byte counts then file counts
def test_download_and_stage_reports_download_and_extract_progress(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("CANDecoder-app.exe", b"x" * 1000)
        zf.writestr("_internal/lib.dll", b"y" * 1000)
    body = buffer.getvalue()
    _capture_urlopen(monkeypatch, body, content_length=len(body))
    updater = _make_updater(tmp_path, repo="o/r", test_mode=False)
    release = ReleaseInfo(tag="v2.0.0", asset_url="https://github.com/o/r/app.zip",
                          api_url="https://api.github.com/repos/o/r/releases/assets/1")
    calls = []

    updater.download_and_stage(release, progress=lambda *args: calls.append(args))

    downloads = [c for c in calls if c[0] == "download"]
    extracts = [c for c in calls if c[0] == "extract"]
    assert downloads[-1] == ("download", len(body), len(body))
    assert extracts == [("extract", 1, 2), ("extract", 2, 2)]


# no Content-Length header, the total is reported as unknown instead of guessed
def test_progress_total_is_none_without_content_length(tmp_path, monkeypatch):
    _capture_urlopen(monkeypatch, b"not a zip")
    updater = _make_updater(tmp_path, repo="o/r", test_mode=False)
    release = ReleaseInfo(tag="v2.0.0", asset_url="https://github.com/o/r/notes.txt")
    calls = []

    updater.download_and_stage(release, progress=lambda *args: calls.append(args))

    assert calls == [("download", 9, None)]


# a failed stage never deletes the version that is currently running
def test_failed_stage_keeps_the_running_versions_folder(tmp_path, monkeypatch):
    import utils.github_updater as gu

    def fail(*_a, **_k):
        raise OSError("offline")

    monkeypatch.setattr(gu.urllib.request, "urlopen", fail)
    monkeypatch.setattr(gu, "get_github_token", lambda: None)
    updater = _make_updater(tmp_path, repo="o/r", test_mode=False)
    running = updater.versions_dir / "v1.0.0"
    running.mkdir()
    (running / "CANDecoder-app.exe").write_bytes(b"app")
    (updater.versions_dir / "current.txt").write_text("v1.0.0")

    with pytest.raises(OSError):
        updater.download_and_stage(ReleaseInfo(tag="v1.0.0", asset_url="https://github.com/o/r/x.zip"))
    assert (running / "CANDecoder-app.exe").exists()
