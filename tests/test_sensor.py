"""Test Abstractor sensor entity identity (REQ-CORE-001, REQ-CORE-003)."""

from unittest.mock import Mock

from custom_components.abstractor.const import (
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    DOMAIN,
)
from custom_components.abstractor.sensor import AbstractorSensor, async_setup_entry


async def test_unique_id_derived_from_subentry_data() -> None:
    """unique_id is derived from the owning subentry's own data (REQ-CORE-001).

    subentry.data is what the create/reconfigure flow writes atomically each
    time (see config_flow.py). The unique_id must be derived from it alone,
    or reconfiguring a subentry (e.g. moving it onto another device) could
    change the id, breaking the entity/recorder history.
    """
    entry = Mock()
    entry.entry_id = "entry-1"
    subentry = Mock()
    subentry.data = {
        CONF_DEVICE_TYPE: "power",
        CONF_SOURCE_ENTITY_ID: "sensor.original",
    }
    entry.subentries = {"subentry-1": subentry}

    hass = Mock()
    coordinator = Mock()
    hass.data = {DOMAIN: {"coordinator": coordinator}}
    added = []
    async_add_entities = Mock(
        side_effect=lambda entities, config_subentry_id=None: added.extend(entities)
    )

    await async_setup_entry(hass, entry, async_add_entities)

    assert added[0].unique_id == "abstractor_sensor.original_power"


async def test_legacy_unique_id_overrides_computed_id() -> None:
    """A migrated YAML template sensor keeps its old unique_id (REQ-CORE-003)."""
    entry = Mock()
    entry.entry_id = "entry-1"
    subentry = Mock()
    subentry.data = {
        CONF_DEVICE_TYPE: "power",
        CONF_SOURCE_ENTITY_ID: "sensor.original",
        CONF_LEGACY_UNIQUE_ID: "fridge_power_template",
    }
    entry.subentries = {"subentry-1": subentry}

    hass = Mock()
    coordinator = Mock()
    hass.data = {DOMAIN: {"coordinator": coordinator}}
    added = []
    async_add_entities = Mock(
        side_effect=lambda entities, config_subentry_id=None: added.extend(entities)
    )

    await async_setup_entry(hass, entry, async_add_entities)

    assert added[0].unique_id == "fridge_power_template"


async def test_unique_id_multi_source_sorted_format() -> None:
    """Multi-source subentries derive unique_id from sorted source ids."""
    entry = Mock()
    entry.entry_id = "entry-1"
    subentry = Mock()
    subentry.data = {
        CONF_DEVICE_TYPE: "power",
        CONF_SOURCE_ENTITY_IDS: ["sensor.b", "sensor.a"],
    }
    entry.subentries = {"subentry-1": subentry}

    hass = Mock()
    coordinator = Mock()
    hass.data = {DOMAIN: {"coordinator": coordinator}}
    added = []
    async_add_entities = Mock(
        side_effect=lambda entities, config_subentry_id=None: added.extend(entities)
    )

    await async_setup_entry(hass, entry, async_add_entities)

    assert added[0].unique_id == "abstractor_power_sensor.a_sensor.b"


def test_native_value_reads_coordinator_data() -> None:
    """The entity itself never polls; it reflects the coordinator's cache."""
    entry = Mock()
    entry.entry_id = "entry-1"
    coordinator = Mock(data={"subentry-1": 42.0})

    sensor = AbstractorSensor(
        coordinator,
        entry,
        "power",
        ["sensor.original"],
        None,
        subentry_id="subentry-1",
        device_group_id=None,
    )

    assert sensor.native_value == 42.0


def test_device_info_uses_shared_group_id() -> None:
    """Two sensors with the same device_group_id share one DeviceInfo identifier."""
    coordinator = Mock()
    entry = Mock()
    sensor_a = AbstractorSensor(
        coordinator, entry, "power", ["sensor.a"], None,
        subentry_id="subentry-a", device_group_id=None,
    )
    sensor_b = AbstractorSensor(
        coordinator, entry, "energy", ["sensor.b"], None,
        subentry_id="subentry-b", device_group_id="subentry-a",
    )

    assert sensor_a.device_info["identifiers"] == {("abstractor", "subentry-a")}
    assert sensor_b.device_info["identifiers"] == {("abstractor", "subentry-a")}
