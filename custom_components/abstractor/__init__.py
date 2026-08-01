"""The Abstractor integration."""
from __future__ import annotations

import logging
from functools import partial

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    SERVICE_EXPORT_DATA,
    SERVICE_IMPORT_DATA,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .coordinator import AbstractorDataUpdateCoordinator
from .repository.device_registry import DeviceRegistry
from .snapshot import build_snapshot, validate_snapshot

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]
_STORAGE_DATA = "storage"
IMPORT_SERVICE_SCHEMA = vol.Schema(
    {vol.Required("data"): vol.All(dict, validate_snapshot)}
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Abstractor from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if _STORAGE_DATA not in domain_data:
        domain_data[_STORAGE_DATA] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        domain_data["stored_snapshot"] = await domain_data[_STORAGE_DATA].async_load() or {}

    coordinator = domain_data.get("coordinator")
    is_new_coordinator = coordinator is None
    if is_new_coordinator:
        coordinator = AbstractorDataUpdateCoordinator(hass)
        domain_data["coordinator"] = coordinator

    if "registry" not in domain_data:
        domain_data["registry"] = DeviceRegistry()

    coordinator.add_entry(entry)
    domain_data[entry.entry_id] = entry.data
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    if is_new_coordinator:
        await coordinator.async_config_entry_first_refresh()
    else:
        await coordinator.async_request_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Setup services if not already setup
    if not hass.services.has_service(DOMAIN, SERVICE_EXPORT_DATA):
        hass.services.async_register(
            DOMAIN,
            SERVICE_EXPORT_DATA,
            partial(export_data_service, hass),
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_IMPORT_DATA,
            partial(import_data_service, hass),
            schema=IMPORT_SERVICE_SCHEMA,
        )
    await _save_snapshot(hass)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        domain_data = hass.data[DOMAIN]
        domain_data.pop(entry.entry_id, None)
        coordinator = domain_data.get("coordinator")
        if coordinator:
            coordinator.remove_entry(entry.entry_id)
            if not coordinator.entries:
                await coordinator.async_shutdown()
                domain_data.pop("coordinator", None)
                domain_data.pop("registry", None)
                await _save_snapshot(hass)
                hass.services.async_remove(DOMAIN, SERVICE_EXPORT_DATA)
                hass.services.async_remove(DOMAIN, SERVICE_IMPORT_DATA)

    return unload_ok

async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)
    return config_entry.version <= 1

async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply options without requiring a restart."""
    await hass.config_entries.async_reload(entry.entry_id)

async def _save_snapshot(hass: HomeAssistant) -> None:
    """Persist config and last coordinator values for support and restore."""
    domain_data = hass.data[DOMAIN]
    entries = domain_data.get("coordinator").entries if domain_data.get("coordinator") else {}
    snapshot = {
        **build_snapshot(
            entries,
            domain_data.get("coordinator").data
            if domain_data.get("coordinator")
            else {},
        ),
    }
    domain_data["stored_snapshot"] = snapshot
    await domain_data[_STORAGE_DATA].async_save(snapshot)


async def export_data_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Persist and log a complete integration snapshot."""
    await _save_snapshot(hass)
    _LOGGER.info("Abstractor data export completed")


async def import_data_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Import a snapshot into persistent storage for review and restore."""
    payload = validate_snapshot(call.data.get("data"))
    store = hass.data[DOMAIN][_STORAGE_DATA]
    await store.async_save(payload)
    hass.data[DOMAIN]["stored_snapshot"] = payload
    _LOGGER.info("Abstractor data import completed; config entries were not recreated")
