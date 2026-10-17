"""Light platform for Abstractor (actuator proxy)."""
from __future__ import annotations

from homeassistant.components.light import LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from ._actuator import AbstractorActuatorEntity, primary_source_id
from .const import (
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_NAMING_TEMPLATE,
    DOMAIN,
)
from .naming import (
    effective_logical_name,
    resolve_entity_name,
    resolve_object_id,
)
from .naming_template import async_get_template
from .specs import SPEC_REGISTRY


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN]["coordinator"]
    group_data = [sub.data for sub in entry.subentries.values()]
    template = await async_get_template(hass, entry.options.get(CONF_NAMING_TEMPLATE))
    for subentry_id, subentry in entry.subentries.items():
        device_type = subentry.data.get(CONF_DEVICE_TYPE, "")
        spec = SPEC_REGISTRY.try_get(device_type)
        if spec is None or spec.platform != "light" or not spec.enabled:
            continue
        source_id = primary_source_id(subentry.data)
        if not source_id:
            continue
        async_add_entities(
            [
                AbstractorLight(
                    coordinator,
                    entry,
                    device_type,
                    source_id,
                    subentry.data.get(CONF_LEGACY_UNIQUE_ID),
                    subentry_id=subentry_id,
                    device_group_id=subentry.data.get(CONF_DEVICE_GROUP_ID),
                    logical_name=effective_logical_name(subentry.data, group_data),
                    entity_name=resolve_entity_name(subentry.data, spec, template),
                    object_id=resolve_object_id(subentry.data, spec, template),
                    template=template,
                )
            ],
            config_subentry_id=subentry_id,
        )


class AbstractorLight(AbstractorActuatorEntity, LightEntity):
    """An on/off light that proxies a source light entity (no color/brightness)."""

    @property
    def is_on(self) -> bool | None:
        return self._is_on()

    async def async_turn_on(self, **kwargs) -> None:
        await self._call_source("turn_on")

    async def async_turn_off(self, **kwargs) -> None:
        await self._call_source("turn_off")
