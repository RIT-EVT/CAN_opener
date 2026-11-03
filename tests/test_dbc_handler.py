#--------------------#
# test_dbc_handler.py
# tests for dbc structure, temp edits, export and force mapping
#--------------------#
from pathlib import Path

import pytest

from core.dbc_handler import DbcHandler, SignalEdit

FIXTURE_DBC = Path(__file__).parent / "fixtures" / "sample.dbc"


def test_messages():
    handler = DbcHandler(FIXTURE_DBC)
    names = [m.name for m in handler.messages()]
    assert "EngineData" in names


def test_signal_detail():
    handler = DbcHandler(FIXTURE_DBC)
    detail = handler.signal_detail("EngineData", "RPM")
    assert detail["unit"] == "rpm"
    assert detail["scale"] == 1


def test_temp_edit_is_non_destructive_and_exports_to_new_file(tmp_path):
    handler = DbcHandler(FIXTURE_DBC)
    handler.apply_temp_edit(SignalEdit(
        message_name="EngineData", signal_name="RPM", unit="RPM (edited)", scale=2.0,
    ))
    detail = handler.signal_detail("EngineData", "RPM")
    assert detail["unit"] == "RPM (edited)"
    assert detail["scale"] == 2.0

    out_path = tmp_path / "edited.dbc"
    handler.export_edited_dbc(out_path)
    assert out_path.exists()

    # base dbc on disk is untouched by the in-memory edit
    assert "RPM (edited)" not in FIXTURE_DBC.read_text()

    # refuses to overwrite the base dbc
    with pytest.raises(ValueError):
        handler.export_edited_dbc(FIXTURE_DBC)


def test_force_map_requires_existing_message():
    handler = DbcHandler(FIXTURE_DBC)
    with pytest.raises(Exception):
        handler.force_map(0x123, "NoSuchMessage")

    handler.force_map(0x123, "EngineData")
    resolved = handler.resolve_force_map(0x123)
    assert resolved.name == "EngineData"
    assert handler.resolve_force_map(0x999) is None
