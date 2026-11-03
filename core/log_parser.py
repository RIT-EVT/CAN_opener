#--------------------#
# log_parser.py
# reads mf4 logs (asammdf), decodes them with the dbc and builds signal summaries
#--------------------#
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from asammdf import MDF

from core.dbc_handler import DbcHandler


@dataclass
class SignalSeries:
    name: str
    timestamps: np.ndarray
    values: np.ndarray
    unit: str = ""


@dataclass
class SignalSummary:
    name: str
    maximum: float
    minimum: float
    average: float


class LogParser:
    def __init__(self, mf4_path: Path, dbc_handler: DbcHandler):
        self.mf4_path = mf4_path
        self.dbc_handler = dbc_handler
        self._mdf: Optional[MDF] = None
        self.decoded: dict[str, SignalSeries] = {}
        self.summaries: dict[str, SignalSummary] = {}
        self.not_decoded_ids: set[int] = set()  # raw ids the dbc doesn't cover

    # -- loading --

    # select() reads each group once instead of once per channel, master (time) channels are skipped
    def load(self) -> None:
        self._mdf = MDF(str(self.mf4_path))
        decoded_mdf = self._mdf.extract_bus_logging(
            database_files={"CAN": [(str(self.dbc_handler.dbc_path), 0)]}
        )
        entries = [
            (None, gi, ci)
            for gi, group in enumerate(decoded_mdf.groups)
            for ci in range(len(group.channels))
            if ci != decoded_mdf.masters_db.get(gi)
        ]
        for sig in decoded_mdf.select(entries):
            self.decoded[sig.name] = SignalSeries(
                name=sig.name,
                timestamps=sig.timestamps,
                values=np.asarray(sig.samples),
                unit=sig.unit or "",
            )
        self._collect_not_decoded()
        self._compute_summaries()

    def _collect_not_decoded(self) -> None:
        try:
            raw = self._mdf.get("CAN_DataFrame.ID")
            all_ids = {int(i) for i in np.unique(raw.samples)}
        except Exception:
            all_ids = set()
        known_ids = {m.frame_id for m in self.dbc_handler.messages()}
        self.not_decoded_ids = all_ids - known_ids

    # max/min/avg for numeric signals only, enum signals decode to text and are skipped
    # see docs/ARCHITECTURE.md, log parsing
    def _compute_summaries(self) -> None:
        self.summaries = {}
        for name, series in self.decoded.items():
            self._summarize(name, series)

    def _summarize(self, name: str, series: SignalSeries) -> None:
        if not np.issubdtype(series.values.dtype, np.number):
            return
        self.summaries[name] = SignalSummary(
            name=name,
            maximum=float(np.max(series.values)),
            minimum=float(np.min(series.values)),
            average=float(np.mean(series.values)),
        )

    # -- force decode --

    # decodes every raw frame with raw_id using the message from DbcHandler.force_map()
    # results merge into self.decoded, returns {} if nothing decodes
    def apply_force_decode(self, raw_id: int) -> dict[str, SignalSeries]:
        message = self.dbc_handler.resolve_force_map(raw_id)
        if message is None or self._mdf is None:
            return {}

        id_sig = self._mdf.get("CAN_DataFrame.ID")
        mask = id_sig.samples == raw_id
        if not mask.any():
            return {}

        data_sig = self._mdf.get("CAN_DataFrame.DataBytes")
        timestamps = id_sig.timestamps[mask]
        frames = data_sig.samples[mask]  # fixed width rows, zero padded past the dlc
        length = message.length

        per_signal_values: dict[str, list] = {}
        valid_timestamps: list[float] = []
        for row_bytes, ts in zip(frames, timestamps):
            try:
                decoded_values = message.decode(bytes(row_bytes[:length]))
            except Exception:
                continue  # frame doesn't fit this message layout
            valid_timestamps.append(ts)
            for sig_name, value in decoded_values.items():
                per_signal_values.setdefault(sig_name, []).append(value)

        if not valid_timestamps:
            return {}

        ts_array = np.array(valid_timestamps)
        unit_lookup = {s.name: (s.unit or "") for s in message.signals}
        result: dict[str, SignalSeries] = {}
        for sig_name, values in per_signal_values.items():
            series = SignalSeries(
                name=sig_name,
                timestamps=ts_array,
                values=np.array([_as_float(v) for v in values], dtype=float),
                unit=unit_lookup.get(sig_name, ""),
            )
            self.decoded[sig_name] = series
            self._summarize(sig_name, series)  # only the new signals, the rest are unchanged
            result[sig_name] = series
        return result

    def close(self) -> None:
        if self._mdf is not None:
            self._mdf.close()


# enum or choice values have no number, they become nan
def _as_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")
