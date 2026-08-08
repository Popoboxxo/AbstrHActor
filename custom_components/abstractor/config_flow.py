"""Config flow for Abstractor."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .const import (
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_TYPE,
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
    CONF_FALLBACK_ZERO,
    CONF_INVERT,
    CONF_LEGACY_UNIQUE_ID,
    CONF_NET_SUBTRACT_ENTITY_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    CONF_SPIKE_FILTER,
    CONF_TARGET_DEVICE_ID,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SENSOR_TYPES,
    SUBENTRY_TYPE_SENSOR,
)

_LOGGER = logging.getLogger(__name__)


def _device_group_id_for_device(hass, device_id: str) -> str | None:
    """Look up this integration's own (DOMAIN, X) identifier for a device_id.

    A user picks a target device via HA's internal registry device_id
    (opaque to us); to bundle a new sensor onto that device we need the
    SAME identifier key an earlier subentry originally registered that
    device under, so the device registry keeps merging them into one
    device instead of creating a second one.
    """
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            return identifier
    return None


class AbstractorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the one-time setup of the Abstractor root entry."""

    VERSION = CONFIG_ENTRY_VERSION

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the singleton root entry; no sensor data is collected here."""
        await self.async_set_unique_id("abstractor_root")
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="Abstractor", data={})

        return self.async_show_form(step_id="user")

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {SUBENTRY_TYPE_SENSOR: AbstractorSensorSubentryFlowHandler}


class AbstractorSensorSubentryFlowHandler(ConfigSubentryFlow):
    """Create or reconfigure one Abstract sensor as a subentry."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Create a new Abstract sensor subentry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            sources = user_input.get(CONF_SOURCE_ENTITY_IDS) or [
                user_input.get(CONF_SOURCE_ENTITY_ID)
            ]
            sources = [source for source in sources if source]
            if not sources:
                errors["base"] = "source_required"
            else:
                data = self._normalize(user_input, sources)
                device_type = data[CONF_DEVICE_TYPE]
                return self.async_create_entry(
                    title=f"Abstract {device_type}", data=data
                )

        return self.async_show_form(
            step_id="user", data_schema=self._schema(), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit an existing Abstract sensor's settings, or move it to another device."""
        errors: dict[str, str] = {}
        current = self._get_reconfigure_subentry()

        if user_input is not None:
            sources = user_input.get(CONF_SOURCE_ENTITY_IDS) or [
                user_input.get(CONF_SOURCE_ENTITY_ID)
            ]
            sources = [source for source in sources if source]
            if not sources:
                errors["base"] = "source_required"
            else:
                data = self._normalize(user_input, sources)
                device_type = data[CONF_DEVICE_TYPE]
                return self.async_update_and_abort(
                    self._get_reconfigure_entry(),
                    current,
                    title=f"Abstract {device_type}",
                    data=data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._schema(), current.data
            ),
            errors=errors,
        )

    def _normalize(self, user_input: dict[str, Any], sources: list[str]) -> dict[str, Any]:
        """Shared shaping for both create and reconfigure: sources, legacy id,
        and resolving the picked target device into our own identifier key."""
        data = dict(user_input)
        if len(sources) > 1:
            data[CONF_SOURCE_ENTITY_IDS] = sorted(set(sources))
        else:
            data.pop(CONF_SOURCE_ENTITY_IDS, None)

        legacy_unique_id = data.get(CONF_LEGACY_UNIQUE_ID) or None
        if legacy_unique_id:
            data[CONF_LEGACY_UNIQUE_ID] = legacy_unique_id
        else:
            data.pop(CONF_LEGACY_UNIQUE_ID, None)

        target_device_id = data.pop(CONF_TARGET_DEVICE_ID, None)
        if target_device_id:
            group_id = _device_group_id_for_device(self.hass, target_device_id)
            if group_id:
                data[CONF_DEVICE_GROUP_ID] = group_id
        return data

    @staticmethod
    def _schema() -> vol.Schema:
        """Build the sensor schema — shared by create and reconfigure."""
        return vol.Schema(
            {
                vol.Required(CONF_DEVICE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=SENSOR_TYPES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_SOURCE_ENTITY_ID): selector.EntitySelector(),
                vol.Optional(CONF_SOURCE_ENTITY_IDS): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
                vol.Optional(CONF_LEGACY_UNIQUE_ID): selector.TextSelector(),
                vol.Optional(CONF_TARGET_DEVICE_ID): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(integration=DOMAIN)
                ),
                vol.Optional(CONF_SPIKE_FILTER, default=False): bool,
                vol.Optional(CONF_INVERT, default=False): bool,
                vol.Optional(CONF_FALLBACK_ZERO, default=False): bool,
                vol.Optional(CONF_NET_SUBTRACT_ENTITY_ID): selector.EntitySelector(),
                vol.Optional(CONF_FALLBACK_SOURCE_ENTITY_ID): selector.EntitySelector(),
                vol.Optional(
                    CONF_FALLBACK_CONDITION_ENTITY_ID
                ): selector.EntitySelector(),
                vol.Optional(CONF_FALLBACK_CONDITION_STATE): selector.TextSelector(),
            }
        )
