"""Test Abstractor service handlers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.abstractor import export_data_service, import_data_service
from custom_components.abstractor.const import DOMAIN


def _hass(store: Mock) -> SimpleNamespace:
    """Build the minimal hass surface used by service handlers."""
    entry = SimpleNamespace(
        data={"device_type": "power", "source_entity_id": "sensor.test_source"},
        options={},
        title="Abstract power",
        unique_id="abstractor_power_sensor.test_source",
        version=1,
    )
    coordinator = SimpleNamespace(entries={"entry-1": entry}, data={"entry-1": 4.0})
    return SimpleNamespace(
        data={DOMAIN: {"storage": store, "coordinator": coordinator}},
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
