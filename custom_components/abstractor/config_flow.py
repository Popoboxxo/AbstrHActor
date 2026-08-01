"""Config flow for Abstractor."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_DEVICE_TYPE,
    CONF_FALLBACK_ZERO,
    CONF_INVERT,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    CONF_SPIKE_FILTER,
    DOMAIN,
    SENSOR_TYPES,
)

_LOGGER = logging.getLogger(__name__)

class AbstractorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Abstractor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            sources = user_input.get(CONF_SOURCE_ENTITY_IDS) or [
                user_input.get(CONF_SOURCE_ENTITY_ID)
            ]
            sources = [source for source in sources if source]
            if not sources:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._user_schema(),
                    errors={"base": "source_required"},
                )
            if len(sources) > 1:
                user_input[CONF_SOURCE_ENTITY_IDS] = sorted(set(sources))
            else:
                user_input.pop(CONF_SOURCE_ENTITY_IDS, None)
            unique_id = (
                f"abstractor_{user_input[CONF_DEVICE_TYPE]}_"
                f"{'_'.join(sorted(sources))}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Abstract {user_input[CONF_DEVICE_TYPE]}", data=user_input
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(),
        )

    @staticmethod
    def _user_schema() -> vol.Schema:
        """Build the onboarding schema."""
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
            }
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
                    vol.Required(
                        CONF_SOURCE_ENTITY_IDS,
                        default=self.config_entry.data.get(
                            CONF_SOURCE_ENTITY_IDS,
                            [self.config_entry.data.get(CONF_SOURCE_ENTITY_ID)],
                        ),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Optional(
                        CONF_SPIKE_FILTER,
                        default=self.config_entry.options.get(CONF_SPIKE_FILTER, False)
                    ): bool,
                    vol.Optional(
                        CONF_INVERT,
                        default=self.config_entry.options.get(CONF_INVERT, False)
                    ): bool,
                    vol.Optional(
                        CONF_FALLBACK_ZERO,
                        default=self.config_entry.options.get(CONF_FALLBACK_ZERO, False)
                    ): bool,
                }
            ),
        )
