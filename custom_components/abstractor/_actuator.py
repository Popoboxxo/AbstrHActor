"""Shared actuator entity base for Abstractor.

Actuators are *thin proxies*: they read the configured source entity's state
(through the coordinator's pass-through path for non-numeric specs) and forward
commands to that same source entity's service. Abstractor never talks to
hardware directly — swapping the underlying device means reconfiguring the
source entity, exactly like the sensor side.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
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

_ON_VALUES = {"on", "true", "1", "yes", "home", "open"}


def primary_source_id(data: Mapping[str, Any]) -> str | None:
    """Return the first configured source entity id, or None."""
    ids = data.get(CONF_SOURCE_ENTITY_IDS) or [data.get(CONF_SOURCE_ENTITY_ID)]
    ids = [source for source in ids if source]
    return ids[0] if ids else None


def build_device_info(
    entry, device_type: str, subentry_id: str, device_group_id: str | None
) -> DeviceInfo:
    """Device grouping identical to the sensor/binary_sensor platforms."""
    device_key = device_group_id or subentry_id
    device_name = str(
        entry.options.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME)
    ).replace("{device_type}", device_type.capitalize())
    manufacturer = str(
        entry.options.get(CONF_DEVICE_MANUFACTURER, DEFAULT_DEVICE_MANUFACTURER)
    )
    model = str(entry.options.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL))
    return DeviceInfo(
        identifiers={(DOMAIN, device_key)},
        name=device_name,
        manufacturer=manufacturer,
        model=model,
    )


class AbstractorActuatorEntity(CoordinatorEntity[AbstractorDataUpdateCoordinator]):
    """Common state/command plumbing for a source-proxying actuator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry,
        device_type: str,
        source_id: str,
        legacy_unique_id: str | None = None,
        *,
        subentry_id: str,
        device_group_id: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._subentry_id = subentry_id
        self._device_type = device_type
        self._source_id = source_id
        spec = SPEC_REGISTRY.get(device_type)
        self._attr_unique_id = legacy_unique_id or f"abstractor_{source_id}_{device_type}"
        self._attr_name = spec.display_name
        self._attr_device_info = build_device_info(
            entry, device_type, subentry_id, device_group_id
        )

    @property
    def _source_state(self):
        """The coordinator's pass-through value for this subentry."""
        data = getattr(self.coordinator, "data", None)
        if not data:
            return None
        return data.get(self._subentry_id)

    def _is_on(self) -> bool | None:
        value = self._source_state
        if value is None:
            return None
        return str(value).lower() in _ON_VALUES

    async def _call_source(self, service: str, data: dict | None = None) -> None:
        """Forward a command to the source entity's own service."""
        domain = self._source_id.split(".", 1)[0]
        payload = {ATTR_ENTITY_ID: self._source_id}
        if data:
            payload.update(data)
        await self.hass.services.async_call(domain, service, payload, blocking=True)
