"""Pure aggregation helpers for the `summary` service (WS-6 · E8).

Aggregates are computed exclusively over the coordinator's bounded
``value_history`` windows ((ts, value) samples, newest first semantics do
not matter — filtering by timestamp does). Non-numeric samples (binary/
switch pass-through states) never enter min/max/avg. The recorder's
internals are never consulted, so a dashboard and the integration can
never disagree about which numbers were aggregated.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Any


def aggregate_window(
    samples: Iterable[tuple[datetime, Any]],
    window_seconds: int,
    now: datetime,
) -> dict[str, float | None]:
    """min/max/avg over numeric samples inside the window (inclusive bound).

    Raises:
        ValueError: If ``window_seconds`` is not positive.
    """
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    numbers = [
        float(value)
        for timestamp, value in samples
        if (now - timestamp).total_seconds() <= window_seconds
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ]
    if not numbers:
        return {"min": None, "max": None, "avg": None}
    return {
        "min": min(numbers),
        "max": max(numbers),
        "avg": sum(numbers) / len(numbers),
    }
