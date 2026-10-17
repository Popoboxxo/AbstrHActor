"""End-to-end naming/identity wiring through a loaded root entry.

Covers REQ-NAME-002..006: a local naming template (and explicit subentry
overrides) drive the device name, the entity name and the suggested entity_id
without ever touching ``unique_id``.
"""
from __future__ import annotations

import pathlib

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abstractor.const import (
    CONF_DEVICE_TYPE,
    CONF_ENTITY_NAME,
    CONF_LOGICAL_NAME,
    CONF_NAMING_TEMPLATE,
    CONF_OBJECT_ID,
    CONF_SOURCE_ENTITY_ID,
    DOMAIN,
    SUBENTRY_TYPE_SENSOR,
)

_TEMPLATE = """
schema_version: 1
id: household
device_name: "Home {spec_display_name}"
entity_name:
  power: "Fridge Draw"
object_id: "fridge_{device_type}"
"""


def _write_template(hass: HomeAssistant, tmp_path: pathlib.Path) -> None:
    # Redirect the config dir to a per-test temp path so the template file
    # never lands in the shared testing_config directory.
    template_dir = tmp_path / "abstractor" / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "household.yaml").write_text(_TEMPLATE)
    hass.config.config_dir = str(tmp_path)


async def _setup(hass: HomeAssistant, subentry_data: dict) -> MockConfigEntry:
    root_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_root",
        data={},
        options={CONF_NAMING_TEMPLATE: "household"},
    )
    root_entry.add_to_hass(hass)
    subentry = ConfigSubentry(
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.plug", **subentry_data},
        subentry_type=SUBENTRY_TYPE_SENSOR,
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, subentry)
    hass.states.async_set("sensor.plug", "7")
    assert await hass.config_entries.async_setup(root_entry.entry_id)
    await hass.async_block_till_done()
    return root_entry


async def test_template_drives_name_and_object_id(
    hass: HomeAssistant, tmp_path: pathlib.Path
) -> None:
    _write_template(hass, tmp_path)
    await _setup(hass, {})

    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("sensor.fridge_power")
    assert entry is not None
    assert entry.unique_id == "abstractor_sensor.plug_power"

    state = hass.states.get("sensor.fridge_power")
    # has_entity_name=True: HA renders "<device name> <entity name>".
    assert state.attributes["friendly_name"] == "Home Power Fridge Draw"

    device = dr.async_get(hass).async_get(entry.device_id)
    assert device is not None
    assert device.name == "Home Power"


async def test_explicit_overrides_beat_template(
    hass: HomeAssistant, tmp_path: pathlib.Path
) -> None:
    _write_template(hass, tmp_path)
    await _setup(
        hass,
        {
            CONF_LOGICAL_NAME: "Deep Freeze",
            CONF_ENTITY_NAME: "Compressor",
            CONF_OBJECT_ID: "deep_freeze_power",
        },
    )

    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("sensor.deep_freeze_power")
    assert entry is not None

    state = hass.states.get("sensor.deep_freeze_power")
    assert state.attributes["friendly_name"] == "Deep Freeze Compressor"

    device = dr.async_get(hass).async_get(entry.device_id)
    assert device is not None
    assert device.name == "Deep Freeze"
