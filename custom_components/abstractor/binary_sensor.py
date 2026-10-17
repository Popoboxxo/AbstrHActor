"""Binary sensor platform for Abstractor."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_NAMING_TEMPLATE,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    DEFAULT_DEVICE_MANUFACTURER,
    DEFAULT_DEVICE_MODEL,
    DOMAIN,
)
from .coordinator import AbstractorDataUpdateCoordinator
from .naming import (
    effective_logical_name,
    resolve_device_name,
    resolve_entity_name,
    resolve_object_id,
)
from .naming_template import async_get_template
from .specs import SPEC_REGISTRY

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: AbstractorDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]
    group_data = [sub.data for sub in entry.subentries.values()]
    template = await async_get_template(hass, entry.options.get(CONF_NAMING_TEMPLATE))
    for subentry_id, subentry in entry.subentries.items():
        device_type = subentry.data.get(CONF_DEVICE_TYPE, "")
        spec = SPEC_REGISTRY.try_get(device_type)
        if spec is None or spec.platform != "binary_sensor" or not spec.enabled:
            continue
        identity_source_ids = subentry.data.get(CONF_SOURCE_ENTITY_IDS) or [
            subentry.data.get(CONF_SOURCE_ENTITY_ID)
        ]
        identity_source_ids = [s for s in identity_source_ids if s]
        async_add_entities(
            [
                AbstractorBinarySensor(
                    coordinator,
                    entry,
                    device_type,
                    identity_source_ids,
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


class AbstractorBinarySensor(CoordinatorEntity[AbstractorDataUpdateCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry,
        device_type,
        identity_source_ids,
        legacy_unique_id=None,
        *,
        subentry_id,
        device_group_id=None,
        logical_name=None,
        entity_name=None,
        object_id=None,
        template=None,
    ):
        super().__init__(coordinator)
        self.entry = entry
        self._subentry_id = subentry_id
        self._device_type = device_type
        self._spec = SPEC_REGISTRY.get(device_type)
        if legacy_unique_id:
            self._attr_unique_id = legacy_unique_id
        elif len(identity_source_ids) == 1:
            self._attr_unique_id = f"abstractor_{identity_source_ids[0]}_{device_type}"
        else:
            self._attr_unique_id = f"abstractor_{device_type}_{'_'.join(sorted(identity_source_ids))}"
        if entity_name:
            self._attr_name = entity_name
        else:
            # Localized default (REQ-NAME-003).
            self._attr_translation_key = self._spec.type_key
        self._attr_device_class = self._spec.device_class
        # Entity.device_info is a cached_property returning _attr_device_info;
        # a subclass override has to be a property too (or, as here, the
        # attribute just set in __init__). Overriding it as a plain method left
        # Home Assistant reading a bound method instead of a DeviceInfo, so the
        # entity never attached to its device. Assigning _attr_device_info is
        # the same pattern sensor.py uses.
        device_key = device_group_id or subentry_id
        device_name = resolve_device_name(
            self.entry.options, device_type, logical_name, template
        )
        manufacturer = str(
            self.entry.options.get(
                CONF_DEVICE_MANUFACTURER, DEFAULT_DEVICE_MANUFACTURER
            )
        )
        model = str(self.entry.options.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            name=device_name,
            manufacturer=manufacturer,
            model=model,
        )
        if object_id:
            self.entity_id = f"{self._spec.platform}.{object_id}"

    @property
    def is_on(self) -> bool | None:
        value = None
        if self.coordinator.data:
            value = self.coordinator.data.get(self._subentry_id)
        if value is None:
            return None
        return str(value).lower() in {"on", "true", "1", "yes", "home", "open"}
