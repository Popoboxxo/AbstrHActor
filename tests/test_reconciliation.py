"""Test the one-time legacy-entry reconciliation (device bundling migration).

Verifies the mechanism documented in
docs/superpowers/specs/2026-08-08-device-bundling-design.md's "Migration"
section: async_setup (not async_migrate_entry, which can't restructure
across entries) converts existing flat top-level entries into subentries
under a singleton root entry.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abstractor import (
    _async_reconcile_legacy_entries,
    _pre_migration_unique_id,
)
from custom_components.abstractor.const import (
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    DOMAIN,
    ROOT_UNIQUE_ID,
)


def _legacy_entry(
    hass: HomeAssistant, source_entity_id: str, device_type: str
) -> MockConfigEntry:
    """Add a pre-bundling flat top-level entry, exactly as older versions wrote it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"abstractor_{device_type}_{source_entity_id}",
        data={CONF_DEVICE_TYPE: device_type, CONF_SOURCE_ENTITY_ID: source_entity_id},
    )
    entry.add_to_hass(hass)
    return entry


async def test_reconciliation_converts_legacy_entries_to_subentries(
    hass: HomeAssistant,
) -> None:
    """Two legacy flat entries become two subentries under one root entry."""
    _legacy_entry(hass, "sensor.a", "power")
    _legacy_entry(hass, "sensor.b", "energy")

    await _async_reconcile_legacy_entries(hass)

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    root_entry = entries[0]
    assert root_entry.unique_id == ROOT_UNIQUE_ID
    assert len(root_entry.subentries) == 2

    subentry_data = {
        s.data[CONF_SOURCE_ENTITY_ID]: s.data for s in root_entry.subentries.values()
    }
    assert subentry_data["sensor.a"][CONF_DEVICE_TYPE] == "power"
    assert subentry_data["sensor.b"][CONF_DEVICE_TYPE] == "energy"


async def test_reconciliation_is_idempotent(hass: HomeAssistant) -> None:
    """Running reconciliation twice (e.g. a restart after partial completion)
    does not create a second root entry or duplicate subentries."""
    _legacy_entry(hass, "sensor.a", "power")

    await _async_reconcile_legacy_entries(hass)
    await _async_reconcile_legacy_entries(hass)

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert len(entries[0].subentries) == 1


async def test_reconciliation_skips_fresh_install(hass: HomeAssistant) -> None:
    """No legacy entries at all -> no root entry is created by reconciliation
    (a fresh install creates the root entry through the normal config flow
    instead, the first time a user adds the integration)."""
    await _async_reconcile_legacy_entries(hass)

    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_reconciliation_keeps_entry_id_as_subentry_id(
    hass: HomeAssistant,
) -> None:
    """Each subentry keeps the id of the legacy entry it was created from.

    sensor.py derives a sensor's device identifier as
    `device_group_id or subentry_id`. No sensor predating this feature has a
    device group, so their device identifier is effectively the old config
    entry's id. Letting ConfigSubentry mint a fresh ULID instead would point
    every migrated sensor at a brand-new device on upgrade and orphan the
    user's existing one (area, custom name, dashboard references), even though
    the entity's own unique_id would still be correct.

    Both conversion paths are covered: the first legacy entry is promoted into
    the root entry in place, the second is attached and then removed.
    """
    legacy_a = _legacy_entry(hass, "sensor.a", "power")
    legacy_b = _legacy_entry(hass, "sensor.b", "energy")
    legacy_ids = {legacy_a.entry_id, legacy_b.entry_id}

    await _async_reconcile_legacy_entries(hass)

    root_entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert set(root_entry.subentries) == legacy_ids

    for legacy_id, subentry in root_entry.subentries.items():
        assert subentry.subentry_id == legacy_id
        # Ungrouped, so sensor.py falls back to subentry_id — which is exactly
        # the device identifier these sensors already have today.
        assert CONF_DEVICE_GROUP_ID not in subentry.data
        device_key = subentry.data.get(CONF_DEVICE_GROUP_ID) or subentry.subentry_id
        assert device_key == legacy_id


