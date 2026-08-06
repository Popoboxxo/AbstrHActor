"""Diagnostics support for Abstractor."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import AbstractorDataUpdateCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: AbstractorDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]

    return {
        "entry": entry.as_dict(),
        "coordinator_data": coordinator.data or {},
        "pipeline_config": {
            key: value.config
            for key, value in coordinator.pipelines.items()
            if key == entry.entry_id
        },
    }
