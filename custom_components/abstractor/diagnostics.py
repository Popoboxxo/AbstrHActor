"""Diagnostics support for Abstractor."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_INFLUX_TOKEN, DOMAIN
from .coordinator import AbstractorDataUpdateCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: AbstractorDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]

    entry_data = deepcopy(entry.as_dict())
    options = entry_data.get("options")
    if isinstance(options, dict) and CONF_INFLUX_TOKEN in options:
        options[CONF_INFLUX_TOKEN] = "***"

    return {
        "entry": entry_data,
        "coordinator_data": coordinator.data or {},
        "pipeline_config": {
            subentry_id: pipeline.config
            for subentry_id, pipeline in coordinator.pipelines.items()
            if subentry_id in entry.subentries
        },
    }
