"""Filter pipeline for Abstractor."""
from __future__ import annotations

import logging
import math
from typing import Any

_LOGGER = logging.getLogger(__name__)

class AbstractorFilterPipeline:
    """Processes states through configured filters."""
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._last_valid_state: float | None = None
        self.last_event: str | None = None

    def process(self, raw_state: str | None) -> float | None:
        """Process the raw state string through the pipeline."""
        self.last_event = None
        if raw_state in ("unavailable", "unknown", "none", None):
            self.last_event = "source unavailable"
            return self._handle_unavailable()

        try:
            val = float(raw_state)
        except (ValueError, TypeError):
            _LOGGER.debug("Non-numeric state received: %s", raw_state)
            self.last_event = "source non-numeric"
            return self._handle_unavailable()

        if not math.isfinite(val):
            _LOGGER.debug("Non-finite state received: %s", raw_state)
            self.last_event = "source non-finite"
            return self._handle_unavailable()
        
        if self.config.get("invert", False):
            val = val * -1

        if self.config.get("spike_filter", False) and self._last_valid_state is not None and val < self._last_valid_state:
            _LOGGER.debug("Spike filter blocked value drop: %s -> %s", self._last_valid_state, val)
            self.last_event = "spike rejected"
            return self._last_valid_state

        self._last_valid_state = val
        return val

    def process_sources(self, raw_states: list[str | None]) -> float | None:
        """Process and aggregate source states.

        Power sources are fail-soft and contribute zero when unavailable. Energy
        sources are fail-closed so a utility meter cannot count a bad sample.
        """
        last_value = self._last_valid_state
        spike_filter = self.config.get("spike_filter", False)
        self.config["spike_filter"] = False
        values = []
        try:
            for raw_state in raw_states:
                value = self.process(raw_state)
                if value is None:
                    if self.config.get("device_type") == "power":
                        continue
                    return None
                values.append(value)
        finally:
            self.config["spike_filter"] = spike_filter
        total = sum(values) if values else (0.0 if self.config.get("device_type") == "power" else None)
        self._last_valid_state = last_value
        if (
            total is not None
            and spike_filter
            and last_value is not None
            and total < last_value
        ):
            _LOGGER.debug("Spike filter blocked aggregate drop: %s -> %s", last_value, total)
            self.last_event = "aggregate spike rejected"
            return last_value
        if total is not None:
            self._last_valid_state = total
        return total

    def _handle_unavailable(self) -> float | None:
        if self.config.get("fallback_zero", False) or self.config.get("device_type") == "power":
            return 0.0
        return None
