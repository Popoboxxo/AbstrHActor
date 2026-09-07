"""Test Abstractor service handlers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abstractor import export_data_service, import_data_service
from custom_components.abstractor.const import (
    CONF_DEVICE_TYPE,
    CONF_SOURCE_ENTITY_ID,
    DOMAIN,
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
    entry = SimpleNamespace(subentries={"subentry-1": subentry}, version=1)
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
