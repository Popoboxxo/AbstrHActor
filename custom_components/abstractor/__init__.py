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
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
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


def _pre_migration_unique_id(data: Mapping[str, Any]) -> str:
    """Recompute the unique_id the sensor of a pre-bundling entry already has.

    A frozen copy of the identity logic the sensor platform used before device
    bundling landed, deliberately not delegated to `sensor.py`: it describes
    historical behaviour and has to keep describing it even when the current
    derivation changes.

    Derived from the entry's `data` only, never its `options` — exactly as the
    old sensor platform did. The pre-bundling options flow (REQ-CORE-007,
    hardware swap) wrote CONF_SOURCE_ENTITY_IDS into `options`, and identity
    ignored that on purpose so the entity kept its unique_id, and with it its
    recorder history, across a source swap.
    """
    explicit_legacy_id = data.get(CONF_LEGACY_UNIQUE_ID)
    if explicit_legacy_id:
        # REQ-CORE-003: a migrated YAML template sensor's id always won.
        return str(explicit_legacy_id)

    device_type = data.get(CONF_DEVICE_TYPE, "")
    identity_source_ids = data.get(CONF_SOURCE_ENTITY_IDS) or [
        data.get(CONF_SOURCE_ENTITY_ID)
    ]
    identity_source_ids = [source for source in identity_source_ids if source]
    if len(identity_source_ids) == 1:
        return f"abstractor_{identity_source_ids[0]}_{device_type}"
    return f"abstractor_{device_type}_{'_'.join(sorted(identity_source_ids))}"


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

    The three steps below must stay in this order, see the comment on the last
    one.
    """
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    is_promotion = legacy_entry.entry_id == root_entry.entry_id
    devices = dr.async_entries_for_config_entry(device_registry, legacy_entry.entry_id)
    device_ids = [device.id for device in devices]
    # A disabled config entry stamps `disabled_by=CONFIG_ENTRY` on its own
    # registry rows. Folding such an entry into an ENABLED root leaves that
    # stamp behind, now claiming to follow an entry that is not disabled:
    # nothing ever revisits it (HA only re-enables those rows when an entry's
    # own disabled_by changes), so the sensor stays dark, and a row disabled
    # "by config entry" cannot be re-enabled from the entity dialog either.
    # Clear it here — the same thing HA does when an entry is re-enabled, and
    # consistent with a disabled entry that has no registry rows yet, whose
    # sensor simply comes back enabled. Rows the user disabled explicitly are
    # left untouched, and if the root itself ends up disabled (every legacy
    # entry was), the stamp still matches reality and stays.
    revive = legacy_entry.disabled_by is not None and root_entry.disabled_by is None

    for device in devices:
        device_registry.async_update_device(
            device.id,
            add_config_entry_id=root_entry.entry_id,
            add_config_subentry_id=subentry_id,
        )
        if revive and device.disabled_by is dr.DeviceEntryDisabler.CONFIG_ENTRY:
            device_registry.async_update_device(device.id, disabled_by=None)

    for entity in er.async_entries_for_config_entry(
        entity_registry, legacy_entry.entry_id
    ):
        entity_registry.async_update_entity(
            entity.entity_id,
            config_entry_id=root_entry.entry_id,
            config_subentry_id=subentry_id,
        )
        if revive and entity.disabled_by is er.RegistryEntryDisabler.CONFIG_ENTRY:
            entity_registry.async_update_entity(entity.entity_id, disabled_by=None)

    if not is_promotion:
        # Nothing else to do: removing the legacy entry afterwards takes its
        # whole device link with it.
        return

    for device_id in device_ids:
        # The promoted entry keeps its entry_id, so adding the subentry link
        # above was a union, not a replacement: the device is now linked to
        # BOTH the root's main-entry slot (`None`) and its subentry. That
        # stale `None` link outlives the subentry — deleting the sensor later
        # drops only the subentry link, the device stays behind at
        # `{entry_id: {None}}`, is never cleaned up and cannot be removed
        # through the UI either. Drop it now; the subentry link owns the
        # device from here on.
        #
        # Strictly after the entity loop above: the entity registry listens
        # for device updates and removes every entity whose
        # `config_subentry_id` is no longer among the device's subentries for
        # its config entry (entity_registry.py, "Remove entities which belong
        # to config subentries no longer associated with the device"). That
        # listener is a @callback, so it runs inline inside async_update_device
        # — dropping the `None` link while the rows still carry
        # `config_subentry_id=None` deletes them, and the platform then
        # re-creates them from `suggested_object_id`, silently discarding a
        # renamed entity_id and the recorder history attached to it
        # (reproduced against homeassistant 2025.3.0).
        device_registry.async_update_device(
            device_id,
            remove_config_entry_id=root_entry.entry_id,
            remove_config_subentry_id=None,
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
    # Runtime config is the data|options merge: the polling pipeline has to
    # read the CURRENT source, including one a pre-migration hardware swap
    # wrote into `options` (REQ-CORE-007). Identity must NOT move with it,
    # though — after the migration the subentry's data is the only place
    # config lives, so a swapped source in the merge would make sensor.py
    # compute a different unique_id than the entity already has, orphaning it
    # and its recorder history. Pinning the pre-migration unique_id as
    # CONF_LEGACY_UNIQUE_ID keeps identity exactly where it was: sensor.py
    # gives that key precedence over every other derivation, so it also
    # survives later reconfigures of the subentry.
    data = dict(legacy_entry.data) | dict(legacy_entry.options)
    data[CONF_LEGACY_UNIQUE_ID] = _pre_migration_unique_id(legacy_entry.data)
    subentry = ConfigSubentry(
        data=MappingProxyType(data),
        subentry_id=legacy_entry.entry_id,
        subentry_type=SUBENTRY_TYPE_SENSOR,
        title=legacy_entry.title,
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, subentry)
    _async_adopt_registry_entries(hass, root_entry, legacy_entry, subentry.subentry_id)


def _select_promotion_target(legacy_entries: list[ConfigEntry]) -> ConfigEntry:
    """Pick the legacy entry that becomes the singleton root entry.

    An ENABLED entry whenever one exists. `async_entries()` also returns
    user-disabled entries, and the promoted entry becomes the parent of every
    migrated sensor — promote a disabled one and the root entry stays disabled
    (ConfigEntryState.NOT_LOADED), taking every perfectly healthy sensor in the
    installation down with it, with nothing pointing the user at the cause.

    The disabled state cannot simply be cleared here:
    `async_set_disabled_by` reloads the entry, which re-enters
    `async_setup_component` for this domain and waits on the very setup future
    its own caller is still computing — the same deadlock as `async_add`
    (both verified against the installed homeassistant 2025.3.0).

    If every legacy entry is disabled there is no healthy candidate. The
    migration still runs (leaving entries flat would strand them: a flat entry
    carries no subentries and therefore produces no entities at all under the
    bundled layout), and the root simply inherits that disabled state — which
    changes nothing for the user, since no sensor of theirs was running
    before the upgrade either. Re-enabling the single root entry in the UI
    then brings all of them up at once, so the warning below says so.
    """
    for entry in legacy_entries:
        if entry.disabled_by is None:
            return entry

    _LOGGER.warning(
        "Every Abstractor config entry is disabled; the migrated Abstractor "
        "entry stays disabled too. Re-enable Abstractor under Settings > "
        "Devices & Services to bring the migrated sensors back"
    )
    return legacy_entries[0]


@callback
def _async_promote_to_root(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Turn the selected legacy entry into the singleton root entry, in place.

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
        root_entry = _select_promotion_target(legacy_entries)
        legacy_entries.remove(root_entry)
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