async def test_reconciliation_preserves_registry_identity(
    hass: HomeAssistant,
) -> None:
    """Removing the old entry must not take its registry rows with it.

    Covers the entry that gets removed (not the promoted one): its device and
    entity registry rows are re-pointed at the root entry first, so
    async_remove's registry cleanup finds nothing to delete. Without that, HA
    deletes both rows and only restores their internal ids — the user's
    renamed entity_id, custom name, icon, area and device name would be gone,
    breaking recorder history along with them.
    """
    _legacy_entry(hass, "sensor.a", "power")
    legacy_b = _legacy_entry(hass, "sensor.b", "energy")

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    device = device_registry.async_get_or_create(
        config_entry_id=legacy_b.entry_id,
        identifiers={(DOMAIN, legacy_b.entry_id)},
        name="Abstract Energy",
    )
    device_registry.async_update_device(
        device.id, name_by_user="Cellar meter", area_id="cellar"
    )
    entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "abstractor_sensor.b_energy",
        config_entry=legacy_b,
        device_id=device.id,
        suggested_object_id="abstract_energy",
    )
    entity_registry.async_update_entity(
        entity.entity_id,
        new_entity_id="sensor.keller_zaehler",
        name="Keller Zähler",
        icon="mdi:flash",
    )

    await _async_reconcile_legacy_entries(hass)

    root_entry = hass.config_entries.async_entries(DOMAIN)[0]

    surviving_device = device_registry.async_get(device.id)
    assert surviving_device is not None
    assert device.id not in device_registry.deleted_devices
    assert (DOMAIN, legacy_b.entry_id) in surviving_device.identifiers
    assert surviving_device.name_by_user == "Cellar meter"
    assert surviving_device.area_id == "cellar"
    assert root_entry.entry_id in surviving_device.config_entries

    surviving_entity = entity_registry.async_get("sensor.keller_zaehler")
    assert surviving_entity is not None
    assert surviving_entity.unique_id == "abstractor_sensor.b_energy"
    assert surviving_entity.name == "Keller Zähler"
    assert surviving_entity.icon == "mdi:flash"
    assert surviving_entity.device_id == device.id
    assert surviving_entity.config_entry_id == root_entry.entry_id
    assert surviving_entity.config_subentry_id == legacy_b.entry_id


