"""Cover platform for Abstractor (actuator proxy)."""
from __future__ import annotations

from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_POSITION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from ._actuator import AbstractorActuatorEntity, primary_source_id
from .const import (
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    DOMAIN,
)
from .specs import SPEC_REGISTRY


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN]["coordinator"]
    for subentry_id, subentry in entry.subentries.items():
        device_type = subentry.data.get(CONF_DEVICE_TYPE, "")
        spec = SPEC_REGISTRY.try_get(device_type)
        if spec is None or spec.platform != "cover" or not spec.enabled:
            continue
        source_id = primary_source_id(subentry.data)
        if not source_id:
            continue
        async_add_entities(
            [
                AbstractorCover(
                    coordinator,
                    entry,
                    device_type,
                    source_id,
                    subentry.data.get(CONF_LEGACY_UNIQUE_ID),
                    subentry_id=subentry_id,
                    device_group_id=subentry.data.get(CONF_DEVICE_GROUP_ID),
                )
            ],
            config_subentry_id=subentry_id,
        )


class AbstractorCover(AbstractorActuatorEntity, CoverEntity):
    """A position-aware cover that proxies a source cover entity."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
    )

    @property
    def current_cover_position(self) -> int | None:
        value = self._source_state
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        if position is None:
            return None
        return position == 0

    async def async_open_cover(self, **kwargs) -> None:
        await self._call_source("open_cover")

    async def async_close_cover(self, **kwargs) -> None:
        await self._call_source("close_cover")

    async def async_set_cover_position(self, **kwargs) -> None:
        await self._call_source(
            "set_cover_position", {ATTR_POSITION: kwargs.get(ATTR_POSITION)}
        )
