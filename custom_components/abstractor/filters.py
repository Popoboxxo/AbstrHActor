"""Filter pipeline for Abstractor."""
from __future__ import annotations

import logging
import math
from typing import Any

from .const import (
    AGGREGATION_FIRST_AVAILABLE,
    AGGREGATION_MAX,
    AGGREGATION_MIN,
    AGGREGATION_MODES,
    AGGREGATION_SUM,
    CONF_AGGREGATION,
)

_LOGGER = logging.getLogger(__name__)

class AbstractorFilterPipeline:
    """Processes states through configured filters."""
    def __init__(
        self, config: dict[str, Any], initial_last_valid_state: float | None = None
    ):
        self.config = config
        self._last_valid_state: float | None = initial_last_valid_state
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

        The per-subentry ``aggregation`` mode (REQ-CORE-004 extension) decides
        how the successfully parsed source values are combined:

        - ``sum`` (default): all parsed values are added. For power, sources
          that fail to parse are skipped (they contribute zero); for
          energy/water a single failed source fails the whole aggregate
          closed (``None``) so a utility meter cannot count a bad sample.
        - ``max`` / ``min``: the highest / lowest parsed value wins. Only
          successfully parsed sources are considered — a partially failed
          multi-source sensor still reports a value. When NO source parses,
          the device-type fallback applies (power fails soft to ``0.0``,
          energy/water fail closed to ``None``).
        - ``first_available``: the first successfully parsed source in the
          configured (sorted) source order wins; when none parse, the same
          device-type fallback as for ``max``/``min`` applies.

        In every mode the configured ``invert`` transformation has already
        been applied to each parsed value, and the device-type failure
        contract is unchanged: power never fails closed, energy/water never
        invent a sample.

        ``net_subtract_raw`` (REQ-CORE-005) is subtracted from the aggregate
        after aggregation, e.g. to derive a net flow such as charge - discharge.

        ``fallback_raw``/``fallback_condition_met`` (REQ-COMP-004) provide an
        alternate hardware source used only when the primary aggregate is
        unavailable AND the configured condition is met.
        """
        aggregation = self.config.get(CONF_AGGREGATION, AGGREGATION_SUM)
        if aggregation not in AGGREGATION_MODES:
            _LOGGER.debug("Unknown aggregation mode %s; using sum", aggregation)
            aggregation = AGGREGATION_SUM
        last_value = self._last_valid_state
        spike_filter = self.config.get("spike_filter", False)
        self.config["spike_filter"] = False
        values = []
        fail_closed = False
        try:
            for raw_state in raw_states:
                if aggregation != AGGREGATION_SUM and self._parse_plain(
                    raw_state
                ) is None:
                    # max/min/first_available: a source that delivered no
                    # parseable value is skipped entirely — including the
                    # fail-soft 0.0 power would otherwise get — so a dead
                    # channel can never win min/first_available. Only the
                    # total absence of parsed values falls through to the
                    # device-type fallback below.
                    continue
                value = self.process(raw_state)
                if value is None:
                    if self.config.get("device_type") == "power":
                        continue
                    if aggregation == AGGREGATION_SUM:
                        # Fail-closed device types (energy/water): don't bail
                        # out immediately — the REQ-COMP-004 fallback below
                        # still gets a chance to supply a value before we
                        # give up.
                        fail_closed = True
                        break
                    continue
                values.append(value)
        finally:
            self.config["spike_filter"] = spike_filter
        if fail_closed:
            total = None
        elif values:
            total = self._aggregate_values(values, aggregation)
        else:
            total = 0.0 if self.config.get("device_type") == "power" else None
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

    @staticmethod
    def _aggregate_values(values: list[float], aggregation: str) -> float:
        """Combine parsed per-source values per the configured aggregation mode.

        ``values`` only contains successfully parsed (and possibly inverted)
        source values, in configured source order. ``sum`` adds them (the
        historical behavior), ``max``/``min`` pick the extreme, and
        ``first_available`` keeps the first — i.e. the highest-priority
        source that delivered a value.
        """
        if aggregation == AGGREGATION_MAX:
            return max(values)
        if aggregation == AGGREGATION_MIN:
            return min(values)
        if aggregation == AGGREGATION_FIRST_AVAILABLE:
            return values[0]
        return sum(values)

    def _handle_unavailable(self) -> float | None:
        if self.config.get("fallback_zero", False) or self.config.get("device_type") == "power":
            return 0.0
        return None
