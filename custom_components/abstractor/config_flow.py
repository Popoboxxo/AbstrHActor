"""Config flow for Abstractor."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from inspect import signature
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_CREATE_NEW_DEVICE,
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
    CONF_FALLBACK_ZERO,
    CONF_INFLUX_BUCKET,
    CONF_INFLUX_HOST,
    CONF_INFLUX_ORG,
    CONF_INFLUX_TOKEN,
    CONF_INVERT,
    CONF_LEGACY_UNIQUE_ID,
    CONF_NET_SUBTRACT_ENTITY_ID,
    CONF_POLL_INTERVAL,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    CONF_SPIKE_FILTER,
    CONF_TARGET_DEVICE_ID,
    CONFIG_ENTRY_VERSION,
    DEFAULT_DEVICE_MANUFACTURER,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_NAME,
    DEFAULT_OPTIONS,
    DOMAIN,
    POLL_INTERVAL_MAX,
    POLL_INTERVAL_MIN,
    POLL_INTERVAL_PRESETS,
    ROOT_ENTRY_TITLE,
    ROOT_UNIQUE_ID,
    SENSOR_TYPES,
    SUBENTRY_TYPE_SENSOR,
)

_LOGGER = logging.getLogger(__name__)


def _device_group_id_for_device(hass: HomeAssistant, device_id: str) -> str | None:
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


@dataclass(frozen=True)
class RegistryCapabilities:
    """Feature-detected shape of the installed HA registry model.

    HA 2026.8 restricted devices to a single config entry and at most one
    subentry, deprecating the union-style ``config_entries``/
    ``config_entries_subentries`` fields and the ``add/remove_config_*``
    kwargs of ``async_update_device`` in favour of singular owner fields and
    ``new_config_entry_id``/``new_config_subentry_id``. Rather than pin an
    upper (or lower) HA version and scatter checks through the flow, all of
    those differences are detected once, here, from the installed objects.
    Unknown shapes fail closed: the mapping is rejected before any mutation.
    """

    owv_model: str
    add_config_entry_id: str | None
    add_config_subentry_id: str | None
    remove_config_entry_id: str | None
    remove_config_subentry_id: str | None
    new_config_entry_id: str | None
    new_config_subentry_id: str | None
    entity_update_has_device_id: bool

    @property
    def union(self) -> bool:
        """True when the runtime exposes the pre-2026.8 union ownership model."""
        return self.owv_model != "single-owner"


def _detect_ownership_model(device_cls: type[dr.DeviceEntry]) -> str:
    """Return ``"single-owner"`` or ``"union"`` for the DeviceEntry class.

    Inspects the ``DeviceEntry`` class directly (never an instance), so no
    registry dataclass is ever constructed — their constructor signatures vary
    across HA versions (newer releases require ``config_entry_id``), and
    instantiating one is both unnecessary and brittle.

    Feature detection, not an HA version pin. The new owner fields
    (``config_entry_id``/``config_subentry_id``) only exist on a runtime that
    has adopted the single-owner model; a runtime that still only carries the
    union fields is treated as union-compatible. A device class caught
    between the two models (e.g. a compatibility shim that reports a singular
    owner value while still carrying union collection fields) is only treated
    as single-owner when the singular fields are genuinely present.
    """
    has_owner = hasattr(device_cls, "config_entry_id")
    has_subentry_owner = hasattr(device_cls, "config_subentry_id")
    if has_owner and has_subentry_owner:
        return "single-owner"
    return "union"


@lru_cache(maxsize=1)
def _registry_capabilities(hass: HomeAssistant) -> RegistryCapabilities:
    """Detect the installed registry API shape once, closed over the runtime.

    Uses ``inspect.signature`` (never version constants) on the registries the
    installed HA actually exposes, so the same code path works from the
    integration's minimum floor up through the single-owner model and any
    future ``new_config_*``-style rename. ``hass`` is used only as a cache key
    carrier; the registries themselves come from ``dr``/``er`` so detection is
    independent of a particular registry instance.
    """
    device_cls = dr.DeviceRegistry
    entity_cls = er.EntityRegistry

    update_device_params = signature(device_cls.async_update_device).parameters
    update_entity_params = signature(entity_cls.async_update_entity).parameters

    def _kwarg_or_none(*names: str) -> str | None:
        for name in names:
            if name in update_device_params:
                return name
        return None

    # The ownership model is classified from the DeviceEntry class itself
    # (never an instance): where the installed DeviceEntry class lacks the
    # singular owner fields it is union-compatible, and no registry dataclass
    # is ever constructed.
    owv_model = _detect_ownership_model(dr.DeviceEntry)

    return RegistryCapabilities(
        owv_model=owv_model,
        add_config_entry_id=_kwarg_or_none(
            "add_config_entry_id", "new_config_entry_id"
        ),
        add_config_subentry_id=_kwarg_or_none(
            "add_config_subentry_id", "new_config_subentry_id"
        ),
        remove_config_entry_id=_kwarg_or_none(
            "remove_config_entry_id", "new_config_entry_id"
        ),
        remove_config_subentry_id=_kwarg_or_none(
            "remove_config_subentry_id", "new_config_subentry_id"
        ),
        new_config_entry_id=_kwarg_or_none("new_config_entry_id"),
        new_config_subentry_id=_kwarg_or_none("new_config_subentry_id"),
        entity_update_has_device_id="device_id" in update_entity_params,
    )


def _sensor_unique_id(data: Mapping[str, Any]) -> str:
    """Recompute the sensor's unique id from subentry data (sensor.py's rule).

    Mirrors the identity derivation in ``sensor.py`` so the config flow can
    locate the entity row a reconfigure is about to move without importing the
    platform. A legacy unique id always wins; otherwise single-source and
    multi-source ids follow the same derivation as the entity, keeping the
    entity row and its recorder history stable across a move (REQ-CORE-001).
    """
    if legacy := data.get(CONF_LEGACY_UNIQUE_ID):
        return str(legacy)
    sources = data.get(CONF_SOURCE_ENTITY_IDS) or [data.get(CONF_SOURCE_ENTITY_ID)]
    sources = [source for source in sources if source]
    device_type = data.get(CONF_DEVICE_TYPE, "")
    if len(sources) == 1:
        return f"abstractor_{sources[0]}_{device_type}"
    return f"abstractor_{device_type}_{'_'.join(sorted(sources))}"


class AbstractorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the one-time setup of the Abstractor root entry."""

    VERSION = CONFIG_ENTRY_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AbstractorOptionsFlow:
        """Return the options flow for the singleton root entry."""
        return AbstractorOptionsFlow()

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


