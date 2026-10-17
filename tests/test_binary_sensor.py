"""Tests for the Abstractor binary_sensor platform (M7)."""

from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.abstractor import binary_sensor
from custom_components.abstractor.const import DOMAIN


def _entry(options=None, subentries=None):
    return SimpleNamespace(options=options or {}, subentries=subentries or {})


def _coordinator(data=None):
    coordinator = Mock()
    coordinator.data = data if data is not None else {}
    return coordinator


def _subentry(data, title="Abstract door_contact"):
    return SimpleNamespace(data=data, title=title)


def _entity(coordinator=None, entry=None, device_type="door_contact", sources=None,
           legacy=None, subentry_id="b1", device_group_id=None):
    return binary_sensor.AbstractorBinarySensor(
        coordinator or _coordinator(),
        entry or _entry(),
        device_type,
        sources or ["binary_sensor.door"],
        legacy,
        subentry_id=subentry_id,
        device_group_id=device_group_id,
    )


async def test_setup_entry_adds_only_enabled_binary_specs() -> None:
    coordinator = _coordinator()
    hass = SimpleNamespace(data={DOMAIN: {"coordinator": coordinator}})
    entry = _entry(
        subentries={
            "b1": _subentry(
                {"device_type": "door_contact", "source_entity_id": "binary_sensor.door"}
            ),
            "s1": _subentry(
                {"device_type": "power", "source_entity_id": "sensor.power"}
            ),
            "x1": _subentry(
                {"device_type": "riemann_energy", "source_entity_id": "sensor.energy"}
            ),
        }
    )
    added = []

    def _add(entities, config_subentry_id=None):
        added.extend(entities)

    await binary_sensor.async_setup_entry(hass, entry, _add)

    assert len(added) == 1
    assert added[0]._attr_unique_id.endswith("door_contact")
    assert added[0]._attr_translation_key == "door_contact"


def test_unique_id_prefers_legacy() -> None:
    assert _entity(legacy="legacy-uid")._attr_unique_id == "legacy-uid"


def test_unique_id_single_and_multi_source() -> None:
    single = _entity(device_type="motion", sources=["binary_sensor.m"])
    assert single._attr_unique_id == "abstractor_binary_sensor.m_motion"

    multi = _entity(
        device_type="smoke",
        sources=["binary_sensor.b", "binary_sensor.a"],
        subentry_id="b2",
    )
    assert multi._attr_unique_id == "abstractor_smoke_binary_sensor.a_binary_sensor.b"


def test_is_on_parses_common_states() -> None:
    coordinator = _coordinator({"b1": "on"})
    entity = _entity(coordinator=coordinator)
    assert entity.is_on is True

    coordinator.data = {"b1": "off"}
    assert entity.is_on is False

    coordinator.data = {}
    assert entity.is_on is None


def test_device_class_comes_from_spec() -> None:
    assert _entity(device_type="door_contact")._attr_device_class == "door"
    assert _entity(device_type="motion")._attr_device_class == "motion"
    assert _entity(device_type="smoke")._attr_device_class == "smoke"


def test_device_info_uses_group_id_when_present() -> None:
    info = _entity(device_group_id="grp").device_info
    assert ("abstractor", "grp") in info["identifiers"]


def test_device_info_falls_back_to_subentry_id() -> None:
    info = _entity().device_info
    assert ("abstractor", "b1") in info["identifiers"]
