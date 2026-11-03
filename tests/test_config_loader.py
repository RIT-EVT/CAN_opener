#--------------------#
# test_config_loader.py
# tests for config schemas, yaml loading, settings bootstrap and github repo parsing
#--------------------#
import pytest
import yaml

from core.config_loader import (
    DEFAULT_DEV_PASSWORD,
    ConfigLoadError,
    bootstrap_settings,
    discover_platforms,
    ensure_default_settings,
    is_default_dev_password,
    load_app_settings,
    load_platform_config,
    load_theme_config,
    set_dev_password,
    verify_dev_password,
)


def test_platform_config_missing_field_raises_friendly_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("description: no name or dbc_path\n")
    with pytest.raises(ConfigLoadError):
        load_platform_config(bad)


# regression, a bare string yaml file used to crash startup with a TypeError
def test_platform_config_wrong_shape_raises_config_load_error_not_typeerror(tmp_path):
    bad = tmp_path / "my_car.yaml"
    bad.write_text("my platform\n")
    with pytest.raises(ConfigLoadError):
        load_platform_config(bad)


def test_theme_config_wrong_shape_raises_config_load_error_not_typeerror(tmp_path):
    bad = tmp_path / "bad_theme.yaml"
    bad.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigLoadError):
        load_theme_config(bad)


# one bad file comes back as a per-file error, discovery keeps going
def test_discover_platforms_surfaces_wrong_shape_file_without_crashing(tmp_path):
    platforms_dir = tmp_path / "platforms"
    platforms_dir.mkdir()
    (platforms_dir / "my_car.yaml").write_text("my platform\n")
    (platforms_dir / "good_car.yaml").write_text(yaml.safe_dump({
        "name": "Good Car",
        "dbc_path": "good_car.dbc",
    }))

    results = discover_platforms(platforms_dir)

    assert isinstance(results["my_car"], ConfigLoadError)
    assert results["good_car"].name == "Good Car"


def test_platform_config_valid_loads(tmp_path):
    good = tmp_path / "platform_a.yaml"
    good.write_text(yaml.safe_dump({
        "name": "Platform A",
        "dbc_path": "platform_a.dbc",
        "important_values": ["VehicleSpeed", "PackVoltage"],
    }))
    cfg = load_platform_config(good)
    assert cfg.name == "Platform A"
    assert "VehicleSpeed" in cfg.important_values


def test_theme_config_round_trip(tmp_path):
    theme_file = tmp_path / "custom.yaml"
    theme_file.write_text(yaml.safe_dump({
        "name": "custom",
        "mode": "custom",
        "font_scale": 1.2,
        "colors": {
            "background": "#000000", "surface": "#111111", "text": "#ffffff",
            "accent": "#ff00ff", "border": "#222222", "plot_palette": ["#ff0000"],
        },
    }))
    theme = load_theme_config(theme_file)
    assert theme.font_scale == 1.2
    assert theme.colors.plot_palette == ["#ff0000"]


def test_default_settings_bootstrap_and_dev_password(tmp_path):
    settings_path = tmp_path / "settings.yaml"
    ensure_default_settings(settings_path)
    settings = load_app_settings(settings_path)

    assert is_default_dev_password(settings)
    assert verify_dev_password(settings, DEFAULT_DEV_PASSWORD)
    assert not verify_dev_password(settings, "wrong-password")

    settings = set_dev_password(settings_path, settings, "team-secret")
    assert verify_dev_password(settings, "team-secret")
    assert not verify_dev_password(settings, DEFAULT_DEV_PASSWORD)

    # reloading from disk shows the new password
    reloaded = load_app_settings(settings_path)
    assert verify_dev_password(reloaded, "team-secret")


def test_bootstrap_settings_with_no_args_matches_plain_default():
    # dev run or deleted settings.yaml, same as ensure_default_settings()
    settings = bootstrap_settings()
    assert settings.updater.repo == ""
    assert settings.updater.test_mode is True
    assert settings.version == "0.1.0"
    assert is_default_dev_password(settings)


def test_bootstrap_settings_applies_template_and_version():
    # what the release build bakes in, template updater settings plus the real version
    template = {"updater": {"repo": "acme/can-decoder", "test_mode": False}}
    settings = bootstrap_settings(template=template, version="1.2.0")

    assert settings.updater.repo == "acme/can-decoder"
    assert settings.updater.test_mode is False
    assert settings.updater.local_feed_path is None
    assert settings.version == "1.2.0"
    # the dev password is always freshly hashed, never taken from the template
    assert is_default_dev_password(settings)


def test_bootstrap_settings_template_never_overrides_dev_password():
    # only the updater key is read, a template can't sneak in a password hash
    template = {"updater": {"repo": "acme/can-decoder", "test_mode": False}, "dev_password_hash": "bogus"}
    settings = bootstrap_settings(template=template)
    assert is_default_dev_password(settings)


@pytest.mark.parametrize("raw", [
    "tkenn0/can_decoder_app",
    "  tkenn0/can_decoder_app  ",
    "https://github.com/tkenn0/can_decoder_app",
    "https://github.com/tkenn0/can_decoder_app/",
    "https://github.com/tkenn0/can_decoder_app.git",
    "github.com/tkenn0/can_decoder_app",
    "git@github.com:tkenn0/can_decoder_app.git",
    "https://github.com/tkenn0/can_decoder_app/releases",
    "https://github.com/tkenn0/can_decoder_app/tree/main",
])
def test_normalize_github_repo_accepts_common_forms(raw):
    from core.config_loader import normalize_github_repo
    assert normalize_github_repo(raw) == "tkenn0/can_decoder_app"


@pytest.mark.parametrize("raw", ["", "can_decoder_app", "https://gitlab.com/a/b", "a/b/c", "not a repo"])
def test_normalize_github_repo_rejects_garbage(raw):
    from core.config_loader import normalize_github_repo
    with pytest.raises(ValueError):
        normalize_github_repo(raw)


def test_set_updater_repo_persists(tmp_path):
    from core.config_loader import (
        ensure_default_settings, load_app_settings, set_updater_repo,
    )
    path = tmp_path / "settings.yaml"
    ensure_default_settings(path)
    settings = load_app_settings(path)
    set_updater_repo(path, settings, "https://github.com/someone/other_repo.git", test_mode=False)

    reloaded = load_app_settings(path)
    assert reloaded.updater.repo == "someone/other_repo"
    assert reloaded.updater.test_mode is False

    set_updater_repo(path, reloaded, "   ")
    assert load_app_settings(path).updater.repo == ""
