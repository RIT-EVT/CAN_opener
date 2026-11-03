#--------------------#
# file_utils.py
# data folder setup, atomic writes and first-run default copies
#--------------------#
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

# folders created inside the data root (versions/ lives beside it, not in it)
REQUIRED_DIRS = [
    "config/platforms",
    "config/themes",
    "config/help",
    "dbc_store",
    "logs_cache",
]


def ensure_directories(app_root: Path) -> None:
    for rel in REQUIRED_DIRS:
        (app_root / rel).mkdir(parents=True, exist_ok=True)


# write to a temp file then swap it in, so a crash can't leave a half-written config
def atomic_write_text(path: Path, content: str, encoding: Optional[str] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    os.replace(tmp, path)


# copies a default into place only if dst doesn't exist yet, returns true if it copied
def copy_default_if_missing(src: Path, dst: Path) -> bool:
    if dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    return True
