#--------------------#
# signal_stats.py
# value lookups at a time and per signal statistics, used by the cursors, data analysis and table view
# values hold between samples (the last frame received), see docs/ARCHITECTURE.md, held values and statistics
#--------------------#
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


# index of the last sample at or before t, -1 if t is before the first sample
def sample_index_at(timestamps: np.ndarray, t: float) -> int:
    return int(np.searchsorted(timestamps, t, side="right")) - 1


# same lookup for many times at once, used by the table view
def sample_indices_at(timestamps: np.ndarray, times: np.ndarray) -> np.ndarray:
    return np.searchsorted(timestamps, times, side="right") - 1


# the held value at time t, None before the first sample
def value_at(timestamps: np.ndarray, values: np.ndarray, t: float):
    idx = sample_index_at(timestamps, t)
    return None if idx < 0 else values[idx]


def is_numeric(values: np.ndarray) -> bool:
    return np.issubdtype(values.dtype, np.number)


# enum signals decode to bytes or str labels
def label_text(value) -> str:
    return value.decode(errors="replace") if isinstance(value, bytes) else str(value)


@dataclass
class SignalStats:
    name: str
    unit: str
    samples: int
    start: Optional[float]  # time of the first sample in range
    end: Optional[float]
    numeric: bool
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    mean: Optional[float] = None
    std: Optional[float] = None
    time_of_min: Optional[float] = None
    time_of_max: Optional[float] = None
    rate_hz: Optional[float] = None
    distinct: Optional[int] = None  # categorical only
    most_common: Optional[str] = None  # categorical only


# stats over the whole log, or only samples with t0 <= t <= t1
def compute_stats(name: str, timestamps: np.ndarray, values: np.ndarray, unit: str = "",
                  t0: Optional[float] = None, t1: Optional[float] = None) -> SignalStats:
    if t0 is not None and t1 is not None:
        lo, hi = sorted((t0, t1))
        mask = (timestamps >= lo) & (timestamps <= hi)
        timestamps, values = timestamps[mask], values[mask]

    count = len(timestamps)
    numeric = is_numeric(values)
    stats = SignalStats(
        name=name, unit=unit, samples=count, numeric=numeric,
        start=float(timestamps[0]) if count else None,
        end=float(timestamps[-1]) if count else None,
    )
    if count >= 2 and timestamps[-1] > timestamps[0]:
        stats.rate_hz = (count - 1) / float(timestamps[-1] - timestamps[0])
    if not count:
        return stats

    if numeric:
        finite = np.isfinite(values)
        if not finite.any():
            return stats
        vals, ts = values[finite], timestamps[finite]
        i_min, i_max = int(np.argmin(vals)), int(np.argmax(vals))
        stats.minimum, stats.maximum = float(vals[i_min]), float(vals[i_max])
        stats.time_of_min, stats.time_of_max = float(ts[i_min]), float(ts[i_max])
        stats.mean = float(np.mean(vals))
        stats.std = float(np.std(vals))
    else:
        labels, counts = np.unique(values, return_counts=True)
        stats.distinct = len(labels)
        stats.most_common = label_text(labels[int(np.argmax(counts))])
    return stats


# short readable number for tables and readouts
def format_number(value: Optional[float], unit: str = "") -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    text = f"{value:.6g}"
    return f"{text} {unit}" if unit else text


# a held value as text, numbers get the unit, enum labels are decoded
def format_value(value, unit: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, (bytes, str)):
        return label_text(value)
    return format_number(float(value), unit)
