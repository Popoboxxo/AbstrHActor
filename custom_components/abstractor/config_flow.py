"""Config flow for Abstractor."""
from __future__ import annotations

import logging
from collections.abc import Mapping
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
    CONF_CREATE_NEW_DEVICE,
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
    ROOT_ENTRY_TITLE,
    ROOT_UNIQUE_ID,
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


def _device_id_for_group(hass, group_id: str) -> str | None:
    """Resolve this integration's own (DOMAIN, X) identifier back to a device_id.

    Reverse of `_device_group_id_for_device`: used to pre-fill the reconfigure
    form's device selector with the subentry's CURRENT device, so resubmitting
    the form for an unrelated reason (e.g. toggling spike_filter) shows the
    already-bundled device as selected instead of looking like "no device".
    """
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, group_id)})
    return device.id if device is not None else None


class AbstractorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the one-time setup of the Abstractor root entry."""

    VERSION = CONFIG_ENTRY_VERSION

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the singleton root entry; no sensor data is collected here."""
        await self.async_set_unique_id(ROOT_UNIQUE_ID)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title=ROOT_ENTRY_TITLE, data={})

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
                data = self._normalize(user_input, sources, current_data=current.data)
                device_type = data[CONF_DEVICE_TYPE]
                return self.async_update_and_abort(
                    self._get_reconfigure_entry(),
                    current,
                    title=f"Abstract {device_type}",
                    data=data,
                )

        # Pre-fill the device selector with the subentry's CURRENT device.
        # CONF_TARGET_DEVICE_ID (a transient form field, HA registry device_id)
        # and CONF_DEVICE_GROUP_ID (what's actually stored, our own (DOMAIN, X)
        # identifier) are different keys, so current.data alone never fills the
        # selector — without this, resubmitting the form for an unrelated
        # reason looks exactly like explicitly clearing the device.
        suggested_values = dict(current.data)
        group_id = suggested_values.get(CONF_DEVICE_GROUP_ID)
        if group_id:
            device_id = _device_id_for_group(self.hass, group_id)
            if device_id:
                suggested_values[CONF_TARGET_DEVICE_ID] = device_id

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._schema(reconfigure=True), suggested_values
            ),
            errors=errors,
        )

    def _normalize(
        self,
        user_input: dict[str, Any],
        sources: list[str],
        current_data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Shared shaping for both create and reconfigure: sources, legacy id,
        and resolving the picked target device into our own identifier key.

        `current_data` is the subentry's pre-existing data, passed only on
        reconfigure. Device-group resolution, in priority order:
        1. `CONF_TARGET_DEVICE_ID` submitted → resolve and use that group id
           (moving to a specific existing device always wins).
        2. Else `CONF_CREATE_NEW_DEVICE` is True in this submission → the
           explicit "detach" signal; `CONF_DEVICE_GROUP_ID` is left absent
           from the returned data entirely, so the sensor falls back to its
           own device keyed by its own subentry_id (same as an ungrouped
           sensor elsewhere in this codebase).
        3. Else (neither submitted) → any group id the subentry already had
           is carried forward unchanged rather than silently dropped —
           reconfiguring a bundled sensor for an unrelated reason (e.g.
           toggling spike_filter) must not un-bundle it from its device.
        """
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
        create_new_device = data.pop(CONF_CREATE_NEW_DEVICE, False)
        if target_device_id:
            group_id = _device_group_id_for_device(self.hass, target_device_id)
            if group_id:
                data[CONF_DEVICE_GROUP_ID] = group_id
        elif create_new_device:
            # Explicit detach: leave CONF_DEVICE_GROUP_ID absent entirely.
            pass
        elif current_data and current_data.get(CONF_DEVICE_GROUP_ID):
            data[CONF_DEVICE_GROUP_ID] = current_data[CONF_DEVICE_GROUP_ID]
        return data

    @staticmethod
    def _schema(*, reconfigure: bool = False) -> vol.Schema:
        """Build the sensor schema — shared by create and reconfigure.

        `reconfigure=True` adds `CONF_CREATE_NEW_DEVICE`, an explicit
        "detach into its own device" checkbox that only makes sense when
        editing an already-bundled sensor — on the create step, "no device
        selected" already unambiguously means "new device" by definition,
        so that field is omitted there.
        """
        schema: dict[Any, Any] = {
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
        }
        if reconfigure:
            schema[vol.Optional(CONF_CREATE_NEW_DEVICE, default=False)] = bool
        schema.update(
            {
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
        return vol.Schema(schema)
