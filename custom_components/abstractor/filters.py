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

    def process_sources(
        self,
        raw_states: list[str | None],
        net_subtract_raw: str | None = None,
        fallback_raw: str | None = None,
        fallback_condition_met: bool = False,
    ) -> float | None:
        """Process and aggregate source states.

        Power sources are fail-soft and contribute zero when unavailable. Energy
        sources are fail-closed so a utility meter cannot count a bad sample.

        ``net_subtract_raw`` (REQ-CORE-005) is subtracted from the aggregate
        after summing, e.g. to derive a net flow such as charge - discharge.

        ``fallback_raw``/``fallback_condition_met`` (REQ-COMP-004) provide an
        alternate hardware source used only when the primary aggregate is
        unavailable AND the configured condition is met.
        """
        last_value = self._last_valid_state
        spike_filter = self.config.get("spike_filter", False)
        self.config["spike_filter"] = False
        values = []
        fail_closed = False
        try:
            for raw_state in raw_states:
                value = self.process(raw_state)
                if value is None:
                    if self.config.get("device_type") == "power":
                        continue
                    # Fail-closed device types (energy/water): don't bail out
                    # immediately — the REQ-COMP-004 fallback below still gets
                    # a chance to supply a value before we give up.
                    fail_closed = True
                    break
                values.append(value)
        finally:
            self.config["spike_filter"] = spike_filter
        if fail_closed:
            total = None
        else:
            total = sum(values) if values else (0.0 if self.config.get("device_type") == "power" else None)
        self._last_valid_state = last_value

        if total is not None and net_subtract_raw is not None:
            subtract_value = self._parse_plain(net_subtract_raw)
            if subtract_value is not None:
                total -= subtract_value

        if total is None and fallback_condition_met and fallback_raw is not None:
            fallback_value = self._parse_plain(fallback_raw)
            if fallback_value is not None:
                _LOGGER.debug("Using fallback source value: %s", fallback_value)
                self.last_event = "fallback source used"
                total = fallback_value

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

    @staticmethod
    def _parse_plain(raw_state: str | None) -> float | None:
        """Parse a raw HA state to float without side effects on pipeline state."""
        if raw_state in ("unavailable", "unknown", "none", None):
            return None
        try:
            val = float(raw_state)
        except (ValueError, TypeError):
            return None
        return val if math.isfinite(val) else None

    def _handle_unavailable(self) -> float | None:
        if self.config.get("fallback_zero", False) or self.config.get("device_type") == "power":
            return 0.0
        return None
