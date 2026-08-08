"""DataUpdateCoordinator for Abstractor."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
    CONF_NET_SUBTRACT_ENTITY_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    DOMAIN,
)
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
        self.subentry_data: dict[str, dict] = {}
        self.pipelines: dict[str, AbstractorFilterPipeline] = {}
        self.influx_exporter = None
        self._last_notified_events: dict[str, str] = {}

    def add_subentry(self, subentry_id: str, subentry_data: dict) -> None:
        """Add a subentry to central polling."""
        config = dict(subentry_data)
        config["device_type"] = config.get("device_type", "power")
        self.subentry_data[subentry_id] = config
        self.pipelines[subentry_id] = AbstractorFilterPipeline(config)

    def remove_subentry(self, subentry_id: str) -> None:
        """Remove a subentry from central polling."""
        self.subentry_data.pop(subentry_id, None)
        self.pipelines.pop(subentry_id, None)
        self._last_notified_events.pop(subentry_id, None)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via central polling."""
        data: dict[str, float | None] = {}
        for subentry_id, config in self.subentry_data.items():
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

            pipeline = self.pipelines.get(subentry_id)
            if pipeline:
                net_subtract_raw = self._read_state(config.get(CONF_NET_SUBTRACT_ENTITY_ID))
                fallback_raw = self._read_state(config.get(CONF_FALLBACK_SOURCE_ENTITY_ID))
                fallback_condition_met = self._fallback_condition_met(config)
                val = pipeline.process_sources(
                    raw_states,
                    net_subtract_raw=net_subtract_raw,
                    fallback_raw=fallback_raw,
                    fallback_condition_met=fallback_condition_met,
                )
                data[subentry_id] = val
                await self._async_notify_debug(subentry_id, pipeline.last_event)

                if self.influx_exporter and val is not None:
                    await self.influx_exporter.async_push(source_ids[0], val)
        return data

    def _read_state(self, entity_id: str | None) -> str | None:
        """Read a raw HA state string for an optional entity_id."""
        if not entity_id:
            return None
        state_obj = self.hass.states.get(entity_id)
        return state_obj.state if state_obj else None

    def _fallback_condition_met(self, config: dict[str, Any]) -> bool:
        """Evaluate the REQ-COMP-004 fallback condition.

        No fallback source configured -> never eligible. A fallback source
        without a condition entity is always eligible when the primary is
        unavailable. With a condition entity, the fallback is only eligible
        while that entity's state matches the configured expected state.
        """
        if not config.get(CONF_FALLBACK_SOURCE_ENTITY_ID):
            return False
        condition_entity_id = config.get(CONF_FALLBACK_CONDITION_ENTITY_ID)
        if not condition_entity_id:
            return True
        expected_state = config.get(CONF_FALLBACK_CONDITION_STATE)
        return self._read_state(condition_entity_id) == expected_state

    async def _async_notify_debug(self, subentry_id: str, event: str | None) -> None:
        """Send deduplicated debug events through the existing HA notify group."""
        if event is None:
            self._last_notified_events.pop(subentry_id, None)
            return
        if self._last_notified_events.get(subentry_id) == event:
            return
        if not self.hass.states.is_state("input_boolean.automation_debugger", "on"):
            return
        if not self.hass.services.has_service("notify", "adminnotificationgroup"):
            return
        await self.hass.services.async_call(
            "notify",
            "adminnotificationgroup",
            {"message": f"Abstractor {subentry_id}: {event}"},
            blocking=False,
        )
        self._last_notified_events[subentry_id] = event
