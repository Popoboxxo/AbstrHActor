"""The Abstractor integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import storage
from .const import DOMAIN
from .coordinator import AbstractorDataUpdateCoordinator
from .repository.device_registry import DeviceRegistry

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Abstractor from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})

    if "coordinator" not in domain_data:
        coordinator = AbstractorDataUpdateCoordinator(hass)
        await coordinator.async_config_entry_first_refresh()
        domain_data["coordinator"] = coordinator
    else:
        coordinator = domain_data["coordinator"]

    if "registry" not in domain_data:
        domain_data["registry"] = DeviceRegistry()
        # Storage logic would initialize the registry here

    coordinator.add_entry(entry)
    domain_data[entry.entry_id] = entry.data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Setup services if not already setup
    if not hass.services.has_service(DOMAIN, "export_data"):
        hass.services.async_register(DOMAIN, "export_data", export_data_service)
        hass.services.async_register(DOMAIN, "import_data", import_data_service)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator:
            coordinator.remove_entry(entry.entry_id)

    return unload_ok

async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)
    return config_entry.version <= 1

async def export_data_service(call):
    """Export the internal state of all abstractors."""

async def import_data_service(call):
    """Import the internal state of all abstractors."""
