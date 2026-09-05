"""Regression tests for the config entry setup/unload lifecycle (I1).

Covers two related bugs found in the final whole-branch review, both rooted
in the same gap: the subentry-sync loop in async_setup_entry only ever ADDED
subentries to the coordinator, never pruned ones no longer present in
entry.subentries. By the time the update-listener-triggered reload runs
after HA's own subentry removal, entry.subentries already excludes the
deleted subentry_id — so coordinator.remove_subentry was never called for
it, and it stayed a "ghost", polled forever.

1. The removed sensor's source kept getting polled forever (never actually
   pruned from the coordinator).

2. Because a ghost id was never in entry.subentries to be cleaned up by
   async_unload_entry's own `for subentry_id in entry.subentries:` loop,
   coordinator.subentry_data could never truly reach empty again after a
   single subentry had been removed on its own — so removing the WHOLE
   integration afterwards never fully tore the coordinator down,
   unregistered services, or removed the sidebar panel either.

async_setup_entry now prunes any coordinator id no longer present in
entry.subentries before (re-)adding the current ones, which keeps the two in
sync after every setup/reload and fixes both symptoms — async_unload_entry's
existing `if not coordinator.subentry_data` teardown gate needed no change,
it simply becomes reachable/correct again once ghosts can no longer
accumulate.
"""
from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abstractor.const import (
    CONF_DEVICE_TYPE,
    CONF_INFLUX_BUCKET,
    CONF_INFLUX_HOST,
    CONF_INFLUX_ORG,
    CONF_INFLUX_TOKEN,
    CONF_POLL_INTERVAL,
    CONF_SOURCE_ENTITY_ID,
    DOMAIN,
    SERVICE_EXPORT_DATA,
    SERVICE_IMPORT_DATA,
    SUBENTRY_TYPE_SENSOR,
)
from custom_components.abstractor.influx_exporter import InfluxExporter


