#--------------------#
# test_help_content.py
# tests for help topic storage and bootstrapping
#--------------------#
from core.help_content import (
    DEFAULT_HELP_TEXT, bootstrap_default_help, list_help_keys, load_help_text,
    save_help_text,
)


def test_load_missing_topic_returns_fallback_text(tmp_path):
    assert load_help_text(tmp_path / "help", "nonexistent") == DEFAULT_HELP_TEXT


def test_save_then_load_round_trips(tmp_path):
    help_dir = tmp_path / "help"
    save_help_text(help_dir, "topic_a", "# Hello\n\nSome **bold** text.")
    assert load_help_text(help_dir, "topic_a") == "# Hello\n\nSome **bold** text."


def test_bootstrap_copies_defaults_without_overwriting_edits(tmp_path):
    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir(parents=True)
    (defaults_dir / "topic_a.md").write_text("default content")
    help_dir = tmp_path / "help"

    bootstrap_default_help(help_dir, defaults_dir)
    assert load_help_text(help_dir, "topic_a") == "default content"

    save_help_text(help_dir, "topic_a", "edited by a developer")
    bootstrap_default_help(help_dir, defaults_dir)  # simulate a second app launch
    assert load_help_text(help_dir, "topic_a") == "edited by a developer"


def test_list_help_keys_includes_defaults_and_user_only_topics(tmp_path):
    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir(parents=True)
    (defaults_dir / "from_default.md").write_text("x")
    help_dir = tmp_path / "help"
    save_help_text(help_dir, "user_only", "y")

    keys = list_help_keys(help_dir, defaults_dir)
    assert "from_default" in keys
    assert "user_only" in keys
