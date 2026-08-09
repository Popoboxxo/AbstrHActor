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

    def _get_subentry_config_entry(self) -> ConfigEntry:
        """Return the config entry linked to this subentry flow's context.

        HA 2025.3.0 (this integration's pinned floor, per manifest.json)
        exposes ``ConfigSubentryFlow._get_reconfigure_entry()``. Newer HA
        (observed on 2026.8.0) renamed it to ``_get_entry()`` as part of
        unifying entry access across subentry flow steps. Feature-detect
        at call time so a single code path works across that whole range
        without pinning an upper `homeassistant` version bound.
        """
        if hasattr(self, "_get_entry"):
            return self._get_entry()
        return self._get_reconfigure_entry()

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
                    self._get_subentry_config_entry(),
                    current,
                    title=f"Abstract {device_type}",
                    data=data,
                )

        # The schema is built per subentry: once this one has a legacy unique
        # id, that id IS the sensor's identity, so the field is dropped from
        # the form instead of being offered prefilled and clearable (see
        # _schema and _normalize).
        #
        # NOTE: the device-bundling UI fields (CONF_TARGET_DEVICE_ID,
        # CONF_CREATE_NEW_DEVICE) that used to be pre-filled here have been
        # removed from _schema() (GH#18 — using either on current Home
        # Assistant silently merges/moves a device between subentries and
        # destroys the OTHER sensor's entity registry row). No suggested
        # values are needed for a field the form no longer shows.
        suggested_values = dict(current.data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._schema(
                    reconfigure=True,
                    legacy_unique_id_pinned=bool(
                        current.data.get(CONF_LEGACY_UNIQUE_ID)
                    ),
                ),
                suggested_values,
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
        and resolving a picked target device into our own identifier key.

        `current_data` is the subentry's pre-existing data, passed only on
        reconfigure. Anything it already carries wins over an absent field in
        the submission — a reconfigure changes what the user actually changed,
        never what the form simply did not repeat.

        `CONF_LEGACY_UNIQUE_ID` goes one step further: once set it is carried
        forward *unconditionally*, so a resubmission can neither clear nor
        change it. Device-group resolution, in priority order:
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

        GH#18: steps 1 and 2 above are no longer reachable through the UI —
        `_schema()` stopped offering `CONF_TARGET_DEVICE_ID` /
        `CONF_CREATE_NEW_DEVICE` because using either on current Home
        Assistant silently merges/moves a device between subentries and
        destroys the OTHER sensor's entity registry row. The resolution logic
        stays here, inert without a form field to feed it, as the seam a
        future, non-destructive bundling fix will reuse. Step 3 (carrying an
        existing `CONF_DEVICE_GROUP_ID` forward) is the only path currently
        reachable and remains fully active.
        """
        data = dict(user_input)
        if len(sources) > 1:
            data[CONF_SOURCE_ENTITY_IDS] = sorted(set(sources))
        else:
            data.pop(CONF_SOURCE_ENTITY_IDS, None)

        # A legacy unique id is this sensor's identity, not a preference: it is
        # what the entity registry keyed the row on, and with it every bit of
        # recorder history hanging off that row. Whether it got there through a
        # YAML template migration (REQ-CORE-003) or through the device-bundling
        # reconciliation pinning the pre-migration id, clearing or changing it
        # re-derives the unique_id from the current sources, orphans the
        # existing entity and starts a second one from zero.
        #
        # So an already-set value always wins: the reconfigure schema does not
        # even offer the field once one exists, and this carries it forward
        # regardless of what the submission contains — the schema decides what
        # a user can see, this decides what the data can lose. Setting one for
        # the first time stays possible; that is a deliberate, typed-in action.
        pinned_legacy_unique_id = (
            current_data.get(CONF_LEGACY_UNIQUE_ID) if current_data else None
        )
        legacy_unique_id = pinned_legacy_unique_id or data.get(CONF_LEGACY_UNIQUE_ID)
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
    def _schema(
        *, reconfigure: bool = False, legacy_unique_id_pinned: bool = False
    ) -> vol.Schema:
        """Build the sensor schema — shared by create and reconfigure.

        `reconfigure` is accepted for API symmetry with `_normalize` and the
        callers below, even though it currently does not change the returned
        schema: it used to add `CONF_CREATE_NEW_DEVICE`, an explicit "detach
        into its own device" checkbox, but that field (together with
        `CONF_TARGET_DEVICE_ID`) has been removed from the form entirely
        (GH#18 — using either on current Home Assistant silently
        merges/moves a device between subentries and destroys the OTHER
        sensor's entity registry row).

        `legacy_unique_id_pinned=True` drops `CONF_LEGACY_UNIQUE_ID` from the
        form: the subentry already has one, which makes it that sensor's
        actual identity rather than an optional extra. Shown as a prefilled
        text box it reads like a setting one may clear, and clearing it
        silently re-derives the unique_id and orphans the entity together with
        its recorder history. Not rendering it is the honest form of "this
        cannot change" — and `_normalize` enforces the same thing on the data,
        so a submission that bypasses the form cannot drop it either.
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
        }
        if not legacy_unique_id_pinned:
            schema[vol.Optional(CONF_LEGACY_UNIQUE_ID)] = selector.TextSelector()
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
