"""Sensor platform for Abstractor."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_TYPE,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    DOMAIN,
)
from .coordinator import AbstractorDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: AbstractorDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]

    device_type = entry.data.get(CONF_DEVICE_TYPE, "")
    config = {**entry.data, **entry.options}
    source_entity_ids = config.get(CONF_SOURCE_ENTITY_IDS) or [
        config.get(CONF_SOURCE_ENTITY_ID)
    ]
    source_entity_ids = [source for source in source_entity_ids if source]

    async_add_entities(
        [AbstractorSensor(coordinator, entry, device_type, source_entity_ids)]
    )

class AbstractorSensor(CoordinatorEntity[AbstractorDataUpdateCoordinator], SensorEntity):
    """Abstractor Sensor Entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AbstractorDataUpdateCoordinator,
        entry: ConfigEntry,
        device_type: str,
        source_entity_ids: list[str],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._device_type = device_type
        self._source_entity_ids = source_entity_ids
        
        if len(source_entity_ids) == 1:
            # Keep the first MVP's ID stable for existing single-source entries.
            self._attr_unique_id = f"abstractor_{source_entity_ids[0]}_{device_type}"
        else:
            self._attr_unique_id = (
                f"abstractor_{device_type}_{'_'.join(sorted(source_entity_ids))}"
            )
        self._attr_name = device_type.capitalize()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Abstract {device_type.capitalize()}",
            manufacturer="Abstractor",
            model="Abstract sensor",
        )

        if device_type == "power":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = "W"
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif device_type == "energy":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "kWh"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif device_type == "water":
            self._attr_device_class = SensorDeviceClass.WATER
            self._attr_native_unit_of_measurement = "L"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self.entry.entry_id)
