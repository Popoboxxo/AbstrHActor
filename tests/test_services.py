"""Test Abstractor service handlers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abstractor import (
    delete_sensor_service,
    export_data_service,
    import_data_service,
)
from custom_components.abstractor.const import (
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_SOURCE_ENTITY_ID,
    DOMAIN,
    ROOT_UNIQUE_ID,
    SERVICE_DELETE_SENSOR,
    SERVICE_EXPORT_DATA,
    SUBENTRY_TYPE_SENSOR,
)


def _hass(store: Mock) -> SimpleNamespace:
    """Build the minimal hass surface used by service handlers.

    Sensor configuration is read from the config entries' subentries since
    device bundling; only the last-known values still come from the
    coordinator.
    """
    subentry = SimpleNamespace(
        data={"device_type": "power", "source_entity_id": "sensor.test_source"},
        title="Abstract power",
        unique_id=None,
    )
    entry = SimpleNamespace(
        subentries={"subentry-1": subentry}, version=1, unique_id=ROOT_UNIQUE_ID
    )
    coordinator = SimpleNamespace(data={"subentry-1": 4.0})
    return SimpleNamespace(
        data={DOMAIN: {"storage": store, "coordinator": coordinator}},
        config_entries=SimpleNamespace(async_entries=lambda domain: [entry]),
    )


async def test_export_service_uses_captured_hass() -> None:
    """Export must not depend on a non-contract ServiceCall hass attribute."""
    store = Mock(async_save=AsyncMock())
    hass = _hass(store)
    call = SimpleNamespace(data={})

    await export_data_service(hass, call)

    store.async_save.assert_awaited_once()


async def test_import_service_persists_valid_snapshot() -> None:
    """Import writes the validated service payload to HA storage."""
    store = Mock(async_save=AsyncMock())
    hass = _hass(store)
    payload = {
        "format": "abstractor.snapshot",
        "version": 1,
        "entries": [],
        "values": {},
    }
    call = SimpleNamespace(data={"data": payload})

    await import_data_service(hass, call)

    store.async_save.assert_awaited_once_with(payload)
    assert hass.data[DOMAIN]["stored_snapshot"] == payload


async def test_export_service_call_returns_snapshot_response(hass: HomeAssistant) -> None:
    """The `export_data` service must hand the snapshot back to the caller
    via `return_response=True`, not just persist it to Store — a panel
    "Export" button has nothing to download otherwise (plan
    docs/plan-panel-action-hub.md, work item 1)."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)
    subentry = ConfigSubentry(
        data={
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.grid_power",
        },
        subentry_type=SUBENTRY_TYPE_SENSOR,
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, subentry)
    hass.states.async_set("sensor.grid_power", "42")

    assert await hass.config_entries.async_setup(root_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN]["coordinator"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    result = await hass.services.async_call(
        DOMAIN, SERVICE_EXPORT_DATA, {}, blocking=True, return_response=True
    )

    assert result is not None, (
        "export_data must be registered with supports_response=SupportsResponse.ONLY "
        "for return_response=True to yield a result instead of None"
    )
    assert "snapshot" in result
    snapshot = result["snapshot"]
    assert snapshot["format"] == "abstractor.snapshot"
    assert snapshot["version"] == 1
    assert len(snapshot["entries"]) == 1
    exported_entry = snapshot["entries"][0]
    assert exported_entry["data"] == {
        CONF_DEVICE_TYPE: "power",
        CONF_SOURCE_ENTITY_ID: "sensor.grid_power",
    }
    assert exported_entry["title"] == "Abstract power"
    assert snapshot["values"] == coordinator.data


def _snapshot_entry(entry_id: str, data: dict, title: str = "Abstract power") -> dict:
    """Build one snapshot entry in the shape produced by export_data."""
    return {
        "entry_id": entry_id,
        "data": data,
        "options": {},
        "title": title,
        "unique_id": None,
        "version": 1,
    }


async def _setup_root(hass: HomeAssistant):
    """Register + set up a singleton root entry and return it."""
    root_entry = MockConfigEntry(
        domain=DOMAIN, unique_id=ROOT_UNIQUE_ID, data={}, options={}
    )
    root_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(root_entry.entry_id)
    await hass.async_block_till_done()
    return root_entry


async def test_import_recreates_missing_subentries(hass: HomeAssistant) -> None:
    """[B6] Import restores sensor subentries that are missing from the
    installation, pinned to their snapshot identity, and HA's standard
    subentry-add reload brings their entities up."""
    root_entry = await _setup_root(hass)
    payload = {
        "format": "abstractor.snapshot",
        "version": 1,
        "entries": [
            _snapshot_entry(
                "subentry-restored",
                {
                    CONF_DEVICE_TYPE: "power",
                    CONF_SOURCE_ENTITY_ID: "sensor.grid_power",
                    CONF_LEGACY_UNIQUE_ID: "abstractor_legacy_1",
                },
            )
        ],
        "values": {},
    }

    await hass.services.async_call(
        DOMAIN, "import_data", {"data": payload}, blocking=True
    )
    await hass.async_block_till_done()

    restored = root_entry.subentries.get("subentry-restored")
    assert restored is not None
    assert restored.data[CONF_LEGACY_UNIQUE_ID] == "abstractor_legacy_1"
    assert restored.data[CONF_SOURCE_ENTITY_ID] == "sensor.grid_power"
    # The stored snapshot reflects the installation again after the reload
    # (the restored subentry contributes its polled value to `values`), so
    # only the entries are compared against the imported payload.
    assert hass.data[DOMAIN]["stored_snapshot"]["entries"] == payload["entries"]
    state = hass.states.get("sensor.abstract_power_power")
    assert state is not None, "restored sensor entity must come up via the reload"


async def test_import_skips_existing_and_missing_source_entries(
    hass: HomeAssistant,
) -> None:
    """[B6] Import never clobbers or duplicates existing subentries, and
    entries without any source entity are skipped with a warning."""
    root_entry = await _setup_root(hass)
    existing = ConfigSubentry(
        data={
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.grid_power",
            CONF_LEGACY_UNIQUE_ID: "abstractor_legacy_1",
        },
        subentry_type=SUBENTRY_TYPE_SENSOR,
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, existing)
    await hass.async_block_till_done()

    payload = {
        "format": "abstractor.snapshot",
        "version": 1,
        "entries": [
            # Same identity as the existing subentry, but with different
            # data — must be ignored, not applied and not duplicated.
            _snapshot_entry(
                "subentry-clashing",
                {
                    CONF_DEVICE_TYPE: "energy",
                    CONF_SOURCE_ENTITY_ID: "sensor.other_source",
                    CONF_LEGACY_UNIQUE_ID: "abstractor_legacy_1",
                },
            ),
            # No source entity at all — skipped, never fails the import.
            _snapshot_entry(
                "subentry-sourceless",
                {CONF_DEVICE_TYPE: "power", CONF_LEGACY_UNIQUE_ID: "abstractor_x"},
            ),
        ],
        "values": {},
    }

    await hass.services.async_call(
        DOMAIN, "import_data", {"data": payload}, blocking=True
    )
    await hass.async_block_till_done()

    assert len(root_entry.subentries) == 1
    assert root_entry.subentries[existing.subentry_id].data == existing.data


async def test_import_without_root_entry_fails(hass: HomeAssistant) -> None:
    """[B6] With no root config entry there is nothing to attach restored
    subentries to — the service must fail loudly, not silently store."""
    root_entry = await _setup_root(hass)
    await hass.config_entries.async_unload(root_entry.entry_id)
    hass.config_entries.async_remove(root_entry.entry_id)
    await hass.async_block_till_done()
    # Service was deregistered with the entry; call the handler directly to
    # exercise the no-root guard (patch the lookup — removal timing of the
    # config-entry registry is not what this test is about).
    store = SimpleNamespace(async_save=AsyncMock())
    hass.data.setdefault(DOMAIN, {})["storage"] = store
    payload = {
        "format": "abstractor.snapshot",
        "version": 1,
        "entries": [
            _snapshot_entry(
                "subentry-x",
                {
                    CONF_DEVICE_TYPE: "power",
                    CONF_SOURCE_ENTITY_ID: "sensor.grid_power",
                },
            )
        ],
        "values": {},
    }
    call = SimpleNamespace(data={"data": payload})

    with (
        patch(
            "custom_components.abstractor._async_root_entry", return_value=None
        ),
        pytest.raises(HomeAssistantError, match="root config entry"),
    ):
        await import_data_service(hass, call)
    store.async_save.assert_not_awaited()


async def test_delete_sensor_by_subentry_id(hass: HomeAssistant) -> None:
    """[B5] Deleting by subentry_id removes the subentry, its entity and
    its device via HA's standard subentry teardown."""
    root_entry = await _setup_root(hass)
    subentry = ConfigSubentry(
        data={
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.grid_power",
            CONF_LEGACY_UNIQUE_ID: "abstractor_legacy_1",
        },
        subentry_type=SUBENTRY_TYPE_SENSOR,
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, subentry)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.abstract_power_power") is not None

    await hass.services.async_call(
        DOMAIN, SERVICE_DELETE_SENSOR, {"subentry_id": subentry.subentry_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert subentry.subentry_id not in root_entry.subentries
    assert hass.states.get("sensor.abstract_power_power") is None


async def test_delete_sensor_by_legacy_unique_id(hass: HomeAssistant) -> None:
    """[B5] legacy_unique_id is the alternative key, matching what a user
    sees in the entity registry."""
    root_entry = await _setup_root(hass)
    subentry = ConfigSubentry(
        data={
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.grid_power",
            CONF_LEGACY_UNIQUE_ID: "abstractor_legacy_1",
        },
        subentry_type=SUBENTRY_TYPE_SENSOR,
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, subentry)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN, SERVICE_DELETE_SENSOR, {"legacy_unique_id": "abstractor_legacy_1"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert subentry.subentry_id not in root_entry.subentries


async def test_delete_sensor_unknown_ids_fail(hass: HomeAssistant) -> None:
    """[B5] Unknown subentry_id and unknown legacy_unique_id both raise
    ServiceValidationError; a call with no key at all is rejected too."""
    root_entry = await _setup_root(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, SERVICE_DELETE_SENSOR, {"subentry_id": "nope"}, blocking=True
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, SERVICE_DELETE_SENSOR,
            {"legacy_unique_id": "abstractor_nope"},
            blocking=True,
        )
    with pytest.raises(ServiceValidationError):
        await delete_sensor_service(hass, SimpleNamespace(data={}))
    assert root_entry.subentries == {}
