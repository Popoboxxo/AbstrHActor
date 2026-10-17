"""Sensor platform for Abstractor."""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

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
    """Set up the sensor platform: one entity per Abstractor subentry."""
    coordinator: AbstractorDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]
    group_data = [sub.data for sub in entry.subentries.values()]
    template = await async_get_template(hass, entry.options.get(CONF_NAMING_TEMPLATE))

    for subentry_id, subentry in entry.subentries.items():
        device_type = subentry.data.get(CONF_DEVICE_TYPE)
        if not device_type:
            _LOGGER.warning(
                "Subentry %s has no device_type configured; defaulting to "
                "'power'",
                subentry_id,
            )
            device_type = "power"
        spec = SPEC_REGISTRY.try_get(device_type)
        if spec is not None and spec.platform != "sensor":
            # Not owned by this platform (e.g. binary_sensor). Skip.
            continue
        if spec is not None and spec.integration == "riemann_left":
            # Integrator sensor: consumes the (numeric) source power and
            # accumulates energy over time instead of exposing the raw value.
            async_add_entities(
                [
                    RiemannEnergySensor(
                        coordinator,
                        entry,
                        device_type,
                        subentry.data.get(CONF_LEGACY_UNIQUE_ID),
                        subentry_id=subentry_id,
                        device_group_id=subentry.data.get(CONF_DEVICE_GROUP_ID),
                        logical_name=effective_logical_name(
                            subentry.data, group_data
                        ),
                        entity_name=resolve_entity_name(
                            subentry.data, spec, template
                        ),
                        object_id=resolve_object_id(subentry.data, spec, template),
                        template=template,
                    )
                ],
                config_subentry_id=subentry_id,
            )
            continue
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
                    logical_name=effective_logical_name(subentry.data, group_data),
                    entity_name=resolve_entity_name(subentry.data, spec, template),
                    object_id=resolve_object_id(subentry.data, spec, template),
                    template=template,
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
        logical_name: str | None = None,
        entity_name: str | None = None,
        object_id: str | None = None,
        template=None,
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
        self._spec = SPEC_REGISTRY.try_get(device_type) or SPEC_REGISTRY.get("power")
        if entity_name:
            self._attr_name = entity_name
        else:
            # Localized default (REQ-NAME-003): the platform translations carry
            # the English string in en.json, other locales override it.
            self._attr_translation_key = self._spec.type_key
        # device_group_id set -> this sensor joins an existing device (the
        # subentry that originally registered it under this identifier).
        # Not set -> this sensor gets its own device, keyed by its own
        # subentry_id — identical to today's one-device-per-sensor default.
        device_key = device_group_id or subentry_id
        device_name = resolve_device_name(
            entry.options, device_type, logical_name, template
        )
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

        if object_id:
            # Suggest the entity_id once, at creation; the registry row wins
            # afterwards, so this can never rename a live entity (REQ-NAME-004).
            self.entity_id = f"sensor.{object_id}"

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


def _integrate_energy(
    energy_kwh: float, power_w: float | None, elapsed_seconds: float
) -> float:
    """Integrate a power reading (W) over an elapsed interval into energy (kWh).

    Pure helper so the left-Riemann integration is unit-testable without HA.
    A missing power sample or a non-positive interval contributes nothing.
    """
    if power_w is None or elapsed_seconds <= 0:
        return energy_kwh
    return energy_kwh + (float(power_w) / 1000.0) * (elapsed_seconds / 3600.0)


class RiemannEnergySensor(CoordinatorEntity[AbstractorDataUpdateCoordinator], RestoreSensor):
    """Accumulate energy by integrating a source power reading over time.

    The coordinator pipeline supplies the current power value (W) for this
    subentry; this entity integrates it between coordinator updates and exposes
    the running total in kWh. The accumulator is restored across restarts so the
    long-term energy total is not reset on every reload.
    """

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: AbstractorDataUpdateCoordinator,
        entry: ConfigEntry,
        device_type: str,
        legacy_unique_id: str | None = None,
        *,
        subentry_id: str,
        device_group_id: str | None = None,
        logical_name: str | None = None,
        entity_name: str | None = None,
        object_id: str | None = None,
        template=None,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._subentry_id = subentry_id
        self._device_type = device_type
        spec = SPEC_REGISTRY.get(device_type)
        self._attr_unique_id = legacy_unique_id or f"abstractor_{subentry_id}_riemann"
        if entity_name:
            self._attr_name = entity_name
        else:
            self._attr_translation_key = spec.type_key
        device_key = device_group_id or subentry_id
        device_name = resolve_device_name(
            entry.options, device_type, logical_name, template
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            name=device_name,
            manufacturer=str(
                entry.options.get(CONF_DEVICE_MANUFACTURER, DEFAULT_DEVICE_MANUFACTURER)
            ),
            model=str(entry.options.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL)),
        )
        if object_id:
            self.entity_id = f"sensor.{object_id}"
        self._energy = 0.0
        self._last_time: datetime | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self._energy = float(last.native_value)  # type: ignore[arg-type]
        self._last_time = dt_util.utcnow()

    def _handle_coordinator_update(self) -> None:
        now = dt_util.utcnow()
        power = None
        if self.coordinator.data:
            power = self.coordinator.data.get(self._subentry_id)
        if self._last_time is not None:
            elapsed = (now - self._last_time).total_seconds()
            self._energy = _integrate_energy(self._energy, power, elapsed)
        self._last_time = now
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        return round(self._energy, 4)
