"""The Abstractor integration."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    ROOT_ENTRY_TITLE,
    ROOT_UNIQUE_ID,
    SERVICE_EXPORT_DATA,
    SERVICE_IMPORT_DATA,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUBENTRY_TYPE_SENSOR,
)
from .coordinator import AbstractorDataUpdateCoordinator
from .frontend import async_register_panel, async_unregister_panel
from .repository.device_registry import DeviceRegistry
from .snapshot import build_snapshot, validate_snapshot

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]
_STORAGE_DATA = "storage"
IMPORT_SERVICE_SCHEMA = vol.Schema(
    {vol.Required("data"): vol.All(dict, validate_snapshot)}
)
# The integration is configured through the UI only. async_setup exists purely
# for the one-time reconciliation below, so guard against it being taken as an
# invitation to configure `abstractor:` in YAML.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(frozen=True, slots=True)
class _SubentrySnapshotView:
    """One config subentry in the shape `build_snapshot` expects.

    Sensors live in subentries since the device-bundling migration, but a
    ConfigSubentry has no `options` or `version` of its own — both belong to
    the parent entry. Supplying them here keeps the persisted snapshot format
    identical to the one written before the migration.
    """

    data: Mapping[str, Any]
    options: Mapping[str, Any]
    title: str
    unique_id: str | None
    version: int


@callback
def _async_adopt_registry_entries(
    hass: HomeAssistant,
    root_entry: ConfigEntry,
    legacy_entry: ConfigEntry,
    subentry_id: str,
) -> None:
    """Re-point a legacy entry's registry rows at the root entry + subentry.

    This has to happen *before* the legacy entry is removed. Removing a config
    entry runs `async_clear_config_entry` on both the device and the entity
    registry, which deletes every row still owned by that entry; restoring a
    deleted row later only brings back its internal id and creation date, so
    the user-facing entity_id, custom name, icon, area and device name would
    be silently lost. Rows that no longer belong to the removed entry are
    simply left alone, which is what keeps REQ-CORE-001's stable-identity
    guarantee intact across the migration.
    """
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(
        device_registry, legacy_entry.entry_id
    ):
        device_registry.async_update_device(
            device.id,
            add_config_entry_id=root_entry.entry_id,
            add_config_subentry_id=subentry_id,
        )

    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(
        entity_registry, legacy_entry.entry_id
    ):
        entity_registry.async_update_entity(
            entity.entity_id,
            config_entry_id=root_entry.entry_id,
            config_subentry_id=subentry_id,
        )


@callback
def _async_attach_as_subentry(
    hass: HomeAssistant, root_entry: ConfigEntry, legacy_entry: ConfigEntry
) -> None:
    """Mirror one legacy entry into a subentry of the root entry.

    The subentry deliberately reuses the legacy entry's own `entry_id` as its
    `subentry_id` instead of letting ConfigSubentry mint a fresh ULID. An
    ungrouped sensor (every sensor predating device bundling) resolves its
    device identifier to `device_group_id or subentry_id` in sensor.py, which
    before the migration was effectively the config entry's id — so a random
    subentry_id would point the sensor at a different, brand-new device and
    orphan the user's existing one, area assignment and custom name included.
    """
    subentry = ConfigSubentry(
        data=MappingProxyType(dict(legacy_entry.data) | dict(legacy_entry.options)),
        subentry_id=legacy_entry.entry_id,
        subentry_type=SUBENTRY_TYPE_SENSOR,
        title=legacy_entry.title,
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, subentry)
    _async_adopt_registry_entries(hass, root_entry, legacy_entry, subentry.subentry_id)


@callback
def _async_promote_to_root(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Turn the first legacy entry into the singleton root entry, in place.

    A new root entry cannot be created here: `hass.config_entries.async_add`
    sets the entry up straight away, and because the domain is not in
    `hass.config.components` yet while its own `async_setup` is still running,
    that path re-enters `async_setup_component` for this very domain and waits
    on the in-flight setup future — a deadlock that stalls the integration for
    SLOW_SETUP_MAX_WAIT (300s) and then fails it (verified against the
    installed homeassistant 2025.3.0). Promoting an entry that already exists
    is a pure registry-side update, needs no setup, and additionally spares
    one entry the remove/recreate cycle.

    Order matters: the entry's own sensor data is mirrored into a subentry
    first, and only then is the entry's identity flipped. An interruption in
    between leaves an untouched legacy entry that merely carries an extra
    subentry, which the next run re-creates identically (same subentry_id) —
    never a root entry whose sensor data has already been cleared.
    """
    _async_attach_as_subentry(hass, entry, entry)
    hass.config_entries.async_update_entry(
        entry,
        unique_id=ROOT_UNIQUE_ID,
        title=ROOT_ENTRY_TITLE,
        data={},
        options={},
    )


