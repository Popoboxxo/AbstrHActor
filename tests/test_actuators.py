"""Tests for the Abstractor actuator platforms (switch / light)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.abstractor import light, switch


def _entry(options=None, subentries=None):
    return SimpleNamespace(options=options or {}, subentries=subentries or {})


def _coordinator(data=None):
    coordinator = Mock()
    coordinator.data = data if data is not None else {}
    return coordinator


def _with_hass(entity):
    entity.hass = SimpleNamespace(services=SimpleNamespace(async_call=AsyncMock()))
    return entity


async def test_switch_setup_entry_adds_only_switch_specs() -> None:
    coordinator = _coordinator()
    hass = SimpleNamespace(data={"abstractor": {"coordinator": coordinator}})
    entry = _entry(
        subentries={
            "s1": SimpleNamespace(
                data={"device_type": "switch_state", "source_entity_id": "switch.foo"}
            ),
            "l1": SimpleNamespace(
                data={"device_type": "light_state", "source_entity_id": "light.bar"}
            ),
            "p1": SimpleNamespace(
                data={"device_type": "power", "source_entity_id": "sensor.p"}
            ),
        }
    )
    added = []

    def _add(entities, config_subentry_id=None):
        added.extend(entities)

    await switch.async_setup_entry(hass, entry, _add)

    assert len(added) == 1
    assert added[0]._attr_unique_id == "abstractor_switch.foo_switch_state"
    assert added[0]._attr_name == "Switch"


async def test_switch_is_on_parses_state() -> None:
    coordinator = _coordinator({"s1": "on"})
    entity = switch.AbstractorSwitch(
        coordinator, _entry(), "switch_state", "switch.foo", None, subentry_id="s1"
    )
    assert entity.is_on is True

    coordinator.data = {"s1": "off"}
    assert entity.is_on is False

    coordinator.data = {}
    assert entity.is_on is None


async def test_switch_turn_on_forwards_to_source_service() -> None:
    coordinator = _coordinator({"s1": "off"})
    entity = _with_hass(
        switch.AbstractorSwitch(
            coordinator, _entry(), "switch_state", "switch.foo", None, subentry_id="s1"
        )
    )

    await entity.async_turn_on()

    entity.hass.services.async_call.assert_awaited_once_with(
        "switch", "turn_on", {"entity_id": "switch.foo"}, blocking=True
    )


async def test_switch_turn_off_forwards_to_source_service() -> None:
    coordinator = _coordinator({"s1": "on"})
    entity = _with_hass(
        switch.AbstractorSwitch(
            coordinator, _entry(), "switch_state", "switch.foo", None, subentry_id="s1"
        )
    )

    await entity.async_turn_off()

    entity.hass.services.async_call.assert_awaited_once_with(
        "switch", "turn_off", {"entity_id": "switch.foo"}, blocking=True
    )


async def test_light_turn_on_forwards_to_light_domain() -> None:
    coordinator = _coordinator({"l1": "off"})
    entity = _with_hass(
        light.AbstractorLight(
            coordinator, _entry(), "light_state", "light.bar", None, subentry_id="l1"
        )
    )

    await entity.async_turn_on()

    entity.hass.services.async_call.assert_awaited_once_with(
        "light", "turn_on", {"entity_id": "light.bar"}, blocking=True
    )


def test_actuator_unique_id_prefers_legacy() -> None:
    entity = light.AbstractorLight(
        _coordinator(), _entry(), "light_state", "light.bar", "legacy-id", subentry_id="l1"
    )
    assert entity._attr_unique_id == "legacy-id"
