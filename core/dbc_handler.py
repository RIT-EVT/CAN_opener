#--------------------#
# dbc_handler.py
# dbc structure, session-only signal edits and force-decode mapping (cantools)
#--------------------#
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cantools
from cantools.database.can import Database, Message, Signal


# one field-level override on top of the base dbc, see docs/ARCHITECTURE.md, dbc handling
@dataclass
class SignalEdit:
    message_name: str
    signal_name: str
    new_name: Optional[str] = None
    scale: Optional[float] = None
    offset: Optional[float] = None
    unit: Optional[str] = None


class DbcHandler:
    def __init__(self, dbc_path: Path):
        self.dbc_path = dbc_path
        self.db: Database = cantools.database.load_file(str(dbc_path))
        self._force_map: dict[int, str] = {}

    # -- structure viewer --

    def messages(self) -> list[Message]:
        return list(self.db.messages)

    # the fields the signal editor shows
    def signal_detail(self, message_name: str, signal_name: str) -> dict:
        sig = self._find_signal(message_name, signal_name)
        return {"name": sig.name, "unit": sig.unit, "scale": sig.scale, "offset": sig.offset}

    # -- temporary edits (in memory only, never outlive the session) --

    def apply_temp_edit(self, edit: SignalEdit) -> None:
        sig = self._find_signal(edit.message_name, edit.signal_name)
        if edit.new_name is not None:
            sig.name = edit.new_name
        if edit.scale is not None:
            sig.scale = edit.scale
        if edit.offset is not None:
            sig.offset = edit.offset
        if edit.unit is not None:
            sig.unit = edit.unit

    # writes the edited dbc to a new file, the base dbc is never overwritten
    def export_edited_dbc(self, out_path: Path) -> Path:
        if out_path.resolve() == self.dbc_path.resolve():
            raise ValueError("Refusing to overwrite the base DBC file.")
        cantools.database.dump_file(self.db, str(out_path))
        return out_path

    # -- force decoding --

    # maps an unknown raw id onto an existing message, raises KeyError if the message is unknown
    def force_map(self, raw_id: int, message_name: str) -> None:
        self.db.get_message_by_name(message_name)
        self._force_map[raw_id] = message_name

    def resolve_force_map(self, raw_id: int) -> Optional[Message]:
        name = self._force_map.get(raw_id)
        return self.db.get_message_by_name(name) if name else None

    # -- internals --

    def _find_signal(self, message_name: str, signal_name: str) -> Signal:
        msg = self.db.get_message_by_name(message_name)
        for sig in msg.signals:
            if sig.name == signal_name:
                return sig
        raise KeyError(f"Signal {signal_name!r} not found in {message_name!r}")