async def _setup_root_with_subentries(
    hass: HomeAssistant, count: int
) -> tuple[MockConfigEntry, list[str]]:
    """Create the singleton root entry with `count` sensor subentries, loaded."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    subentry_ids: list[str] = []
    for index in range(count):
        subentry = ConfigSubentry(
            data={
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: f"sensor.s{index}",
            },
            subentry_type=SUBENTRY_TYPE_SENSOR,
            title=f"Abstract power {index}",
            unique_id=None,
        )
        hass.config_entries.async_add_subentry(root_entry, subentry)
        subentry_ids.append(subentry.subentry_id)

    assert await hass.config_entries.async_setup(root_entry.entry_id)
    await hass.async_block_till_done()
    return root_entry, subentry_ids


async def test_removing_one_subentry_stops_its_polling(hass: HomeAssistant) -> None:
    """Deleting a single subentry must prune it from the coordinator, not
    leave it polled forever."""
    root_entry, subentry_ids = await _setup_root_with_subentries(hass, 2)
    keep_id, remove_id = subentry_ids

    coordinator = hass.data[DOMAIN]["coordinator"]
    assert set(coordinator.subentry_data) == {keep_id, remove_id}

    hass.config_entries.async_remove_subentry(root_entry, remove_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN]["coordinator"]
    assert remove_id not in coordinator.subentry_data
    assert remove_id not in coordinator.pipelines
    assert keep_id in coordinator.subentry_data


async def test_reload_after_subentry_removal_keeps_remaining_sensor_polled(
    hass: HomeAssistant,
) -> None:
    """The surviving sensor must keep reporting data across the reload that
    a sibling subentry's removal triggers — pruning the deleted one must not
    also disturb the one that's still there."""
    root_entry, subentry_ids = await _setup_root_with_subentries(hass, 2)
    keep_id, remove_id = subentry_ids

    hass.states.async_set("sensor.s0", "10")
    hass.states.async_set("sensor.s1", "20")

    hass.config_entries.async_remove_subentry(root_entry, remove_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN]["coordinator"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert keep_id in coordinator.data
    assert coordinator.data[keep_id] == 10.0


async def test_unloading_the_only_subentry_tears_down_the_coordinator(
    hass: HomeAssistant,
) -> None:
    """Unloading the singleton entry while it has exactly one subentry left
    must fully tear the coordinator, its services and the sidebar panel
    down — the simple case, which already worked before this fix and must
    keep working."""
    root_entry, _ = await _setup_root_with_subentries(hass, 1)

    assert hass.data[DOMAIN].get("coordinator") is not None
    assert hass.services.has_service(DOMAIN, SERVICE_EXPORT_DATA)
    assert hass.services.has_service(DOMAIN, SERVICE_IMPORT_DATA)

    assert await hass.config_entries.async_unload(root_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.data[DOMAIN].get("coordinator") is None
    assert hass.data[DOMAIN].get("registry") is None
    assert not hass.services.has_service(DOMAIN, SERVICE_EXPORT_DATA)
    assert not hass.services.has_service(DOMAIN, SERVICE_IMPORT_DATA)


async def test_full_removal_after_a_single_subentry_removal_still_tears_down(
    hass: HomeAssistant,
) -> None:
    """The actual regression: remove ONE of several sensors first (the
    ghost-producing step before this fix), then unload the whole
    integration. Before the setup-time pruning fix, the removed sensor's
    subentry_id lingered as a coordinator ghost that was never in
    entry.subentries for async_unload_entry's own loop to clean up, so
    coordinator.subentry_data could never reach empty and the domain-wide
    teardown never ran — leaking the coordinator, its services and the
    sidebar panel forever."""
    root_entry, subentry_ids = await _setup_root_with_subentries(hass, 2)
    _, remove_id = subentry_ids

    hass.config_entries.async_remove_subentry(root_entry, remove_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(root_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.data[DOMAIN].get("coordinator") is None
    assert hass.data[DOMAIN].get("registry") is None
    assert not hass.services.has_service(DOMAIN, SERVICE_EXPORT_DATA)
    assert not hass.services.has_service(DOMAIN, SERVICE_IMPORT_DATA)


async def _setup_root_with_options(
    hass: HomeAssistant, options: dict | None = None
) -> MockConfigEntry:
    """Create and load the singleton root entry with the given options."""
    root_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_root",
        data={},
        options=options or {},
    )
    root_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(root_entry.entry_id)
    await hass.async_block_till_done()
    return root_entry


_INFLUX_OPTIONS = {
    CONF_INFLUX_HOST: "http://influx.local:8086",
    CONF_INFLUX_TOKEN: "tok-123",
    CONF_INFLUX_ORG: "energy",
    CONF_INFLUX_BUCKET: "abstractor",
}


async def test_setup_attaches_exporter_when_credentials_configured(
    hass: HomeAssistant,
) -> None:
    """[REQ-DATA-002] With host+token options set, the coordinator carries a
    real InfluxExporter after setup."""
    root_entry = await _setup_root_with_options(hass, _INFLUX_OPTIONS)

    coordinator = hass.data[DOMAIN]["coordinator"]
    assert isinstance(coordinator.influx_exporter, InfluxExporter)
    assert coordinator.influx_exporter._host == "http://influx.local:8086"
    assert coordinator.influx_exporter._bucket == "abstractor"
    assert root_entry.data == {}


async def test_setup_leaves_exporter_none_without_credentials(
    hass: HomeAssistant,
) -> None:
    """[REQ-DATA-002] Without host+token the exporter stays None — no exporter
    object is created for an empty configuration."""
    await _setup_root_with_options(hass, {})

    coordinator = hass.data[DOMAIN]["coordinator"]
    assert coordinator.influx_exporter is None


async def test_setup_applies_poll_interval_from_options(
    hass: HomeAssistant,
) -> None:
    """[REQ-CORE-007] coordinator.update_interval reflects the option, not the
    hardcoded default."""
    await _setup_root_with_options(hass, {CONF_POLL_INTERVAL: 7})

    coordinator = hass.data[DOMAIN]["coordinator"]
    assert coordinator.update_interval == timedelta(seconds=7)


async def test_options_change_reload_rebuilds_exporter_and_interval(
    hass: HomeAssistant,
) -> None:
    """[REQ-CORE-007] An options change (reload) rebuilds the exporter from
    the new options and re-applies the poll interval."""
    root_entry = await _setup_root_with_options(hass, _INFLUX_OPTIONS)
    coordinator = hass.data[DOMAIN]["coordinator"]
    first_exporter = coordinator.influx_exporter
    assert isinstance(first_exporter, InfluxExporter)

    hass.config_entries.async_update_entry(
        root_entry,
        options={
            **dict(_INFLUX_OPTIONS),
            CONF_INFLUX_HOST: "http://influx2.local:8086",
            CONF_POLL_INTERVAL: 15,
        },
    )
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN]["coordinator"]
    assert coordinator.influx_exporter is not first_exporter
    assert isinstance(coordinator.influx_exporter, InfluxExporter)
    assert coordinator.influx_exporter._host == "http://influx2.local:8086"
    assert coordinator.update_interval == timedelta(seconds=15)


async def test_options_change_without_credentials_clears_exporter(
    hass: HomeAssistant,
) -> None:
    """[REQ-DATA-002] Reloading with credentials removed rebuilds to None."""
    root_entry = await _setup_root_with_options(hass, _INFLUX_OPTIONS)
    coordinator = hass.data[DOMAIN]["coordinator"]
    assert isinstance(coordinator.influx_exporter, InfluxExporter)

    hass.config_entries.async_update_entry(root_entry, options={})
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN]["coordinator"]
    assert coordinator.influx_exporter is None


async def test_unload_clears_exporter(hass: HomeAssistant) -> None:
    """[REQ-DATA-002] Unloading the entry clears the exporter from the
    coordinator alongside the existing teardown."""
    root_entry = await _setup_root_with_options(hass, _INFLUX_OPTIONS)
    coordinator = hass.data[DOMAIN]["coordinator"]
    assert isinstance(coordinator.influx_exporter, InfluxExporter)

    assert await hass.config_entries.async_unload(root_entry.entry_id)
    await hass.async_block_till_done()

    assert coordinator.influx_exporter is None
