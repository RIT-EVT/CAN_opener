#--------------------#
# help_content.py
# load, save and list the markdown help topics
#--------------------#
from __future__ import annotations

from pathlib import Path

from utils.file_utils import atomic_write_text, copy_default_if_missing

DEFAULT_HELP_TEXT = "*No help content has been written for this topic yet.*"


# copies built-in topics into config/help/ without overwriting edited ones
def bootstrap_default_help(help_dir: Path, defaults_dir: Path) -> None:
    if not defaults_dir.exists():
        return
    for src in defaults_dir.glob("*.md"):
        copy_default_if_missing(src, help_dir / src.name)


# reads as utf-8, falls back to the locale encoding for older saved copies
def load_help_text(help_dir: Path, key: str) -> str:
    path = help_dir / f"{key}.md"
    if not path.exists():
        return DEFAULT_HELP_TEXT
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text()


def save_help_text(help_dir: Path, key: str, markdown_text: str) -> None:
    atomic_write_text(help_dir / f"{key}.md", markdown_text, encoding="utf-8")


# every topic from both the user copies and the built-in defaults
def list_help_keys(help_dir: Path, defaults_dir: Path) -> list[str]:
    keys = set()
    if help_dir.exists():
        keys.update(p.stem for p in help_dir.glob("*.md"))
    if defaults_dir.exists():
        keys.update(p.stem for p in defaults_dir.glob("*.md"))
    return sorted(keys)