async def _async_reconcile_legacy_entries(hass: HomeAssistant) -> None:
    """One-time structural migration: fold pre-bundling flat top-level entries
    into subentries under a single root entry.

    Not done via `async_migrate_entry`: that hook receives one existing
    ConfigEntry at a time and can only rewrite that entry's own data/version in
    place — it has no way for an entry to dissolve itself into a differently
    structured entry elsewhere.

    Idempotent and safe to interrupt: entries are converted one at a time
    (subentry attached and registry rows re-pointed first, legacy entry removed
    only afterwards), so a restart mid-run resumes with whatever entries are
    still standalone. Already-converted ones no longer show up in this
    function's own scan. Only config-entry structure changes; unique_ids,
    entity_ids and device identifiers are all preserved.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    root_entry = next(
        (entry for entry in entries if entry.unique_id == ROOT_UNIQUE_ID), None
    )
    legacy_entries = [
        entry for entry in entries if entry.unique_id != ROOT_UNIQUE_ID
    ]
    if not legacy_entries:
        return

    _LOGGER.debug(
        "Reconciling %s legacy Abstractor config entries into subentries",
        len(legacy_entries),
    )

    if root_entry is None:
        root_entry = legacy_entries.pop(0)
        _async_promote_to_root(hass, root_entry)

    for legacy_entry in legacy_entries:
        try:
            _async_attach_as_subentry(hass, root_entry, legacy_entry)
            await hass.config_entries.async_remove(legacy_entry.entry_id)
        except Exception:
            # The entry survives as a standalone entry, so the next start
            # simply retries it: re-attaching writes the identical subentry
            # under the identical subentry_id. Letting this bubble up instead
            # would fail the whole domain setup and leave the user without any
            # working sensors at all.
            _LOGGER.exception(
                "Could not convert Abstractor entry %s into a subentry; "
                "it stays a standalone entry and is retried on next start",
                legacy_entry.entry_id,
            )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Abstractor integration.

    Runs once for the whole domain, before any per-entry async_setup_entry.
    """
    await _async_reconcile_legacy_entries(hass)
    return True


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

    # Polling is per sensor subentry, not per config entry: the root entry
    # itself carries no sensor configuration since device bundling landed.
    for subentry_id, subentry in entry.subentries.items():
        coordinator.add_subentry(subentry_id, dict(subentry.data))
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
    await async_register_panel(hass)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        domain_data = hass.data[DOMAIN]
        domain_data.pop(entry.entry_id, None)
        coordinator = domain_data.get("coordinator")
        if coordinator:
            for subentry_id in entry.subentries:
                coordinator.remove_subentry(subentry_id)
            if not coordinator.subentry_data:
                # Snapshot the coordinator's last-known values BEFORE tearing
                # it down: _save_snapshot reads domain_data["coordinator"],
                # so popping it first would persist an empty snapshot right
                # when a restore would matter most.
                await _save_snapshot(hass)
                await coordinator.async_shutdown()
                domain_data.pop("coordinator", None)
                domain_data.pop("registry", None)
                hass.services.async_remove(DOMAIN, SERVICE_EXPORT_DATA)
                hass.services.async_remove(DOMAIN, SERVICE_IMPORT_DATA)
                await async_unregister_panel(hass)

    return unload_ok

async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate an old config entry to CONFIG_ENTRY_VERSION (REQ-NFA-004).

    Each migration step below transforms exactly one version to the next and
    calls hass.config_entries.async_update_entry with the new data/version.
    A future breaking change adds one more `if config_entry.version == N`
    block instead of touching the ones before it.
    """
    _LOGGER.debug(
        "Migrating Abstractor entry %s from version %s to %s",
        config_entry.entry_id,
        config_entry.version,
        CONFIG_ENTRY_VERSION,
    )

    if config_entry.version > CONFIG_ENTRY_VERSION:
        # Entry was created by a newer version of the integration; refuse to
        # guess how to downgrade it instead of silently corrupting it.
        _LOGGER.error(
            "Abstractor entry %s has version %s, newer than supported %s",
            config_entry.entry_id,
            config_entry.version,
            CONFIG_ENTRY_VERSION,
        )
        return False

    # No migration steps exist yet (still on the original version 1 schema).
    # Placeholder for the first real step:
    # if config_entry.version == 1:
    #     new_data = {**config_entry.data, ...}
    #     hass.config_entries.async_update_entry(
    #         config_entry, data=new_data, version=2
    #     )

    return True

async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply options without requiring a restart."""
    await hass.config_entries.async_reload(entry.entry_id)

@callback
def _async_snapshot_entries(hass: HomeAssistant) -> dict[str, _SubentrySnapshotView]:
    """Collect every configured sensor subentry, keyed by subentry id.

    Keyed the same way as the coordinator's values, so a snapshot's config and
    its last-known readings line up entry by entry.
    """
    return {
        subentry_id: _SubentrySnapshotView(
            data=subentry.data,
            options={},
            title=subentry.title,
            unique_id=subentry.unique_id,
            version=entry.version,
        )
        for entry in hass.config_entries.async_entries(DOMAIN)
        for subentry_id, subentry in entry.subentries.items()
    }


async def _save_snapshot(hass: HomeAssistant) -> None:
    """Persist config and last coordinator values for support and restore."""
    domain_data = hass.data[DOMAIN]
    coordinator = domain_data.get("coordinator")
    values = (coordinator.data or {}) if coordinator else {}
    snapshot = build_snapshot(_async_snapshot_entries(hass), values)
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
