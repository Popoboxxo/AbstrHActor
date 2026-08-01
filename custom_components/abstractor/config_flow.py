"""Config flow for Abstractor."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import CONF_DEVICE_TYPE, CONF_SOURCE_ENTITY_ID, DOMAIN, SENSOR_TYPES

_LOGGER = logging.getLogger(__name__)

class AbstractorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Abstractor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            unique_id = f"abstractor_{user_input[CONF_SOURCE_ENTITY_ID]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Abstract {user_input[CONF_DEVICE_TYPE]}", data=user_input
            )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=SENSOR_TYPES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_SOURCE_ENTITY_ID): selector.EntitySelector(),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return AbstractorOptionsFlowHandler(config_entry)


class AbstractorOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "spike_filter", 
                        default=self.config_entry.options.get("spike_filter", False)
                    ): bool,
                    vol.Optional(
                        "invert", 
                        default=self.config_entry.options.get("invert", False)
                    ): bool,
                    vol.Optional(
                        "fallback_zero", 
                        default=self.config_entry.options.get("fallback_zero", False)
                    ): bool,
                }
            ),
        )
