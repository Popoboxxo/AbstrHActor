"""Filter pipeline for Abstractor."""
from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

class AbstractorFilterPipeline:
    """Processes states through configured filters."""
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._last_valid_state: float | None = None

    def process(self, raw_state: str) -> float | None:
        """Process the raw state string through the pipeline."""
        if raw_state in ("unavailable", "unknown", "none", None):
            return self._handle_unavailable()

        try:
            val = float(raw_state)
        except (ValueError, TypeError):
            _LOGGER.debug("Non-numeric state received: %s", raw_state)
            return self._last_valid_state
        
        if self.config.get("spike_filter", False) and self._last_valid_state is not None and val < self._last_valid_state:
            _LOGGER.debug("Spike filter blocked value drop: %s -> %s", self._last_valid_state, val)
            return self._last_valid_state

        if self.config.get("invert", False):
            val = val * -1

        self._last_valid_state = val
        return val

    def _handle_unavailable(self) -> float | None:
        if self.config.get("fallback_zero", False):
            return 0.0
        return self._last_valid_state
