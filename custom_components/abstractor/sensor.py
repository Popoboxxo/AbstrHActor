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

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform: one entity per Abstractor subentry."""
    coordinator: AbstractorDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]

    for subentry_id, subentry in entry.subentries.items():
        device_type = subentry.data.get(CONF_DEVICE_TYPE, "")
        # Identity (unique_id) is derived from subentry.data ONLY. subentry.data
        # is what the create/reconfigure flow writes atomically each time (see
        # config_flow.py); deriving unique_id from anything else would risk
        # changing it on reconfigure, breaking REQ-CORE-001 (stable identity /
        # unbroken recorder history across a hardware swap or device move).
        identity_source_ids = subentry.data.get(CONF_SOURCE_ENTITY_IDS) or [
            subentry.data.get(CONF_SOURCE_ENTITY_ID)
        ]
        identity_source_ids = [source for source in identity_source_ids if source]

        async_add_entities(
            [
                AbstractorSensor(
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

class AbstractorSensor(CoordinatorEntity[AbstractorDataUpdateCoordinator], SensorEntity):
    """Abstractor Sensor Entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AbstractorDataUpdateCoordinator,
        entry: ConfigEntry,
        device_type: str,
        identity_source_ids: list[str],
        legacy_unique_id: str | None = None,
        *,
        subentry_id: str,
        device_group_id: str | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._subentry_id = subentry_id
        self._device_type = device_type
        self._identity_source_ids = identity_source_ids

        if legacy_unique_id:
            # REQ-CORE-003: migrated YAML template sensor, keep its old id.
            self._attr_unique_id = legacy_unique_id
        elif len(identity_source_ids) == 1:
            # Keep the first MVP's ID stable for existing single-source entries.
            self._attr_unique_id = f"abstractor_{identity_source_ids[0]}_{device_type}"
        else:
            self._attr_unique_id = (
                f"abstractor_{device_type}_{'_'.join(sorted(identity_source_ids))}"
            )
        self._attr_name = device_type.capitalize()
        # device_group_id set -> this sensor joins an existing device (the
        # subentry that originally registered it under this identifier).
        # Not set -> this sensor gets its own device, keyed by its own
        # subentry_id — identical to today's one-device-per-sensor default.
        device_key = device_group_id or subentry_id
        device_name = str(
            entry.options.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME)
        ).replace("{device_type}", device_type.capitalize())
        manufacturer = str(
            entry.options.get(CONF_DEVICE_MANUFACTURER, DEFAULT_DEVICE_MANUFACTURER)
        )
        model = str(entry.options.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            name=device_name,
            manufacturer=manufacturer,
            model=model,
        )
        registry = coordinator.hass.data[DOMAIN].get("registry")
        if registry is not None:
            registry.register_device(device_key, device_name, manufacturer, model)

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
        return self.coordinator.data.get(self._subentry_id)