async def test_reconciliation_continues_after_a_failing_entry(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One entry failing to convert must not abort the whole migration.

    Per the design doc's failure handling: the failed entry stays standalone
    and is retried on the next start, while every other entry is converted.
    Aborting instead would fail the domain setup and leave the user with no
    working sensors at all.
    """
    _legacy_entry(hass, "sensor.a", "power")
    legacy_b = _legacy_entry(hass, "sensor.b", "energy")
    legacy_c = _legacy_entry(hass, "sensor.c", "water")

    original_remove = hass.config_entries.async_remove

    async def _failing_remove(entry_id: str) -> dict[str, Any]:
        if entry_id == legacy_b.entry_id:
            raise HomeAssistantError("simulated removal failure")
        return await original_remove(entry_id)

    monkeypatch.setattr(hass.config_entries, "async_remove", _failing_remove)

    await _async_reconcile_legacy_entries(hass)

    remaining = {entry.entry_id for entry in hass.config_entries.async_entries(DOMAIN)}
    assert legacy_b.entry_id in remaining, "failed entry must survive for a retry"
    assert legacy_c.entry_id not in remaining, "later entries are still converted"
    assert legacy_b.data[CONF_SOURCE_ENTITY_ID] == "sensor.b"

    root_entry = next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.unique_id == ROOT_UNIQUE_ID
    )
    assert legacy_c.entry_id in root_entry.subentries
    assert "Could not convert Abstractor entry" in caplog.text


async def test_async_setup_migrates_and_loads_the_integration(
    hass: HomeAssistant,
) -> None:
    """End-to-end upgrade: setting the domain up migrates and loads cleanly.

    The asyncio timeout is the actual assertion for one half of this: awaiting
    hass.config_entries.async_add() inside async_setup re-enters
    async_setup_component for this same domain and waits on its own in-flight
    setup future, which stalls the integration for SLOW_SETUP_MAX_WAIT (300s)
    and then fails it. Reaching the asserts below at all proves the domain
    still sets up synchronously.
    """
    legacy_a = _legacy_entry(hass, "sensor.a", "power")
    legacy_b = _legacy_entry(hass, "sensor.b", "energy")
    legacy_ids = {legacy_a.entry_id, legacy_b.entry_id}

    async with asyncio.timeout(60):
        assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    root_entry = entries[0]
    assert root_entry.state is ConfigEntryState.LOADED
    assert set(root_entry.subentries) == legacy_ids

    # Every migrated sensor is registered, and still sits on the very device
    # identifier it used before the migration.
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    for legacy_id, unique_id in (
        (legacy_a.entry_id, "abstractor_sensor.a_power"),
        (legacy_b.entry_id, "abstractor_sensor.b_energy"),
    ):
        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entity_id is not None
        registry_entry = entity_registry.async_get(entity_id)
        assert registry_entry is not None
        assert registry_entry.config_subentry_id == legacy_id
        device = device_registry.async_get(registry_entry.device_id)
        assert device is not None
        assert (DOMAIN, legacy_id) in device.identifiers


async def test_reconciliation_pins_identity_across_a_pre_migration_swap(
    hass: HomeAssistant,
) -> None:
    """A hardware swap done BEFORE the migration must not move the unique_id.

    Pre-bundling, the options flow (REQ-CORE-007) wrote the new source into
    `entry.options`, while identity was derived from `entry.data` alone — so
    the entity kept its unique_id, entity_id and recorder history across the
    swap. After the migration a subentry has no options at all: `data` is the
    merge of both, which is what the polling pipeline needs to read the
    CURRENT source, but it would also make sensor.py derive a *different*
    unique_id from the swapped source, orphaning the user's entity and
    silently starting a second one. The pinned CONF_LEGACY_UNIQUE_ID is what
    keeps the two apart.
    """
    legacy = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_power_sensor.old_shelly",
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.old_shelly"},
        options={CONF_SOURCE_ENTITY_IDS: ["sensor.new_tasmota"]},
    )
    legacy.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=legacy.entry_id,
        identifiers={(DOMAIN, legacy.entry_id)},
        name="Abstract Power",
    )
    entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "abstractor_sensor.old_shelly_power",
        config_entry=legacy,
        device_id=device.id,
        suggested_object_id="abstract_power",
    )
    entity_registry.async_update_entity(
        entity.entity_id, new_entity_id="sensor.wohnzimmer"
    )

    hass.states.async_set("sensor.old_shelly", "7")
    hass.states.async_set("sensor.new_tasmota", "42")

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    root_entry = hass.config_entries.async_entries(DOMAIN)[0]

    # Exactly one Abstractor entity: the original one, unchanged. A second row
    # here would be the orphaning bug (old entity dark, new one taking over).
    rows = er.async_entries_for_config_entry(entity_registry, root_entry.entry_id)
    assert [(row.unique_id, row.entity_id) for row in rows] == [
        ("abstractor_sensor.old_shelly_power", "sensor.wohnzimmer")
    ]

    # ... while the value still follows the swapped-in source, i.e. the
    # data|options merge is intact for runtime purposes.
    state = hass.states.get("sensor.wohnzimmer")
    assert state is not None
    assert state.state == "42.0"


async def test_reconciliation_pins_identity_for_a_converted_entry(
    hass: HomeAssistant,
) -> None:
    """Same guarantee for an entry that is attached and removed, not promoted."""
    _legacy_entry(hass, "sensor.plain", "power")
    swapped = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_energy_sensor.old",
        data={CONF_DEVICE_TYPE: "energy", CONF_SOURCE_ENTITY_ID: "sensor.old"},
        options={CONF_SOURCE_ENTITY_IDS: ["sensor.new"]},
    )
    swapped.add_to_hass(hass)

    await _async_reconcile_legacy_entries(hass)

    root_entry = hass.config_entries.async_entries(DOMAIN)[0]
    subentry = root_entry.subentries[swapped.entry_id]
    assert subentry.data[CONF_LEGACY_UNIQUE_ID] == "abstractor_sensor.old_energy"
    assert subentry.data[CONF_SOURCE_ENTITY_IDS] == ["sensor.new"]


async def test_reconciliation_keeps_an_explicit_legacy_unique_id(
    hass: HomeAssistant,
) -> None:
    """An entry that already pins a YAML template id keeps exactly that id."""
    legacy = MockConfigEntry(
        domain=DOMAIN,
        unique_id="fridge_power_template",
        data={
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.fridge",
            CONF_LEGACY_UNIQUE_ID: "fridge_power_template",
        },
        options={CONF_SOURCE_ENTITY_IDS: ["sensor.fridge_new"]},
    )
    legacy.add_to_hass(hass)

    await _async_reconcile_legacy_entries(hass)

    root_entry = hass.config_entries.async_entries(DOMAIN)[0]
    subentry = root_entry.subentries[legacy.entry_id]
    assert subentry.data[CONF_LEGACY_UNIQUE_ID] == "fridge_power_template"


def test_pre_migration_unique_id_replicates_the_old_derivation() -> None:
    """The frozen copy of the pre-bundling identity logic, branch by branch."""
    assert (
        _pre_migration_unique_id(
            {CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.a"}
        )
        == "abstractor_sensor.a_power"
    )
    assert (
        _pre_migration_unique_id(
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_IDS: ["sensor.b", "sensor.a"],
            }
        )
        == "abstractor_power_sensor.a_sensor.b"
    )
    assert (
        _pre_migration_unique_id(
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_LEGACY_UNIQUE_ID: "fridge_power_template",
            }
        )
        == "fridge_power_template"
    )


async def test_reconciliation_promotes_an_enabled_entry(hass: HomeAssistant) -> None:
    """A disabled legacy entry must never become the root entry.

    The promoted entry becomes the parent of every migrated sensor, and its
    disabled state cannot be cleared from async_setup (async_set_disabled_by
    reloads the entry, which re-enters async_setup_component for this domain
    and deadlocks on its own setup future). Promoting a disabled entry would
    leave the root NOT_LOADED and take every healthy sensor down with it.
    """
    disabled = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_power_sensor.a",
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.a"},
        disabled_by=ConfigEntryDisabler.USER,
    )
    disabled.add_to_hass(hass)
    healthy = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_energy_sensor.b",
        data={CONF_DEVICE_TYPE: "energy", CONF_SOURCE_ENTITY_ID: "sensor.b"},
    )
    healthy.add_to_hass(hass)

    hass.states.async_set("sensor.a", "11")
    hass.states.async_set("sensor.b", "22")

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    root_entry = entries[0]
    assert root_entry.entry_id == healthy.entry_id
    assert root_entry.disabled_by is None
    assert root_entry.state is ConfigEntryState.LOADED
    assert set(root_entry.subentries) == {disabled.entry_id, healthy.entry_id}

    entity_registry = er.async_get(hass)
    for unique_id in ("abstractor_sensor.a_power", "abstractor_sensor.b_energy"):
        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entity_id is not None, f"no entity for {unique_id}"
        assert hass.states.get(entity_id) is not None, f"{entity_id} has no state"


async def test_reconciliation_revives_rows_of_a_disabled_entry(
    hass: HomeAssistant,
) -> None:
    """Rows stamped disabled_by=CONFIG_ENTRY follow the entry they end up under.

    A disabled entry's registry rows carry `disabled_by=CONFIG_ENTRY`. Once
    folded into an ENABLED root that stamp claims to follow an entry that is
    not disabled: HA never revisits it, so the sensor would stay dark forever
    and the entity dialog offers no way to re-enable it — while an equally
    disabled entry that never got as far as creating registry rows comes back
    enabled. Same intent, opposite outcome; the migration levels that out.
    """
    disabled = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_power_sensor.a",
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.a"},
        disabled_by=ConfigEntryDisabler.USER,
    )
    disabled.add_to_hass(hass)
    _legacy_entry(hass, "sensor.b", "energy")

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=disabled.entry_id,
        identifiers={(DOMAIN, disabled.entry_id)},
        name="Abstract Power",
        disabled_by=dr.DeviceEntryDisabler.CONFIG_ENTRY,
    )
    entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "abstractor_sensor.a_power",
        config_entry=disabled,
        device_id=device.id,
        suggested_object_id="abstract_power",
        disabled_by=er.RegistryEntryDisabler.CONFIG_ENTRY,
    )

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    migrated_device = device_registry.async_get(device.id)
    assert migrated_device is not None
    assert migrated_device.disabled_by is None
    surviving = entity_registry.async_get(entity.entity_id)
    assert surviving is not None
    assert surviving.disabled_by is None
    assert hass.states.get(entity.entity_id) is not None


async def test_reconciliation_with_every_entry_disabled(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """No enabled candidate: migrate anyway, keep the disabled state, say so.

    Leaving the entries flat instead would strand them — a flat entry carries
    no subentries and therefore produces no entities at all under the bundled
    layout, so re-enabling it later would give the user nothing. Inheriting
    the disabled state changes nothing for them (no sensor was running before
    the upgrade either) and one click on the single root entry brings them all
    back, which is what the logged warning points at.
    """
    first = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_power_sensor.a",
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.a"},
        disabled_by=ConfigEntryDisabler.USER,
    )
    first.add_to_hass(hass)
    second = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_energy_sensor.b",
        data={CONF_DEVICE_TYPE: "energy", CONF_SOURCE_ENTITY_ID: "sensor.b"},
        disabled_by=ConfigEntryDisabler.USER,
    )
    second.add_to_hass(hass)

    await _async_reconcile_legacy_entries(hass)

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    root_entry = entries[0]
    assert root_entry.unique_id == ROOT_UNIQUE_ID
    assert root_entry.disabled_by is ConfigEntryDisabler.USER
    assert set(root_entry.subentries) == {first.entry_id, second.entry_id}
    assert "Every Abstractor config entry is disabled" in caplog.text


async def test_reconciliation_drops_the_promoted_entrys_stale_device_link(
    hass: HomeAssistant,
) -> None:
    """The promoted entry's device must end up owned by its subentry alone.

    Adding the subentry link is a union: the device would stay linked to the
    root's main-entry slot (`None`) as well. Deleting the sensor later drops
    only the subentry link, so the device would linger at `{entry_id: {None}}`
    forever — a ghost with no entities that cannot be removed from the UI.
    """
    legacy = _legacy_entry(hass, "sensor.a", "power")
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=legacy.entry_id,
        identifiers={(DOMAIN, legacy.entry_id)},
        name="Abstract Power",
    )

    await _async_reconcile_legacy_entries(hass)

    root_entry = hass.config_entries.async_entries(DOMAIN)[0]
    migrated = device_registry.async_get(device.id)
    assert migrated is not None
    assert migrated.config_entries_subentries == {root_entry.entry_id: {legacy.entry_id}}

    # ... and the device is therefore cleaned up together with its sensor.
    hass.config_entries.async_remove_subentry(root_entry, legacy.entry_id)
    assert device_registry.async_get(device.id) is None