class AbstractorOptionsFlow(config_entries.OptionsFlow):
    """Manage Abstractor polling, export, and device presentation options."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._pending_options: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and persist the main options form."""
        current = dict(DEFAULT_OPTIONS) | dict(self.config_entry.options)
        current_interval = int(current[CONF_POLL_INTERVAL])
        interval_value = (
            str(current_interval)
            if current_interval in POLL_INTERVAL_PRESETS
            else "custom"
        )

        if user_input is not None:
            submitted = dict(user_input)
            influx_host = submitted.get(CONF_INFLUX_HOST, "")
            if influx_host and not influx_host.startswith(("http://", "https://")):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._init_schema(current, interval_value),
                    errors={"base": "invalid_influx_host"},
                )
            interval_value = submitted[CONF_POLL_INTERVAL]
            if interval_value == "custom":
                self._pending_options = {
                    **current,
                    **submitted,
                    CONF_POLL_INTERVAL: current_interval,
                }
                return await self.async_step_poll_interval()
            submitted[CONF_POLL_INTERVAL] = int(interval_value)
            return self.async_create_entry(
                title="", data=dict(DEFAULT_OPTIONS) | submitted
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self._init_schema(current, interval_value),
        )

    @staticmethod
    def _init_schema(current: dict[str, Any], interval_value: str) -> vol.Schema:
        """Build the main options-flow schema (shared by the initial render
        and the re-render-with-errors path after a validation failure)."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_POLL_INTERVAL, default=interval_value
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            *(str(value) for value in POLL_INTERVAL_PRESETS),
                            "custom",
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_INFLUX_HOST, default=current.get(CONF_INFLUX_HOST, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_INFLUX_TOKEN, default=current.get(CONF_INFLUX_TOKEN, "")
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Optional(
                    CONF_INFLUX_ORG, default=current.get(CONF_INFLUX_ORG, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_INFLUX_BUCKET, default=current.get(CONF_INFLUX_BUCKET, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DEVICE_NAME,
                    default=current.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME),
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DEVICE_MANUFACTURER,
                    default=current.get(
                        CONF_DEVICE_MANUFACTURER, DEFAULT_DEVICE_MANUFACTURER
                    ),
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DEVICE_MODEL,
                    default=current.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL),
                ): selector.TextSelector(),
            }
        )

    async def async_step_poll_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect a bounded custom polling interval."""
        if user_input is not None:
            options = dict(self._pending_options)
            options[CONF_POLL_INTERVAL] = int(user_input[CONF_POLL_INTERVAL])
            return self.async_create_entry(
                title="", data=dict(DEFAULT_OPTIONS) | options
            )

        current_interval = int(
            self._pending_options.get(
                CONF_POLL_INTERVAL, DEFAULT_OPTIONS[CONF_POLL_INTERVAL]
            )
        )
        return self.async_show_form(
            step_id="poll_interval",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL, default=current_interval
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=POLL_INTERVAL_MIN,
                            max=POLL_INTERVAL_MAX,
                            mode=selector.NumberSelectorMode.BOX,
                            step=1,
                        )
                    )
                }
            ),
        )


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
                # Flow integration order: validate sources, run the ownership
                # safety check + registry transaction for a real move/detach,
                # and only then normalize and persist. A new sensor has no
                # entity row yet, so there is no entity to reparent — the
                # subentry data is committed verbatim and normal entity setup
                # later creates the entity on the requested safe device.
                errors = await self._validate_device_mapping(user_input)
                if errors:
                    return self.async_show_form(
                        step_id="user", data_schema=self._schema(), errors=errors
                    )
                if not user_input.get(CONF_LEGACY_UNIQUE_ID):
                    # No stable identity was typed in manually — generate one
                    # now, at creation time only. This is what closes GH#19:
                    # without it, a brand-new sensor's unique_id is derived
                    # from its source entity ids (see sensor.py) and changes
                    # the moment the user reconfigures it onto different
                    # hardware, orphaning the entity and its recorder
                    # history. _normalize()/sensor.py already treat a set
                    # legacy_unique_id as permanent and winning over any
                    # later source change — this just makes sure one always
                    # exists from the start.
                    user_input = {
                        **user_input,
                        CONF_LEGACY_UNIQUE_ID: f"abstractor_{uuid.uuid4().hex}",
                    }
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
                # Flow integration order: validate sources, resolve mapping
                # intent, run the ownership safety check, and execute the
                # ordered registry transaction for a real move/detach BEFORE
                # persisting subentry data. On conflict/unsupported runtime the
                # form is re-shown with a fail-loud error and zero mutation.
                errors = await self._validate_device_mapping(
                    user_input, current_data=current.data
                )
                if errors:
                    suggested_values = dict(current.data)
                    suggested_values[CONF_TARGET_DEVICE_ID] = self._current_device_id(
                        current
                    )
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
        suggested_values = dict(current.data)

        # Pre-fill the device selector with the device this sensor currently
        # resides on: resolve the stored CONF_DEVICE_GROUP_ID else fall back to
        # this sensor's own ungrouped device, keyed by its own subentry id.
        suggested_values[CONF_TARGET_DEVICE_ID] = self._current_device_id(current)

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

    def _current_device_id(self, current: ConfigSubentry) -> str | None:
        """Resolve the device id this subentry currently resides on.

        ``CONF_DEVICE_GROUP_ID`` names the ``(DOMAIN, X)`` identifier of an
        existing bundled device; absent, the sensor lives on its own device
        keyed by ``(DOMAIN, subentry_id)``. Both are resolved through the same
        identifier convention sensor.py registers, so the selector pre-fill
        always points at the device the entity row actually sits on.
        """
        device_registry = dr.async_get(self.hass)
        group_id = current.data.get(CONF_DEVICE_GROUP_ID) or current.subentry_id
        device = device_registry.async_get_device({(DOMAIN, group_id)})
        if device is None:
            return None
        return device.id

    async def _validate_device_mapping(
        self,
        user_input: dict[str, Any],
        current_data: Mapping[str, Any] | None = None,
    ) -> dict[str, str]:
        """Run the ownership safety decision and, when safe, the registry move.

        This is the integration-order hook called from both create and
        reconfigure: it runs on the HA event loop, resolves the requested
        mapping intent, performs the ownership safety check, and executes the
        ordered registry transaction for a real move/detach — all BEFORE any
        subentry data write. It returns ``{}`` when the mapping is safe (or a
        no-op) and ``{"base": "device_mapping_conflict"}`` when it must fail
        loud without mutating anything.

        Never calls ``async_get_or_create`` against a *target* before the
        ownership decision; only the detach destination (this sensor's own
        ``(DOMAIN, subentry_id)`` key) is resolved up front, and that is not a
        target of another subentry. UI-only keys are never persisted here —
        they are stripped in ``_normalize`` and ``CONF_DEVICE_GROUP_ID`` alone
        identifies a device in stored data.
        """
        create_new_device = bool(user_input.get(CONF_CREATE_NEW_DEVICE))
        target_device_id = user_input.get(CONF_TARGET_DEVICE_ID)

        if not create_new_device and not target_device_id:
            # Neither mapping control touched: carry-forward only. `_normalize`
            # keeps the existing group id as-is and no registry work happens.
            return {}

        capabilities = _registry_capabilities(self.hass)
        if not capabilities.entity_update_has_device_id:
            # No safe reparenting operation exists on this runtime.
            _LOGGER.error(
                "Abstractor device mapping rejected: the installed entity "
                "registry does not support the device_id argument of "
                "async_update_entity"
            )
            return {"base": "device_mapping_conflict"}

        root_entry = self._get_subentry_config_entry()

        if create_new_device and not target_device_id:
            # Explicit detach. Safe on both ownership models: the entity row is
            # moved before any ownership link is dropped, and on single-owner
            # HA the old link is only dropped when no other entity remains.
            if not self._detach_to_own_device(root_entry, current_data, capabilities):
                return {"base": "device_mapping_conflict"}
            return {}

        # A target device was submitted.
        device_registry = dr.async_get(self.hass)
        target_device = (
            device_registry.async_get(target_device_id) if target_device_id else None
        )
        if target_device is None:
            _LOGGER.error(
                "Abstractor device mapping rejected: selected device %s does "
                "not resolve in the registry",
                target_device_id,
            )
            return {"base": "device_mapping_conflict"}

        if _device_group_id_for_device(self.hass, target_device.id) is None:
            _LOGGER.error(
                "Abstractor device mapping rejected: device %s carries no "
                "%s identifier",
                target_device.id,
                DOMAIN,
            )
            return {"base": "device_mapping_conflict"}

        if not self._apply_target_mapping(
            root_entry,
            current_data,
            target_device,
            capabilities,
        ):
            return {"base": "device_mapping_conflict"}

        return {}

    @property
    def _current_subentry_id(self) -> str | None:
        """Return this flow's subentry id (reconfigure) or None (create).

        Uses the base class's ``_reconfigure_subentry_id`` property when the
        flow source is a reconfigure; a create flow has no subentry yet.
        """
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return self._reconfigure_subentry_id
        return None

    def _detach_to_own_device(
        self,
        root_entry: ConfigEntry,
        current_data: Mapping[str, Any] | None,
        capabilities: RegistryCapabilities,
    ) -> bool:
        """Move this sensor to its own ``(DOMAIN, subentry_id)`` device.

        Detach design (see docs): resolve or create the destination device,
        move the entity row to it BEFORE removing any old ownership, then drop
        the old link — unconditionally on union HA, only when no other entity
        remains on single-owner HA. Moving the row before dropping the link is
        what preserves its identity and recorder history across the move
        (REQ-CORE-001). Returns False on an unexpected registry error
        (logged), leaving the subentry data unwritten.

        A create flow has no existing entity row or old device to detach from,
        so it is a no-op here; the new sensor is simply created ungrouped.
        """
        subentry_id = self._current_subentry_id
        if subentry_id is None or current_data is None:
            # New sensor: already ungrouped, nothing to detach.
            return True

        device_registry = dr.async_get(self.hass)
        entity_registry = er.async_get(self.hass)

        try:
            new_device = device_registry.async_get_or_create(
                config_entry_id=root_entry.entry_id,
                config_subentry_id=subentry_id,
                identifiers={(DOMAIN, subentry_id)},
            )

            unique_id = _sensor_unique_id(current_data)
            entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            old_device_id: str | None = None
            if entity_id is not None:
                entity = entity_registry.async_get(entity_id)
                if entity is not None:
                    old_device_id = entity.device_id

            if entity_id is None:
                # No entity row to move (sensor never finished first setup, or
                # was never created). Nothing else to do and nothing to drop.
                return True

            # Critical ordering: move the entity row to the new device FIRST,
            # so its recorder history follows the row instead of being deleted
            # by the ownership drop below.
            entity_registry.async_update_entity(entity_id, device_id=new_device.id)

            if old_device_id is None:
                return True

            old_device = device_registry.async_get(old_device_id)
            if old_device is None:
                return True

            if not capabilities.union:
                # Single-owner runtime: dropping the old link synchronously
                # invokes the entity-registry listener and deletes every row
                # still on the old device, so only drop it when no OTHER row
                # remains. This sensor's own row has already moved off.
                remaining = [
                    entry
                    for entry in er.async_entries_for_device(
                        entity_registry, old_device_id
                    )
                    if entry.entity_id != entity_id
                ]
                if remaining:
                    _LOGGER.warning(
                        "Abstractor detach: leaving the stale ownership link of "
                        "device %s for subentry %s in place because %s other "
                        "entity row(s) still live on it; removing it would "
                        "delete them on this Home Assistant version",
                        old_device_id,
                        subentry_id,
                        len(remaining),
                    )
                    return True

            # Union runtime: remove only the current subentry link from the old
            # device. On single-owner runtime (no other rows remain, verified
            # above) this is a no-op because devices are moved, not unlinked.
            self._remove_owner_link(old_device, root_entry, subentry_id, capabilities)
            return True
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Abstractor detach failed: %s", exc)
            return False

    def _apply_target_mapping(
        self,
        root_entry: ConfigEntry,
        current_data: Mapping[str, Any] | None,
        target_device: dr.DeviceEntry,
        capabilities: RegistryCapabilities,
    ) -> bool:
        """Inspect the target's ownership and execute a safe move, or reject it.

        Ownership is inspected from ``target_device.config_entries_subentries``
        (never from an identifier alone), distinguishing THIS sensor's subentry
        from a different one. Returns False when the move cannot be performed
        non-destructively (single-owner runtime with a cross-subentry target,
        or an unexpected registry error) so the caller surfaces
        ``device_mapping_conflict``; True after a successful or no-op move,
        with the entity row's identity and recorder history preserved
        (REQ-CORE-001).
        """
        entity_registry = er.async_get(self.hass)
        subentry_id = self._current_subentry_id

        # Which subentries already own the target device for this root entry.
        owner_subentries: set[str | None] = set(
            target_device.config_entries_subentries.get(root_entry.entry_id, ())
        )

        is_same_owner = subentry_id is not None and subentry_id in owner_subentries
        # Cross-subentry when the target already belongs to some subentry that
        # is not this sensor's. On a create flow this sensor has no subentry
        # yet, so any owned target is (or would become) a cross-subentry bundle.
        is_cross_subentry = bool(owner_subentries) and not is_same_owner

        if is_cross_subentry and not capabilities.union:
            _LOGGER.error(
                "Abstractor device mapping rejected: target device %s is owned "
                "by a different Abstractor subentry and this Home Assistant "
                "runtime is single-owner; bundling could delete that sensor's "
                "entity and recorder history",
                target_device.id,
            )
            return False

        # Locate this sensor's entity row (reconfigure only; a create flow has
        # none) and its current device.
        entity_id = None
        old_device_id = None
        if subentry_id is not None and current_data is not None:
            unique_id = _sensor_unique_id(current_data)
            entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is not None:
                entity = entity_registry.async_get(entity_id)
                if entity is not None:
                    old_device_id = entity.device_id

        # Same-owner / no-op: entity already on the target and target already
        # owned by this subentry — nothing to change in the registries.
        if (
            is_same_owner
            and entity_id is not None
            and old_device_id == target_device.id
        ):
            return True

        try:
            if subentry_id is not None:
                if is_cross_subentry:
                    # Union-compatible runtime only (guarded above): explicit,
                    # ordered move. 1) add this root/subentry link to the
                    # target, 2) move the entity row, 3) drop the old link.
                    self._add_owner_link(
                        target_device, root_entry, subentry_id, capabilities
                    )
                elif not is_same_owner:
                    # Target is currently unowned by any subentry (or owned by
                    # a different config entry entirely): claim it for this
                    # subentry. A create flow (subentry_id is None) has no
                    # subentry id yet and no add-link to make here — the new
                    # sensor claims the unowned target via its device identifier
                    # once it is created.
                    self._add_owner_link(
                        target_device, root_entry, subentry_id, capabilities
                    )

            if entity_id is not None:
                entity_registry.async_update_entity(
                    entity_id, device_id=target_device.id
                )

            if old_device_id is not None and old_device_id != target_device.id:
                self._drop_old_link(
                    old_device_id,
                    root_entry,
                    subentry_id,
                    capabilities,
                )
            return True
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Abstractor device move failed: %s", exc)
            return False

    def _add_owner_link(
        self,
        device: dr.DeviceEntry,
        root_entry: ConfigEntry,
        subentry_id: str,
        capabilities: RegistryCapabilities,
    ) -> None:
        """Register this root/subentry as an owner of ``device``.

        Uses the feature-detected kwarg names. On union HA this adds the
        subentry to the device's owner set via ``add_config_entry_id``/
        ``add_config_subentry_id``; on single-owner HA the singular transfer
        kwargs (``new_config_entry_id``/``new_config_subentry_id``) move the
        device to this subentry in a single call.
        """
        device_registry = dr.async_get(self.hass)
        if capabilities.union:
            add_entry_id = capabilities.add_config_entry_id
            add_subentry_id = capabilities.add_config_subentry_id
            if add_entry_id is None or add_subentry_id is None:
                raise RuntimeError("Registry lacks add_config_* kwargs")
            device_registry.async_update_device(
                device.id,
                **{add_entry_id: root_entry.entry_id},  # type: ignore[arg-type]
                **{add_subentry_id: subentry_id},  # type: ignore[arg-type]
            )
        else:
            if (
                capabilities.new_config_entry_id is None
                or capabilities.new_config_subentry_id is None
            ):
                raise RuntimeError("Registry lacks new_config_* kwargs")
            device_registry.async_update_device(
                device.id,
                **{capabilities.new_config_entry_id: root_entry.entry_id},  # type: ignore[arg-type]
                **{capabilities.new_config_subentry_id: subentry_id},  # type: ignore[arg-type]
            )

    def _remove_owner_link(
        self,
        device: dr.DeviceEntry,
        root_entry: ConfigEntry,
        subentry_id: str,
        capabilities: RegistryCapabilities,
    ) -> None:
        """Remove this root/subentry ownership link from ``device``.

        Only the add/remove union kwargs apply here: on a single-owner runtime
        a device has exactly one owner and is moved, not unlinked, so this is
        a no-op there (the caller guards the case where a stale link must be
        left in place instead).
        """
        if not capabilities.union:
            return
        remove_entry_id = capabilities.remove_config_entry_id
        remove_subentry_id = capabilities.remove_config_subentry_id
        if remove_entry_id is None or remove_subentry_id is None:
            raise RuntimeError("Registry lacks remove_config_* kwargs")
        dr.async_get(self.hass).async_update_device(
            device.id,
            **{remove_entry_id: root_entry.entry_id},  # type: ignore[arg-type]
            **{remove_subentry_id: subentry_id},  # type: ignore[arg-type]
        )

    def _drop_old_link(
        self,
        old_device_id: str,
        root_entry: ConfigEntry,
        subentry_id: str | None,
        capabilities: RegistryCapabilities,
    ) -> None:
        """Drop this sensor's old ownership link after its entity has moved.

        Only meaningful on union HA (single-owner devices are moved, not
        unlinked). On single-owner HA leave the link: this sensor's row has
        already been re-pointed away, and removing an owner link there could
        synchronously delete other rows still on the old device.
        """
        if not capabilities.union or subentry_id is None:
            return
        device_registry = dr.async_get(self.hass)
        old_device = device_registry.async_get(old_device_id)
        if old_device is None:
            return
        self._remove_owner_link(old_device, root_entry, subentry_id, capabilities)

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

        This stays a pure data-shaping function: the ownership safety decision
        and the actual registry transaction live in `_validate_device_mapping`
        (called from the flow handlers before this runs), and the UI-only keys
        (`CONF_TARGET_DEVICE_ID`, `CONF_CREATE_NEW_DEVICE`) are popped above so
        they are never persisted.
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

        Adds the device-mapping fields (`CONF_TARGET_DEVICE_ID` device
        selector filtered to `DOMAIN`, and the `CONF_CREATE_NEW_DEVICE`
        checkbox defaulting False) for both create and reconfigure. These are
        UI-only and never persisted: `_normalize` strips them and
        `_validate_device_mapping` turns them into a safe registry operation
        or a fail-loud conflict error before any subentry data write.

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
                # Non-destructive device mapping controls (UI-only, never
                # persisted — see _normalize and _validate_device_mapping).
                vol.Optional(CONF_TARGET_DEVICE_ID): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(integration=DOMAIN)
                ),
                vol.Optional(
                    CONF_CREATE_NEW_DEVICE, default=False
                ): selector.BooleanSelector(),
            }
        )
        return vol.Schema(schema)
