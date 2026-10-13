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
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    DEFAULT_DEVICE_MANUFACTURER,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_NAME,
    DOMAIN,
)
from .coordinator import AbstractorDataUpdateCoordinator
from .specs import SPEC_REGISTRY

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: AbstractorDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]
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
        self._attr_name = self._spec.display_name

    @property
    def is_on(self) -> bool | None:
        value = None
        if self.coordinator.data:
            value = self.coordinator.data.get(self._subentry_id)
        if value is None:
            return None
        return str(value).lower() in {"on", "true", "1", "yes", "home", "open"}

    def device_info(self) -> DeviceInfo:
        subentry = self.entry.subentries.get(self._subentry_id)
        device_key = (subentry.data.get(CONF_DEVICE_GROUP_ID) if subentry else None) or self._subentry_id
        device_name = str(self.entry.options.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME)).replace("{device_type}", self._device_type.capitalize())
        manufacturer = str(self.entry.options.get(CONF_DEVICE_MANUFACTURER, DEFAULT_DEVICE_MANUFACTURER))
        model = str(self.entry.options.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL))
        return DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            name=device_name,
            manufacturer=manufacturer,
            model=model,
        )
