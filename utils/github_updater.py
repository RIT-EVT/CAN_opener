#--------------------#
# github_updater.py
# end-user auto update from github releases into versioned folders
# see docs/ARCHITECTURE.md, auto update
#--------------------#
from __future__ import annotations

import json
import os
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from packaging.version import InvalidVersion, Version

from core.config_loader import AppSettings
from utils.keyring_bridge import get_github_token

# filename prefix of the app-only release zip (the setup zip ships in the same release)
ASSET_NAME_PREFIX = "CANDecoder-app-"
# folder inside the app zip that carries the launcher exe, a subfolder so older
# launchers (which run the first *.exe in versions/<tag>/) never pick it
LAUNCHER_DIR = "launcher"

# progress(phase, done, total), phase is "download" (bytes) or "extract" (files)
# total is None when the server sends no size
Progress = Callable[[str, int, Optional[int]], None]
_CHUNK = 256 * 1024


# stdlib http keeps the launcher small, urlopen raises HTTPError on 4xx/5xx
# the token is unredirected so it never follows github's redirect to the file host
# see docs/ARCHITECTURE.md, auto update
def _http_get(url: str, accept: str, timeout: float = 30):
    request = urllib.request.Request(url, headers={"Accept": accept})
    token = get_github_token()
    if token:
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(request, timeout=timeout)


# asset_url is the browser link (or a local path in test_mode), api_url is the
# api endpoint that also works for private repos
@dataclass
class ReleaseInfo:
    tag: str
    asset_url: str
    api_url: Optional[str] = None


class GithubUpdater:
    def __init__(self, repo: str, current_version: str, versions_dir: Path,
                 test_mode: bool = False, local_feed_path: Optional[Path] = None):
        self.repo = repo
        self.current_version = current_version
        self.versions_dir = versions_dir
        self.test_mode = test_mode
        self.local_feed_path = local_feed_path
        self._queue_file = versions_dir / "queued_update.json"

    @classmethod
    def from_settings(cls, settings: AppSettings, versions_dir: Path) -> "GithubUpdater":
        feed = Path(settings.updater.local_feed_path) if settings.updater.local_feed_path else None
        return cls(
            repo=settings.updater.repo,
            current_version=settings.version,
            versions_dir=versions_dir,
            test_mode=settings.updater.test_mode,
            local_feed_path=feed,
        )

    # -- checking --

    # returns a newer release or nothing, never raises so an offline check can't block launch
    def check_for_update(self) -> Optional[ReleaseInfo]:
        if not self.repo and not self.test_mode:
            return None
        try:
            latest = self._fetch_local_feed() if self.test_mode else self._fetch_latest_release()
        except Exception:
            return None
        if latest is None:
            return None
        try:
            if Version(latest.tag.lstrip("v")) <= Version(self.current_version):
                return None
        except InvalidVersion:
            return None
        return latest

    def _fetch_latest_release(self) -> Optional[ReleaseInfo]:
        with _http_get(f"https://api.github.com/repos/{self.repo}/releases/latest",
                       "application/vnd.github+json", timeout=5) as resp:
            data = json.load(resp)
        asset = self._select_app_asset(data.get("assets", []))
        if asset is None:
            return None
        return ReleaseInfo(tag=data["tag_name"], asset_url=asset["browser_download_url"],
                           api_url=asset.get("url"))

    # picks the app-only zip by name, falls back to the first asset
    @staticmethod
    def _select_app_asset(assets: list[dict]) -> Optional[dict]:
        for asset in assets:
            if asset.get("name", "").startswith(ASSET_NAME_PREFIX):
                return asset
        return assets[0] if assets else None

    # test_mode feed, a local json file with tag and asset_path
    def _fetch_local_feed(self) -> Optional[ReleaseInfo]:
        if not self.local_feed_path or not self.local_feed_path.exists():
            return None
        data = json.loads(self.local_feed_path.read_text())
        return ReleaseInfo(tag=data["tag"], asset_url=data["asset_path"])

    # -- staging --

    # downloads (or copies in test_mode) into versions/<tag>/ and extracts the zip there
    # progress is reported through the optional callback (see Progress above)
    # a failure removes the half-staged folder, never the running version's, and re-raises
    def download_and_stage(self, release: ReleaseInfo, progress: Optional[Progress] = None) -> Path:
        target_dir = self.versions_dir / release.tag
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            downloaded = self._fetch_asset(release, target_dir, progress)
            if downloaded.suffix == ".zip":
                _extract(downloaded, target_dir, progress)
                downloaded.unlink()
        except Exception:
            if release.tag != self._current_tag():
                shutil.rmtree(target_dir, ignore_errors=True)
            raise
        return target_dir

    def _current_tag(self) -> str:
        pointer = self.versions_dir / "current.txt"
        return pointer.read_text().strip() if pointer.exists() else ""

    # api download when the release lists one (needed for private repos), else the plain link
    # streamed to disk in chunks so the zip is never held in memory
    def _fetch_asset(self, release: ReleaseInfo, target_dir: Path,
                     progress: Optional[Progress]) -> Path:
        if self.test_mode:
            src = Path(release.asset_url)
            downloaded = target_dir / src.name
            source, total = src.open("rb"), src.stat().st_size
        else:
            downloaded = target_dir / release.asset_url.split("/")[-1]
            if release.api_url:
                source = _http_get(release.api_url, "application/octet-stream")
            else:
                source = _http_get(release.asset_url, "*/*")
            length = source.headers.get("Content-Length")
            total = int(length) if length else None
        with source, downloaded.open("wb") as out:
            done = 0
            while chunk := source.read(_CHUNK):
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress("download", done, total)
        return downloaded

    # points versions/current.txt at the staged folder
    def set_current_pointer(self, version_dir: Path) -> None:
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        (self.versions_dir / "current.txt").write_text(version_dir.name)

    # -- queued updates (applied after the app exits) --

    def queue_update(self, release: ReleaseInfo) -> None:
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self._queue_file.write_text(json.dumps(
            {"tag": release.tag, "asset_url": release.asset_url, "api_url": release.api_url}
        ))

    # queue files written by older launchers have no api_url
    def pending_queued_release(self) -> Optional[ReleaseInfo]:
        if not self._queue_file.exists():
            return None
        data = json.loads(self._queue_file.read_text())
        return ReleaseInfo(tag=data["tag"], asset_url=data["asset_url"], api_url=data.get("api_url"))

    def clear_queued_release(self) -> None:
        if self._queue_file.exists():
            self._queue_file.unlink()


# extracts one file at a time so progress can count files
def _extract(archive: Path, target_dir: Path, progress: Optional[Progress]) -> None:
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()
        for count, info in enumerate(members, start=1):
            zf.extract(info, target_dir)
            if progress:
                progress("extract", count, len(members))
        # extraction drops unix exec bits, restore them (no-op on windows)
        if os.name != "nt":
            for info in members:
                perms = (info.external_attr >> 16) & 0o777
                extracted = target_dir / info.filename
                if perms and extracted.exists():
                    extracted.chmod(perms)
