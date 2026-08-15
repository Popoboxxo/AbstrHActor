"""Test Abstractor sensor entity identity (REQ-CORE-001, REQ-CORE-003)."""

from unittest.mock import Mock

from custom_components.abstractor.const import (
    CONF_DEVICE_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
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
    coordinator.hass = hass
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
    coordinator.hass = hass
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
    coordinator.hass = hass
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
    hass = Mock()
    hass.data = {DOMAIN: {"coordinator": coordinator}}
    coordinator.hass = hass

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
    hass = Mock()
    coordinator = Mock()
    hass.data = {DOMAIN: {"coordinator": coordinator}}
    coordinator.hass = hass
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


def _sensor_with_options(
    options: dict | None = None,
    *,
    device_group_id: str | None = None,
    with_registry: bool = True,
) -> tuple[AbstractorSensor, Mock]:
    """Build a sensor whose coordinator/hass are wired like async_setup_entry
    does, plus the (possibly mocked) in-memory registry."""
    hass = Mock()
    coordinator = Mock()
    domain_data: dict = {"coordinator": coordinator}
    registry = Mock()
    if with_registry:
        domain_data["registry"] = registry
    hass.data = {DOMAIN: domain_data}
    coordinator.hass = hass

    entry = Mock()
    entry.entry_id = "entry-1"
    entry.options = dict(options or {})

    sensor = AbstractorSensor(
        coordinator,
        entry,
        "power",
        ["sensor.power_plug"],
        None,
        subentry_id="subentry-a",
        device_group_id=device_group_id,
    )
    return sensor, registry


def test_device_info_manufacturer_model_and_name_from_options() -> None:
    """[REQ-CORE-006] DeviceInfo manufacturer/model/name come from options."""
    sensor, _registry = _sensor_with_options(
        {
            CONF_DEVICE_MANUFACTURER: "Acme Labs",
            CONF_DEVICE_MODEL: "OptiSense 3000",
            CONF_DEVICE_NAME: "Fridge {device_type}",
        }
    )

    assert sensor.device_info["manufacturer"] == "Acme Labs"
    assert sensor.device_info["model"] == "OptiSense 3000"
    assert sensor.device_info["name"] == "Fridge Power"


def test_device_info_falls_back_to_defaults_when_options_absent() -> None:
    """[REQ-CORE-006] Missing options fall back to the Abstractor defaults."""
    sensor, _registry = _sensor_with_options()

    assert sensor.device_info["manufacturer"] == "Abstractor"
    assert sensor.device_info["model"] == "Abstract sensor"
    assert sensor.device_info["name"] == "Abstract Power"
    assert sensor.device_info["identifiers"] == {("abstractor", "subentry-a")}


def test_register_device_called_with_option_values() -> None:
    """[REQ-CORE-006] The in-memory registry is populated with the option-
    driven name, manufacturer and model under the device_key."""
    sensor, registry = _sensor_with_options(
        {
            CONF_DEVICE_MANUFACTURER: "Acme Labs",
            CONF_DEVICE_MODEL: "OptiSense 3000",
            CONF_DEVICE_NAME: "Fridge {device_type}",
        }
    )

    assert sensor.device_info["identifiers"] == {("abstractor", "subentry-a")}
    registry.register_device.assert_called_once_with(
        "subentry-a", "Fridge Power", "Acme Labs", "OptiSense 3000"
    )


def test_register_device_uses_group_id_when_bundled() -> None:
    """[REQ-CORE-006] A bundled sensor registers under its device_group_id."""
    _sensor, registry = _sensor_with_options(device_group_id="fridge-group")

    registry.register_device.assert_called_once_with(
        "fridge-group", "Abstract Power", "Abstractor", "Abstract sensor"
    )


def test_register_device_skipped_when_registry_absent() -> None:
    """[REQ-CORE-006] No registry in hass.data -> no register_device call,
    and construction must not raise (fixtures without the key)."""
    sensor, registry = _sensor_with_options(with_registry=False)

    assert sensor.device_info["manufacturer"] == "Abstractor"
    registry.register_device.assert_not_called()
