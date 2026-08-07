"""Config flow for Abstractor."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
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
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SENSOR_TYPES,
)

_LOGGER = logging.getLogger(__name__)

class AbstractorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Abstractor."""

    VERSION = CONFIG_ENTRY_VERSION

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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

            legacy_unique_id = user_input.get(CONF_LEGACY_UNIQUE_ID) or None
            if legacy_unique_id:
                # Migrating an existing YAML template sensor (REQ-CORE-003):
                # reuse its unique_id verbatim so recorder / long-term
                # statistics keep counting instead of starting a new series.
                user_input[CONF_LEGACY_UNIQUE_ID] = legacy_unique_id
                unique_id = legacy_unique_id
            else:
                user_input.pop(CONF_LEGACY_UNIQUE_ID, None)
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
                vol.Optional(CONF_LEGACY_UNIQUE_ID): selector.TextSelector(),
            }
        )


    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return AbstractorOptionsFlowHandler()


class AbstractorOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
                    vol.Optional(
                        CONF_NET_SUBTRACT_ENTITY_ID,
                        description={
                            "suggested_value": self.config_entry.options.get(
                                CONF_NET_SUBTRACT_ENTITY_ID
                            )
                        },
                    ): selector.EntitySelector(),
                    vol.Optional(
                        CONF_FALLBACK_SOURCE_ENTITY_ID,
                        description={
                            "suggested_value": self.config_entry.options.get(
                                CONF_FALLBACK_SOURCE_ENTITY_ID
                            )
                        },
                    ): selector.EntitySelector(),
                    vol.Optional(
                        CONF_FALLBACK_CONDITION_ENTITY_ID,
                        description={
                            "suggested_value": self.config_entry.options.get(
                                CONF_FALLBACK_CONDITION_ENTITY_ID
                            )
                        },
                    ): selector.EntitySelector(),
                    vol.Optional(
                        CONF_FALLBACK_CONDITION_STATE,
                        description={
                            "suggested_value": self.config_entry.options.get(
                                CONF_FALLBACK_CONDITION_STATE
                            )
                        },
                    ): selector.TextSelector(),
                }
            ),
        )
