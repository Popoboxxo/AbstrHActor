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


async def test_unique_id_ignores_reconfigured_source_in_options() -> None:
    """A hardware swap via the options flow must not change unique_id (REQ-CORE-001).

    entry.data is frozen at creation time; entry.options is what the options
    flow rewrites when the source entity is swapped. The unique_id must be
    derived from entry.data only, or the entity/recorder history would break
    on every reconfiguration.
    """
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.data = {CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.original"}
    # Simulates a post-options-flow entry: source was swapped to a new device.
    entry.options = {CONF_SOURCE_ENTITY_IDS: ["sensor.swapped_in"]}

    hass = Mock()
    coordinator = Mock()
    hass.data = {DOMAIN: {"coordinator": coordinator}}
    added = []
    async_add_entities = Mock(side_effect=lambda entities: added.extend(entities))

    await async_setup_entry(hass, entry, async_add_entities)

    assert added[0].unique_id == "abstractor_sensor.original_power"


async def test_legacy_unique_id_overrides_computed_id() -> None:
    """A migrated YAML template sensor keeps its old unique_id (REQ-CORE-003)."""
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.data = {
        CONF_DEVICE_TYPE: "power",
        CONF_SOURCE_ENTITY_ID: "sensor.original",
        CONF_LEGACY_UNIQUE_ID: "fridge_power_template",
    }
    entry.options = {}

    hass = Mock()
    coordinator = Mock()
    hass.data = {DOMAIN: {"coordinator": coordinator}}
    added = []
    async_add_entities = Mock(side_effect=lambda entities: added.extend(entities))

    await async_setup_entry(hass, entry, async_add_entities)

    assert added[0].unique_id == "fridge_power_template"


def test_native_value_reads_coordinator_data() -> None:
    """The entity itself never polls; it reflects the coordinator's cache."""
    entry = Mock()
    entry.entry_id = "entry-1"
    coordinator = Mock(data={"entry-1": 42.0})

    sensor = AbstractorSensor(coordinator, entry, "power", ["sensor.original"])

    assert sensor.native_value == 42.0
