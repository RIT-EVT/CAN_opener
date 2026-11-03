#--------------------#
# config_loader.py
# pydantic schemas and yaml load/save for platforms, themes and app settings
#--------------------#
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Union

import bcrypt
import yaml
from pydantic import BaseModel, Field, ValidationError

from utils.file_utils import atomic_write_text

DEFAULT_DEV_PASSWORD = "changeme"


# -- password hashing (bcrypt, see docs/ARCHITECTURE.md) --

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False  # malformed or legacy hash


# raised when a yaml config file fails to load or validate
class ConfigLoadError(Exception):
    pass


# -- platform configs (config/platforms/*.yaml) --

class PlatformConfig(BaseModel):
    name: str
    description: str = ""
    dbc_path: str  # filename inside dbc_store/
    image: Optional[str] = None
    important_values: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


def load_platform_config(path: Path) -> PlatformConfig:
    return _load_yaml_model(path, PlatformConfig)


def save_platform_config(path: Path, config: PlatformConfig) -> None:
    atomic_write_text(path, yaml.safe_dump(config.model_dump(), sort_keys=False))


# returns {slug: config or error} so one bad file shows as a warning instead of a crash
def discover_platforms(platforms_dir: Path) -> dict[str, Union[PlatformConfig, ConfigLoadError]]:
    result: dict[str, Union[PlatformConfig, ConfigLoadError]] = {}
    if not platforms_dir.exists():
        return result
    for f in sorted(platforms_dir.glob("*.yaml")):
        try:
            result[f.stem] = load_platform_config(f)
        except ConfigLoadError as exc:
            result[f.stem] = exc
    return result


# -- theme configs (config/themes/*.yaml) --

class ThemeColors(BaseModel):
    background: str
    surface: str
    text: str
    accent: str
    border: str
    error: str = "#e05a4e"
    plot_palette: list[str] = Field(default_factory=list)


class ThemeConfig(BaseModel):
    name: str
    mode: str = "custom"  # light, dark or custom
    font_scale: float = 1.0
    colors: ThemeColors


def load_theme_config(path: Path) -> ThemeConfig:
    return _load_yaml_model(path, ThemeConfig)


def discover_themes(themes_dir: Path) -> dict[str, Union[ThemeConfig, ConfigLoadError]]:
    result: dict[str, Union[ThemeConfig, ConfigLoadError]] = {}
    if not themes_dir.exists():
        return result
    for f in sorted(themes_dir.glob("*.yaml")):
        try:
            result[f.stem] = load_theme_config(f)
        except ConfigLoadError as exc:
            result[f.stem] = exc
    return result


# -- app settings (config/settings.yaml) --

class UpdaterSettings(BaseModel):
    repo: str = ""  # owner/name of the release repo
    test_mode: bool = True  # true reads a local mock feed instead of github
    local_feed_path: Optional[str] = None


class AppSettings(BaseModel):
    version: str = "0.1.0"
    active_theme: str = "dark"
    updater: UpdaterSettings = Field(default_factory=UpdaterSettings)
    dev_password_hash: str = ""  # bcrypt hash only, never the plain password


# builds fresh settings, template and version are only passed by the release build
# see docs/ARCHITECTURE.md, settings bootstrap
def bootstrap_settings(
    template: Optional[dict] = None,
    version: Optional[str] = None,
    dev_password: str = DEFAULT_DEV_PASSWORD,
) -> AppSettings:
    updater_overrides = (template or {}).get("updater") or {}
    settings = AppSettings(
        dev_password_hash=_hash_password(dev_password),
        updater=UpdaterSettings(**updater_overrides),
    )
    if version:
        settings.version = version
    return settings


# first run fallback for dev runs or a deleted settings.yaml
def ensure_default_settings(path: Path) -> None:
    if not path.exists():
        save_app_settings(path, bootstrap_settings())


# creates a default settings.yaml first if there isn't one
def load_app_settings(path: Path) -> AppSettings:
    ensure_default_settings(path)
    raw = yaml.safe_load(path.read_text()) or {}
    try:
        return AppSettings(**raw)
    except ValidationError as exc:
        raise ConfigLoadError(f"settings.yaml is invalid: {exc}") from exc


def save_app_settings(path: Path, settings: AppSettings) -> None:
    atomic_write_text(path, yaml.safe_dump(settings.model_dump(), sort_keys=False))


# -- developer password --

def verify_dev_password(settings: AppSettings, attempt: str) -> bool:
    if not settings.dev_password_hash:
        return False
    return _verify_password(attempt, settings.dev_password_hash)


def is_default_dev_password(settings: AppSettings) -> bool:
    return verify_dev_password(settings, DEFAULT_DEV_PASSWORD)


def set_dev_password(settings_path: Path, settings: AppSettings, new_password: str) -> AppSettings:
    settings.dev_password_hash = _hash_password(new_password)
    save_app_settings(settings_path, settings)
    return settings


# -- github repo setting --

_GITHUB_REPO_RE = re.compile(
    r"^(?:(?:https?://)?(?:www\.)?github\.com[/:]|git@github\.com:)?"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)/(?P<name>[A-Za-z0-9._-]+?)"
    r"(?:\.git)?/?$"
)


# turns any pasted github link or owner/name into owner/name, raises ValueError otherwise
def normalize_github_repo(value: str) -> str:
    cleaned = value.strip()
    # drop sub-pages like /releases or /tree/main
    cleaned = re.sub(
        r"(github\.com[/:][^/]+/[^/]+?)/(?:releases|tree|blob|issues|pulls|actions)(?:/.*)?$",
        r"\1", cleaned,
    )
    match = _GITHUB_REPO_RE.match(cleaned)
    if not match:
        raise ValueError(
            f"'{value}' doesn't look like a GitHub repo. Use 'owner/name' or "
            f"a link like https://github.com/owner/name."
        )
    return f"{match['owner']}/{match['name']}"


def github_remote_url(repo: str) -> str:
    return f"https://github.com/{repo}.git"


# saves the updater repo (blank clears it) and optionally test_mode
def set_updater_repo(settings_path: Path, settings: AppSettings, repo: str,
                     test_mode: Optional[bool] = None) -> AppSettings:
    settings.updater.repo = normalize_github_repo(repo) if repo.strip() else ""
    if test_mode is not None:
        settings.updater.test_mode = test_mode
    save_app_settings(settings_path, settings)
    return settings


# -- shared helpers --

# loads yaml into a model and turns every failure into a readable ConfigLoadError
def _load_yaml_model(path: Path, model: type[BaseModel]):
    if not path.exists():
        raise ConfigLoadError(f"Config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"{path.name} is not valid YAML: {exc}") from exc
    # valid yaml can still be a bare string or list, which would crash model(**raw)
    if not isinstance(raw, dict):
        raise ConfigLoadError(
            f"{path.name} is not a valid {model.__name__.replace('Config', '').lower() or model.__name__} "
            f"config -- expected a YAML mapping (key: value pairs) at the top level, "
            f"got {type(raw).__name__}."
        )
    try:
        return model(**raw)
    except ValidationError as exc:
        friendly = "\n".join(
            f"  - {'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise ConfigLoadError(f"{path.name} has invalid/missing fields:\n{friendly}") from exc
