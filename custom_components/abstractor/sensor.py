"""Sensor platform for Abstractor."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_TYPE, CONF_SOURCE_ENTITY_ID, DOMAIN
from .coordinator import AbstractorDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: AbstractorDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]

    device_type = entry.data.get(CONF_DEVICE_TYPE)
    source_entity_id = entry.data.get(CONF_SOURCE_ENTITY_ID)

    async_add_entities([AbstractorSensor(coordinator, entry, device_type, source_entity_id)])

class AbstractorSensor(CoordinatorEntity[AbstractorDataUpdateCoordinator], SensorEntity):
    """Abstractor Sensor Entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AbstractorDataUpdateCoordinator,
        entry: ConfigEntry,
        device_type: str,
        source_entity_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._device_type = device_type
        self._source_entity_id = source_entity_id
        
        self._attr_unique_id = f"abstractor_{source_entity_id}_{device_type}"
        self._attr_name = f"Abstract {device_type.capitalize()}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._source_entity_id)
