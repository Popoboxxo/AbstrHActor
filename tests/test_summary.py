"""Pure window-aggregation tests for the summary helpers (WS-6 · E8)."""

from datetime import UTC, datetime, timedelta

from custom_components.abstractor.summary_values import aggregate_window

T0 = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def test_aggregate_empty_window_is_all_none() -> None:
    """No samples inside the window: explicit None, never a fabricated zero."""
    result = aggregate_window([(T0 - timedelta(days=9), 1.0)], window_seconds=3600, now=T0)
    assert result == {"min": None, "max": None, "avg": None}


def test_aggregate_single_sample() -> None:
    """A single sample has min == max == avg == that value."""
    result = aggregate_window([(T0 - timedelta(seconds=10), 4.0)], window_seconds=3600, now=T0)
    assert result == {"min": 4.0, "max": 4.0, "avg": 4.0}


def test_aggregate_bounded_window_excludes_old_samples() -> None:
    """Samples older than the window are excluded; the boundary is inclusive."""
    samples = [
        (T0 - timedelta(seconds=3600), 1.0),  # exactly at the bound: included
        (T0 - timedelta(seconds=3601), 2.0),  # outside: excluded
        (T0 - timedelta(seconds=60), 10.0),
    ]
    result = aggregate_window(samples, window_seconds=3600, now=T0)
    assert result == {"min": 1.0, "max": 10.0, "avg": 5.5}


def test_aggregate_ignores_non_numeric_samples() -> None:
    """Pass-through states (binary/switch strings) never enter min/max/avg."""
    samples = [(T0 - timedelta(seconds=10), "on"), (T0 - timedelta(seconds=20), 3.0)]
    result = aggregate_window(samples, window_seconds=3600, now=T0)
    assert result == {"min": 3.0, "max": 3.0, "avg": 3.0}


def test_aggregate_rejects_non_positive_window() -> None:
    """A zero/negative window is a caller bug, caught loudly."""
    import pytest

    with pytest.raises(ValueError, match="must be positive"):
        aggregate_window([], window_seconds=0, now=T0)
