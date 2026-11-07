"""Schema builders shared by the config flow, Options flow and WS layer.

WS-1 (docs/plan-system-audit-followup-2026-11.md): one voluptuous source of
truth per config surface. The config flow renders the FORM variants (with
defaults); the websocket layer validates submitted payloads with the
VALIDATOR variants (no defaults, ``None`` allowed for clearing optional
fields, unknown keys rejected). Selecting one builder can never drift the
other because both consume the same ``_*_SPEC`` field tables.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.helpers import selector

from .const import (
    AGGREGATION_MODES,
    AGGREGATION_SUM,
    CONF_AGGREGATION,
    CONF_CREATE_NEW_DEVICE,
    CONF_DEBUG_SWITCH_ENTITY_ID,
    CONF_DEVICE_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_ENTITY_NAME,
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_ON_ZERO,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
    CONF_FALLBACK_ZERO,
    CONF_INFLUX_BUCKET,
    CONF_INFLUX_HOST,
    CONF_INFLUX_ORG,
    CONF_INFLUX_TOKEN,
    CONF_INVERT,
    CONF_LEGACY_UNIQUE_ID,
    CONF_LOGICAL_NAME,
    CONF_NAMING_TEMPLATE,
    CONF_NET_SUBTRACT_ENTITY_ID,
    CONF_NOTIFY_ENTITY_ID,
    CONF_OBJECT_ID,
    CONF_POLL_INTERVAL,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    CONF_SPIKE_FILTER,
    CONF_TARGET_DEVICE_ID,
    DEFAULT_DEVICE_MANUFACTURER,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_NAME,
    DEFAULT_NAMING_TEMPLATE,
    DOMAIN,
    POLL_INTERVAL_MAX,
    POLL_INTERVAL_MIN,
    POLL_INTERVAL_PRESETS,
)
from .specs import SPEC_REGISTRY


def _subentry_schema_spec(
    device_type: str,
    *,
    reconfigure: bool = False,
    legacy_unique_id_pinned: bool = False,
) -> list[tuple[str, bool, object, object]]:
    """Return ``(key, required, default, validator)`` for one device type.

    The field set derives from the device type's spec in ``SPEC_REGISTRY``:
    a non-numeric (pass-through) type never sees the numeric-only pipeline
    fields (aggregation, spike filter, invert, fallback, net-subtract) that
    only the numeric coordinator pipeline consumes. An unknown type keeps
    the historical full field set so a hand-edited legacy subentry stays
    reconfigureable. ``legacy_unique_id_pinned=True`` drops the field: once
    set, it is that sensor's identity, and the WS validator rejecting it as
    an extra key is the data-side mirror of not rendering it in the form.
    """
    spec = SPEC_REGISTRY.try_get(device_type)
    include_numeric = spec.numeric if spec is not None else True

    entries: list[tuple[str, bool, object, object]] = []
    if reconfigure:
        entries.append(
            (
                CONF_DEVICE_TYPE,
                True,
                None,
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=spec.type_key, label=spec.display_name)
                            for spec in SPEC_REGISTRY.enabled()
                            if spec.platform in ("sensor", "binary_sensor", "switch", "light", "cover")
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            )
        )
    entries.extend(
        (
            (CONF_SOURCE_ENTITY_ID, False, None, selector.EntitySelector()),
            (
                CONF_SOURCE_ENTITY_IDS,
                False,
                None,
                selector.EntitySelector(selector.EntitySelectorConfig(multiple=True)),
            ),
        )
    )
    if not legacy_unique_id_pinned:
        entries.append((CONF_LEGACY_UNIQUE_ID, False, None, selector.TextSelector()))
    entries.extend(
        (
            (CONF_LOGICAL_NAME, False, None, selector.TextSelector()),
            (CONF_ENTITY_NAME, False, None, selector.TextSelector()),
            (CONF_OBJECT_ID, False, None, selector.TextSelector()),
        )
    )
    if include_numeric:
        entries.extend(
            (
                (
                    CONF_AGGREGATION,
                    False,
                    AGGREGATION_SUM,
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=AGGREGATION_MODES,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                ),
                (CONF_SPIKE_FILTER, False, False, bool),
                (CONF_INVERT, False, False, bool),
                (CONF_FALLBACK_ZERO, False, False, bool),
                (CONF_NET_SUBTRACT_ENTITY_ID, False, None, selector.EntitySelector()),
                (
                    CONF_FALLBACK_SOURCE_ENTITY_ID,
                    False,
                    None,
                    selector.EntitySelector(),
                ),
                (
                    CONF_FALLBACK_CONDITION_ENTITY_ID,
                    False,
                    None,
                    selector.EntitySelector(),
                ),
                (CONF_FALLBACK_CONDITION_STATE, False, None, selector.TextSelector()),
                (CONF_FALLBACK_ON_ZERO, False, False, bool),
            )
        )
    entries.extend(
        (
            (
                CONF_TARGET_DEVICE_ID,
                False,
                None,
                selector.DeviceSelector(selector.DeviceSelectorConfig(integration=DOMAIN)),
            ),
            (CONF_CREATE_NEW_DEVICE, False, False, selector.BooleanSelector()),
        )
    )
    return entries


def build_subentry_form_schema(
    device_type: str,
    *,
    reconfigure: bool = False,
    legacy_unique_id_pinned: bool = False,
) -> vol.Schema:
    """Build the config-flow form schema (defaults applied by the flow)."""
    schema: dict[object, object] = {}
    for key, required, default, validator in _subentry_schema_spec(
        device_type,
        reconfigure=reconfigure,
        legacy_unique_id_pinned=legacy_unique_id_pinned,
    ):
        kwargs = {"default": default} if default is not None else {}
        marker = vol.Required if required else vol.Optional
        schema[marker(key, **kwargs)] = validator
    return vol.Schema(schema)


def build_subentry_validator(device_type: str | None = None, *, allow_legacy_unique_id: bool = True) -> vol.Schema:
    """Build the WS payload validator for one device type (no defaults).

    Every optional field additionally accepts ``None`` — the panel sends
    ``null`` to clear an optional pipeline field, and ``_normalize_subentry_data``
    then carries the current value forward unless the key is explicitly cleared.
    Unknown keys are rejected (``PREVENT_EXTRA``), closing the UF-03 hole where
    the old handler persisted ``msg["data"]`` verbatim. The ``device_type`` key
    itself is validated against the enabled spec catalogue plus the caller's
    current type, so the WS cannot accept a type the flow would not offer.
    ``allow_legacy_unique_id=False`` (used on update): once set, that id is the
    sensor's identity, so an update payload neither may change nor clear it —
    the data-side mirror of the form hiding it (GH#19 / REQ-CORE-001).
    """
    fields: dict[object, object] = {}
    for key, _required, _default, validator in _subentry_schema_spec(
        device_type if device_type is not None else "power"
    ):
        if key == CONF_LEGACY_UNIQUE_ID and not allow_legacy_unique_id:
            continue
        fields[vol.Optional(key)] = vol.Any(None, validator)

    enabled_types = [
        spec.type_key
        for spec in SPEC_REGISTRY.enabled()
        if spec.platform in ("sensor", "binary_sensor", "switch", "light", "cover")
    ]
    allowed = list(dict.fromkeys([*enabled_types, *([device_type] if device_type else [])]))
    fields[vol.Optional(CONF_DEVICE_TYPE)] = vol.Any(None, vol.In(allowed))
    return vol.Schema(fields, extra=vol.PREVENT_EXTRA)


def build_options_form_schema(
    current: dict,
    interval_value: str,
    template_options: list[str] | None = None,
) -> vol.Schema:
    """Build the OptionsFlow init schema from the current options values.

    Optional entity selectors must not carry a ``None`` default (voluptuous
    applies defaults before the selector runs, and an entity selector rejects
    ``None``); the default is only attached when a value already exists, and
    an explicit ``None`` (the frontend's way of clearing a selector) stays
    valid via ``vol.Any``. A configured naming template whose file vanished
    falls back to the built-in default so the dropdown keeps a valid option.
    """
    current_template = current.get(CONF_NAMING_TEMPLATE, DEFAULT_NAMING_TEMPLATE)
    if template_options and current_template not in template_options:
        current_template = DEFAULT_NAMING_TEMPLATE

    schema: dict[object, object] = {
        vol.Required(CONF_POLL_INTERVAL, default=interval_value): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[str(value) for value in POLL_INTERVAL_PRESETS] + ["custom"],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_INFLUX_HOST, default=current.get(CONF_INFLUX_HOST, "")): selector.TextSelector(),
        vol.Optional(CONF_INFLUX_TOKEN, default=current.get(CONF_INFLUX_TOKEN, "")): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_INFLUX_ORG, default=current.get(CONF_INFLUX_ORG, "")): (selector.TextSelector()),
        vol.Optional(CONF_INFLUX_BUCKET, default=current.get(CONF_INFLUX_BUCKET, "")): selector.TextSelector(),
        vol.Optional(
            CONF_DEVICE_NAME,
            default=current.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_DEVICE_MANUFACTURER,
            default=current.get(CONF_DEVICE_MANUFACTURER, DEFAULT_DEVICE_MANUFACTURER),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_DEVICE_MODEL,
            default=current.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL),
        ): selector.TextSelector(),
        vol.Optional(CONF_NAMING_TEMPLATE, default=current_template): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=template_options or [DEFAULT_NAMING_TEMPLATE],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
    for key, domain in (
        (CONF_DEBUG_SWITCH_ENTITY_ID, "input_boolean"),
        (CONF_NOTIFY_ENTITY_ID, "notify"),
    ):
        entity_selector = selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))
        kwargs: dict[str, object] = {}
        if current.get(key):
            kwargs["default"] = current[key]
        schema[vol.Optional(key, **kwargs)] = vol.Any(None, entity_selector)
    return vol.Schema(schema)


def build_options_validator() -> vol.Schema:
    """Validate a submitted root-options payload in stored shape.

    Values here are persisted straight into ``entry.options``, so bounds are
    enforced at this boundary (UF-03: ``poll_interval: 999999`` must not reach
    storage). The token stays a plain string field here — masking is a UI
    concern, and this validator never echoes values back.
    """
    return vol.Schema(
        {
            vol.Optional(CONF_POLL_INTERVAL): vol.All(
                vol.Coerce(int), vol.Range(min=POLL_INTERVAL_MIN, max=POLL_INTERVAL_MAX)
            ),
            vol.Optional(CONF_INFLUX_HOST): vol.Any(None, str),
            vol.Optional(CONF_INFLUX_TOKEN): vol.Any(None, str),
            vol.Optional(CONF_INFLUX_ORG): vol.Any(None, str),
            vol.Optional(CONF_INFLUX_BUCKET): vol.Any(None, str),
            vol.Optional(CONF_DEVICE_NAME): vol.Any(None, str),
            vol.Optional(CONF_DEVICE_MANUFACTURER): vol.Any(None, str),
            vol.Optional(CONF_DEVICE_MODEL): vol.Any(None, str),
            vol.Optional(CONF_NAMING_TEMPLATE): vol.Any(None, str),
            vol.Optional(CONF_DEBUG_SWITCH_ENTITY_ID): vol.Any(
                None,
                selector.EntitySelector(selector.EntitySelectorConfig(domain="input_boolean")),
            ),
            vol.Optional(CONF_NOTIFY_ENTITY_ID): vol.Any(
                None,
                selector.EntitySelector(selector.EntitySelectorConfig(domain="notify")),
            ),
        },
        extra=vol.PREVENT_EXTRA,
    )
