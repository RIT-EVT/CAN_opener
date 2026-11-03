#--------------------#
# test_signal_stats.py
# tests for held value lookups and per signal statistics
#--------------------#
import numpy as np

from core.signal_stats import compute_stats, format_value, sample_index_at, value_at

T = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
V = np.array([5.0, 1.0, 9.0, 3.0, 2.0])


def test_value_holds_until_the_next_sample():
    assert value_at(T, V, -0.5) is None  # before the first frame
    assert value_at(T, V, 0.0) == 5.0
    assert value_at(T, V, 1.99) == 1.0
    assert value_at(T, V, 100.0) == 2.0
    assert sample_index_at(T, 2.0) == 2


def test_whole_log_stats():
    st = compute_stats("X", T, V, "V")
    assert (st.samples, st.minimum, st.maximum) == (5, 1.0, 9.0)
    assert st.time_of_max == 2.0 and st.time_of_min == 1.0
    assert st.mean == np.mean(V)
    assert st.rate_hz == 1.0


# the cursor range works either way round
def test_stats_between_cursors_only_use_samples_inside():
    st = compute_stats("X", T, V, t0=3.5, t1=1.5)
    assert st.samples == 2  # t=2 and t=3
    assert (st.minimum, st.maximum) == (3.0, 9.0)


def test_nan_values_are_ignored_and_empty_ranges_are_blank():
    st = compute_stats("X", T, np.array([np.nan, 1.0, np.nan, 4.0, 2.0]))
    assert (st.minimum, st.maximum) == (1.0, 4.0)
    empty = compute_stats("X", T, V, t0=10, t1=20)
    assert empty.samples == 0 and empty.minimum is None


def test_enum_signals_count_states():
    labels = np.array([b"OFF", b"ON", b"ON", b"OFF", b"ON"])
    st = compute_stats("State", T, labels)
    assert not st.numeric and st.minimum is None
    assert st.distinct == 2 and st.most_common == "ON"
    assert format_value(labels[1]) == "ON"
