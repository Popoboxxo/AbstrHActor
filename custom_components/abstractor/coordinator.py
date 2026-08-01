"""DataUpdateCoordinator for Abstractor."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, CONF_SOURCE_ENTITY_ID
from .filters import AbstractorFilterPipeline

_LOGGER = logging.getLogger(__name__)

class AbstractorDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Abstractor data."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.entries = {}
        self.pipelines = {}
        self.influx_exporter = None

    def add_entry(self, entry: ConfigEntry):
        """Add an entry to central polling."""
        self.entries[entry.entry_id] = entry
        config = {**entry.data, **entry.options}
        self.pipelines[entry.entry_id] = AbstractorFilterPipeline(config)

    def remove_entry(self, entry_id: str):
        """Remove an entry from central polling."""
        self.entries.pop(entry_id, None)
        self.pipelines.pop(entry_id, None)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via central polling."""
        data = {}
        for entry_id, entry in self.entries.items():
            source_id = entry.data.get(CONF_SOURCE_ENTITY_ID)
            if not source_id:
                continue
            
            state_obj = self.hass.states.get(source_id)
            raw_state = state_obj.state if state_obj else None
            
            pipeline = self.pipelines.get(entry_id)
            if pipeline:
                val = pipeline.process(raw_state)
                data[source_id] = val
                
                if self.influx_exporter and val is not None:
                    await self.influx_exporter.async_push(source_id, val)
        return data
