#--------------------#
# test_log_parser.py
# tests for mf4 decoding, signal summaries and force decode
#--------------------#
from pathlib import Path

import numpy as np
import pytest

from core.dbc_handler import DbcHandler
from core.log_parser import LogParser, SignalSeries

FIXTURE_DBC = Path(__file__).parent / "fixtures" / "sample.dbc"
VALUE_TABLE_DBC = Path(__file__).parent / "fixtures" / "value_table.dbc"
SAMPLE_LOG = Path(__file__).parent / "fixtures" / "sample_log.mf4"

requires_sample_log = pytest.mark.skipif(
    not SAMPLE_LOG.exists(), reason="Real sample .mf4 log not present in tests/fixtures/"
)


# max/min/avg on synthetic data, real decoding is covered below
def test_compute_summaries_from_decoded_signals(tmp_path):
    handler = DbcHandler(FIXTURE_DBC)
    parser = LogParser(mf4_path=tmp_path / "fake.mf4", dbc_handler=handler)
    parser.decoded = {
        "RPM": SignalSeries(
            name="RPM", timestamps=np.array([0.0, 1.0, 2.0]),
            values=np.array([100.0, 200.0, 300.0]), unit="rpm",
        ),
    }
    parser._compute_summaries()

    summary = parser.summaries["RPM"]
    assert summary.maximum == 300.0
    assert summary.minimum == 100.0
    assert summary.average == 200.0


def test_apply_force_decode_without_mapping_returns_empty(tmp_path):
    handler = DbcHandler(FIXTURE_DBC)
    parser = LogParser(mf4_path=tmp_path / "fake.mf4", dbc_handler=handler)
    assert parser.apply_force_decode(0xABC) == {}


# the fixture dbc matches nothing in the real log, so every id lands in not decoded
@requires_sample_log
def test_load_real_log_collects_not_decoded_ids():
    handler = DbcHandler(FIXTURE_DBC)
    parser = LogParser(SAMPLE_LOG, handler)
    parser.load()
    try:
        assert len(parser.not_decoded_ids) > 0
        assert parser.decoded == {}
    finally:
        parser.close()


# maps real id 0x380 onto the fixture EngineData message and decodes real frames
@requires_sample_log
def test_force_decode_against_real_log_frames():
    handler = DbcHandler(FIXTURE_DBC)
    parser = LogParser(SAMPLE_LOG, handler)
    parser.load()
    try:
        real_id = 0x380
        handler.force_map(real_id, "EngineData")
        decoded = parser.apply_force_decode(real_id)

        assert set(decoded.keys()) == {"RPM", "Temp"}
        for series in decoded.values():
            assert len(series.timestamps) > 0
            assert len(series.timestamps) == len(series.values)
        # merged into decoded and summaries like native signals
        assert "RPM" in parser.decoded
        assert "RPM" in parser.summaries
    finally:
        parser.close()


@requires_sample_log
def test_force_decode_unknown_id_returns_empty():
    handler = DbcHandler(FIXTURE_DBC)
    parser = LogParser(SAMPLE_LOG, handler)
    parser.load()
    try:
        handler.force_map(0x7FFFFFF, "EngineData")  # not present in this log
        assert parser.apply_force_decode(0x7FFFFFF) == {}
    finally:
        parser.close()


# regression, enum signals decode to text and used to crash the summary step
@requires_sample_log
def test_load_handles_value_table_enum_signals_without_crashing():
    handler = DbcHandler(VALUE_TABLE_DBC)
    parser = LogParser(SAMPLE_LOG, handler)
    parser.load()  # must not raise
    try:
        assert "StateEnum" in parser.decoded
        assert "StateEnum" not in parser.summaries  # text has no numeric summary
        assert "RawValue" in parser.decoded
        assert "RawValue" in parser.summaries  # numeric signal still summarized fine
    finally:
        parser.close()
