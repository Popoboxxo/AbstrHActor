"""DataUpdateCoordinator for Abstractor."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_SOURCE_ENTITY_ID, CONF_SOURCE_ENTITY_IDS, DOMAIN
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
        self.entries: dict[str, ConfigEntry] = {}
        self.pipelines: dict[str, AbstractorFilterPipeline] = {}
        self.influx_exporter = None
        self._last_notified_events: dict[str, str] = {}

    def add_entry(self, entry: ConfigEntry) -> None:
        """Add an entry to central polling."""
        self.entries[entry.entry_id] = entry
        config = {**entry.data, **entry.options}
        config["device_type"] = config.get("device_type", "power")
        self.pipelines[entry.entry_id] = AbstractorFilterPipeline(config)

    def remove_entry(self, entry_id: str) -> None:
        """Remove an entry from central polling."""
        self.entries.pop(entry_id, None)
        self.pipelines.pop(entry_id, None)
        self._last_notified_events.pop(entry_id, None)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via central polling."""
        data: dict[str, float | None] = {}
        for entry_id, entry in self.entries.items():
            config = {**entry.data, **entry.options}
            source_ids = config.get(CONF_SOURCE_ENTITY_IDS) or [
                config.get(CONF_SOURCE_ENTITY_ID)
            ]
            source_ids = [source_id for source_id in source_ids if source_id]
            if not source_ids:
                continue

            raw_states = [
                (state_obj.state if (state_obj := self.hass.states.get(source_id)) else None)
                for source_id in source_ids
            ]

            pipeline = self.pipelines.get(entry_id)
            if pipeline:
                val = pipeline.process_sources(raw_states)
                data[entry_id] = val
                await self._async_notify_debug(entry_id, pipeline.last_event)

                if self.influx_exporter and val is not None:
                    await self.influx_exporter.async_push(source_ids[0], val)
        return data

    async def _async_notify_debug(self, entry_id: str, event: str | None) -> None:
        """Send deduplicated debug events through the existing HA notify group."""
        if event is None:
            self._last_notified_events.pop(entry_id, None)
            return
        if self._last_notified_events.get(entry_id) == event:
            return
        if not self.hass.states.is_state("input_boolean.automation_debugger", "on"):
            return
        if not self.hass.services.has_service("notify", "adminnotificationgroup"):
            return
        await self.hass.services.async_call(
            "notify",
            "adminnotificationgroup",
            {"message": f"Abstractor {entry_id}: {event}"},
            blocking=False,
        )
        self._last_notified_events[entry_id] = event
