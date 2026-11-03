#--------------------#
# build_release.py
# packs the pyinstaller output into the setup zip and the app-only update zip
# run: python packaging/build_release.py v1.2.0
# see docs/DEVELOPER_SETUP.md, build the release artifacts
#--------------------#
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# run as a plain script, so put the repo root on the path for the imports below
sys.path.insert(0, str(REPO_ROOT))

import yaml

from core.config_loader import bootstrap_settings
from utils.github_updater import ASSET_NAME_PREFIX, LAUNCHER_DIR  # noqa: E402

DIST_DIR = REPO_ROOT / "dist"
RELEASE_DIR = DIST_DIR / "release"

LAUNCHER_EXE = DIST_DIR / "CANDecoderLauncher.exe"
APP_DIR = DIST_DIR / "CANDecoder-app"
SETTINGS_TEMPLATE = REPO_ROOT / "config" / "settings_template.yaml"


# arc_prefix is the folder inside the zip, blank puts the files at the zip root
def _zip_dir(zf: zipfile.ZipFile, src_dir: Path, arc_prefix: str = "") -> None:
    for path in src_dir.rglob("*"):
        if path.is_file():
            zf.write(path, Path(arc_prefix) / path.relative_to(src_dir))


# -- app-only update zip --

# contents sit at the zip root since the updater extracts straight into versions/<tag>/
# the launcher rides along in launcher/ so installs can replace their own launcher
def build_app_zip(tag: str) -> Path:
    if not APP_DIR.exists():
        raise SystemExit(f"Missing build output: {APP_DIR}. Run PyInstaller with build.spec first.")
    if not LAUNCHER_EXE.exists():
        raise SystemExit(f"Missing build output: {LAUNCHER_EXE}. Run PyInstaller with launcher.spec first.")

    out_path = RELEASE_DIR / f"{ASSET_NAME_PREFIX}{tag}.zip"
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        _zip_dir(zf, APP_DIR)
        zf.write(LAUNCHER_EXE, f"{LAUNCHER_DIR}/{LAUNCHER_EXE.name}")
    return out_path


# -- baked settings --

def _load_settings_template() -> dict:
    if not SETTINGS_TEMPLATE.exists():
        return {}
    return yaml.safe_load(SETTINGS_TEMPLATE.read_text()) or {}


# settings.yaml for a fresh install, update source from the template plus the real version
# see docs/ARCHITECTURE.md, settings bootstrap
def build_baked_settings_yaml(tag: str) -> str:
    template = _load_settings_template()
    updater = template.get("updater") or {}
    if updater.get("test_mode") is False and not updater.get("repo"):
        print(
            f"WARNING: {SETTINGS_TEMPLATE} has test_mode: false "
            "but no repo set -- the shipped app will never check for updates. "
            "Fill in `updater.repo` before releasing."
        )
    settings = bootstrap_settings(template=template, version=tag.lstrip("v"))
    return yaml.safe_dump(settings.model_dump(), sort_keys=False)


# -- first install setup zip --

# launcher, this version pre-staged with current.txt, and the baked settings.yaml
def build_setup_zip(tag: str) -> Path:
    if not LAUNCHER_EXE.exists():
        raise SystemExit(f"Missing build output: {LAUNCHER_EXE}. Run PyInstaller with launcher.spec first.")
    if not APP_DIR.exists():
        raise SystemExit(f"Missing build output: {APP_DIR}. Run PyInstaller with build.spec first.")

    out_path = RELEASE_DIR / f"CANDecoder-Setup-{tag}.zip"
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(LAUNCHER_EXE, LAUNCHER_EXE.name)
        _zip_dir(zf, APP_DIR, f"versions/{tag}")
        zf.writestr("versions/current.txt", tag)
        zf.writestr("data/config/settings.yaml", build_baked_settings_yaml(tag))
    return out_path


# -- cli --

def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python packaging/build_release.py <tag>  (e.g. v1.2.0)")
        return 1
    tag = sys.argv[1]

    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)

    app_zip = build_app_zip(tag)
    setup_zip = build_setup_zip(tag)

    print("Built release assets:")
    print(f"  {app_zip}")
    print(f"  {setup_zip}")
    print()
    print(f"Attach both to a GitHub release tagged '{tag}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
