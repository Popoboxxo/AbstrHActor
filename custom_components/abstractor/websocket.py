"""Websocket API for the Abstractor sidebar panel (Phase UI-1/2)."""

from __future__ import annotations

import logging
import re
import uuid
from types import MappingProxyType

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.abstractor.config_flow import (
    _build_new_subentry_data,
    _device_group_id_for_device,
    _normalize_subentry_data,
)
from custom_components.abstractor.const import (
    AGGREGATION_MODES,
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_TYPE,
    CONF_ENTITY_NAME,
    CONF_INFLUX_TOKEN,
    CONF_LEGACY_UNIQUE_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    CONF_TARGET_DEVICE_ID,
    DOMAIN,
    ROOT_UNIQUE_ID,
    SUBENTRY_TYPE_SENSOR,
    WS_GET_SUBENTRIES,
    WS_OPTIONS_READ,
    WS_SUBSCRIBE_SUBENTRIES,
    WS_YAML_SCAN,
)
from custom_components.abstractor.schema import (
    build_options_validator,
    build_subentry_validator,
)
from custom_components.abstractor.specs import SPEC_REGISTRY
from custom_components.abstractor.yaml_scan import scan_config_dir

_LOGGER = logging.getLogger(__name__)

# WS-1 task 1.4 (plan): classification of every registered websocket command.
# Read paths feed the panel; write paths mutate config entries. The table is
# asserted to match ``async_register_websocket`` registrations (no drift) and
# drives future gate/redaction decisions (WS-3) from one source of truth.
WS_COMMAND_TABLE: dict[str, str] = {
    "ws_get_subentries": "read",
    "ws_subentries_subscribe": "subscribe",
    "ws_yaml_scan": "read",
    "ws_get_types": "read",
    "ws_options_read": "read",
    "ws_subentry_create": "write",
    "ws_subentry_update": "write",
    "ws_subentry_delete": "write",
    "ws_options_update": "write",
    "ws_logical_rename": "write",
}
WS_ERROR_SCHEMA = "schema_violation"


def _validate_device_mapping(hass, user_input, current_data=None):
    """Read-only pre-check of a submitted device-mapping intent.

    Validates only the *intent* carried by ``CONF_TARGET_DEVICE_ID`` /
    ``CONF_CREATE_NEW_DEVICE``: it performs NO registry mutation and never
    swallows a failure into a silent pass. The config flow's own
    ``_validate_device_mapping`` stays the authoritative check and owns the
    ordered registry transaction; this WS pre-check merely rejects a target
    device that cannot be resolved to this integration's ``(DOMAIN, X)``
    identifier before any subentry write happens.
    """
    target_device_id = user_input.get(CONF_TARGET_DEVICE_ID)
    if not target_device_id:
        # Neither mapping control touched, or an explicit detach (no target):
        # both are safe intents and need no registry lookup.
        return {}
    if _device_group_id_for_device(hass, target_device_id) is None:
        return {"base": "device_mapping_conflict"}
    return {}


def _require_admin(connection, msg) -> bool:
    user = getattr(connection, "user", None)
    if bool(getattr(user, "is_admin", False)):
        return True
    connection.send_error(msg["id"], "not_allowed", "Admin privileges required")
    return False


def _is_admin(connection) -> bool:
    """Gate-free admin check for read-path DECISIONS (no error side effect)."""
    return bool(getattr(getattr(connection, "user", None), "is_admin", False))


# WS-3 read redaction: identity material that only matters for the admin
# edit/migration paths must not leak to ordinary users (decision D-5); the
# panel renders them as empty. Write gates still use ``_require_admin``.
READ_REDACTED_KEYS = ("legacy_unique_id", "device_group_id")


def _redact_rows(rows: list[dict], admin: bool) -> list[dict]:
    if admin:
        return rows
    return [{k: (None if k in READ_REDACTED_KEYS else v) for k, v in row.items()} for row in rows]


def _async_root_entry(hass: HomeAssistant):
    return next(
        (entry for entry in hass.config_entries.async_entries(DOMAIN) if entry.unique_id == ROOT_UNIQUE_ID),
        None,
    )


def _meta_payload(coordinator, subentry_id: str):
    if coordinator is None:
        return None
    meta = getattr(coordinator, "meta", None)
    if not isinstance(meta, dict):
        return None
    item = meta.get(subentry_id)
    if item is None:
        return None
    return {
        "last_event": item.last_event,
        "event_at": item.event_at.isoformat() if item.event_at is not None else None,
        "spike_rejections": item.spike_rejections,
        "fallbacks": item.fallbacks,
        "unavailable_samples": item.unavailable_samples,
        "source_states": item.source_states,
        "stale": item.stale,
    }


def _build_subentries(hass):
    """Build the subentry list payload shared by the read API and subscription."""
    root_entry = _async_root_entry(hass)
    if root_entry is None:
        return []
    coordinator = hass.data.get(DOMAIN, {}).get("coordinator")
    out = []
    for subentry_id, subentry in root_entry.subentries.items():
        data = dict(subentry.data)
        value = None
        last_event = None
        if coordinator is not None:
            coordinator_data = getattr(coordinator, "data", None)
            value = coordinator_data.get(subentry_id) if coordinator_data else None
            pipelines = getattr(coordinator, "pipelines", {}) or {}
            pipeline = pipelines.get(subentry_id)
            last_event = pipeline.last_event if pipeline is not None else None
        health = "idle"
        if coordinator is not None and not getattr(coordinator, "last_update_success", True):
            health = "bad"
        elif value is None:
            health = "idle"
        elif last_event:
            health = "warn"
        else:
            health = "ok"
        out.append(
            {
                "subentry_id": subentry_id,
                "title": subentry.title,
                "unique_id": subentry.unique_id,
                "device_type": data.get(CONF_DEVICE_TYPE, "power"),
                "logical_name": data.get("logical_name"),
                "object_id": data.get("object_id"),
                "source_entity_ids": data.get(CONF_SOURCE_ENTITY_IDS) or [data.get(CONF_SOURCE_ENTITY_ID)],
                "legacy_unique_id": data.get(CONF_LEGACY_UNIQUE_ID),
                "device_group_id": data.get(CONF_DEVICE_GROUP_ID),
                "value": value,
                "last_event": last_event,
                "health": health,
                "meta": _meta_payload(coordinator, subentry_id),
            }
        )
    return out


@websocket_api.websocket_command({vol.Required("type"): WS_GET_SUBENTRIES})
@websocket_api.async_response
async def ws_get_subentries(hass, connection, msg) -> None:
    """One-shot read of the subentry list (WS-3: visible to every user).

    UF-04: the admin gate made the panel render an empty surface for
    ordinary users. Read paths are now open; identity keys are redacted
    server-side for non-admins (single source of truth, decision D-5).
    """
    connection.send_result(msg["id"], {"subentries": _redact_rows(_build_subentries(hass), _is_admin(connection))})


@websocket_api.websocket_command({vol.Required("type"): WS_SUBSCRIBE_SUBENTRIES})
@websocket_api.async_response
async def ws_subentries_subscribe(hass, connection, msg) -> None:
    """Push the subentry list on every coordinator update.

    Read-only and open to every user like the one-shot
    ``abstractor/subentries`` (WS-3); non-admins get the same redacted rows.
    The coordinator is reused across config-entry reloads (see ``__init__.py``),
    so this listener survives the reload that every subentry add/remove triggers
    and a write is reflected without the panel polling.
    """
    admin = _is_admin(connection)
    coordinator = hass.data.get(DOMAIN, {}).get("coordinator")

    @callback
    def _forward() -> None:
        connection.send_event(msg["id"], {"subentries": _redact_rows(_build_subentries(hass), admin)})

    if coordinator is not None:
        connection.subscriptions[msg["id"]] = coordinator.async_add_listener(_forward)
    else:
        connection.subscriptions[msg["id"]] = lambda: None
    connection.send_result(msg["id"])
    # Push the current snapshot immediately: subscribeMessage only delivers
    # events (not the result payload), so without this the panel would stay
    # empty until the next coordinator update.
    _forward()


@websocket_api.websocket_command({vol.Required("type"): "abstractor/subentry/create", vol.Required("data"): dict})
@websocket_api.async_response
async def ws_subentry_create(hass, connection, msg) -> None:
    if not _require_admin(connection, msg):
        return
    root_entry = _async_root_entry(hass)
    if root_entry is None:
        connection.send_error(msg["id"], "not_found", "Abstractor root entry not found")
        return
    data = dict(msg["data"])
    sources = data.get(CONF_SOURCE_ENTITY_IDS) or [data.get(CONF_SOURCE_ENTITY_ID)]
    sources = [s for s in sources if s]
    if not sources:
        connection.send_error(msg["id"], "invalid", "At least one source entity is required")
        return
    requested_type = data.get(CONF_DEVICE_TYPE)
    if requested_type is not None:
        spec = SPEC_REGISTRY.try_get(requested_type)
        if (
            spec is None
            or not spec.enabled
            or spec.platform not in {"sensor", "binary_sensor", "switch", "light", "cover"}
        ):
            connection.send_error(msg["id"], "invalid", f"Unsupported device_type: {requested_type}")
            return
    try:
        data = build_subentry_validator(requested_type)(data)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.error("Abstractor WS create schema violation: %s", exc)
        connection.send_error(msg["id"], WS_ERROR_SCHEMA, str(exc))
        return
    try:
        errors = _validate_device_mapping(hass, data)
    except Exception as exc:  # noqa: BLE001
        connection.send_error(msg["id"], "invalid", str(exc))
        return
    if errors:
        connection.send_error(msg["id"], "invalid", str(errors))
        return
    try:
        built = _build_new_subentry_data(hass, data, sources)
    except Exception as exc:  # noqa: BLE001
        connection.send_error(msg["id"], "invalid", str(exc))
        return
    subentry_id = f"{uuid.uuid4().hex[:24]}"
    device_type = built.get(CONF_DEVICE_TYPE, "power")
    subentry = ConfigSubentry(
        data=MappingProxyType(built),
        subentry_id=subentry_id,
        subentry_type=SUBENTRY_TYPE_SENSOR,
        title=f"Abstract {device_type}",
        unique_id=built.get(CONF_LEGACY_UNIQUE_ID),
    )
    try:
        hass.config_entries.async_add_subentry(root_entry, subentry)
    except Exception as exc:  # noqa: BLE001
        connection.send_error(msg["id"], "internal_error", str(exc))
        return
    connection.send_result(msg["id"], {"created": True, "subentry_id": subentry_id})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "abstractor/subentry/update",
        vol.Required("subentry_id"): str,
        vol.Required("data"): dict,
    }
)
@websocket_api.async_response
async def ws_subentry_update(hass, connection, msg) -> None:
    if not _require_admin(connection, msg):
        return
    root_entry = _async_root_entry(hass)
    if root_entry is None or msg["subentry_id"] not in root_entry.subentries:
        connection.send_error(msg["id"], "not_found", "Abstractor subentry not found")
        return
    data = dict(msg["data"])
    sources = data.get(CONF_SOURCE_ENTITY_IDS) or [data.get(CONF_SOURCE_ENTITY_ID)]
    sources = [s for s in sources if s]
    if not sources:
        current = root_entry.subentries[msg["subentry_id"]].data
        sources = current.get(CONF_SOURCE_ENTITY_IDS) or [current.get(CONF_SOURCE_ENTITY_ID)]
        sources = [s for s in sources if s]
    if not sources:
        connection.send_error(msg["id"], "invalid", "At least one source entity is required")
        return
    current = dict(root_entry.subentries[msg["subentry_id"]].data)
    target_type = data.get(CONF_DEVICE_TYPE) or current.get(CONF_DEVICE_TYPE, "power")
    try:
        data = build_subentry_validator(target_type, allow_legacy_unique_id=False)(data)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.error("Abstractor WS update schema violation: %s", exc)
        connection.send_error(msg["id"], WS_ERROR_SCHEMA, str(exc))
        return
    merged = dict(current)
    merged.update(data)
    merged[CONF_SOURCE_ENTITY_IDS] = sources
    try:
        errors = _validate_device_mapping(hass, merged, current)
    except Exception as exc:  # noqa: BLE001
        connection.send_error(msg["id"], "invalid", str(exc))
        return
    if errors:
        connection.send_error(msg["id"], "invalid", str(errors))
        return
    normalized = _normalize_subentry_data(hass, merged, sources, current)
    try:
        hass.config_entries.async_update_subentry(
            root_entry,
            msg["subentry_id"],
            data=normalized,
            title=root_entry.subentries[msg["subentry_id"]].title,
        )
    except Exception as exc:  # noqa: BLE001
        connection.send_error(msg["id"], "internal_error", str(exc))
        return
    connection.send_result(msg["id"], {"updated": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "abstractor/subentry/delete",
        vol.Required("subentry_id"): str,
    }
)
@websocket_api.async_response
async def ws_subentry_delete(hass, connection, msg) -> None:
    if not _require_admin(connection, msg):
        return
    root_entry = _async_root_entry(hass)
    if root_entry is None or msg["subentry_id"] not in root_entry.subentries:
        connection.send_error(msg["id"], "not_found", "Abstractor subentry not found")
        return
    try:
        hass.config_entries.async_remove_subentry(root_entry, msg["subentry_id"])
    except Exception as exc:  # noqa: BLE001
        connection.send_error(msg["id"], "internal_error", str(exc))
        return
    connection.send_result(msg["id"], {"deleted": True})


@websocket_api.websocket_command({vol.Required("type"): "abstractor/options/update", vol.Required("options"): dict})
@websocket_api.async_response
async def ws_options_update(hass, connection, msg) -> None:
    if not _require_admin(connection, msg):
        return
    root_entry = _async_root_entry(hass)
    if root_entry is None:
        connection.send_error(msg["id"], "not_found", "Abstractor root entry not found")
        return
    try:
        validated = build_options_validator()(dict(msg["options"]))
    except Exception as exc:  # noqa: BLE001
        _LOGGER.error("Abstractor WS options schema violation: %s", exc)
        connection.send_error(msg["id"], WS_ERROR_SCHEMA, str(exc))
        return
    current_options = dict(getattr(root_entry, "options", None) or {})
    merged_options = {**current_options, **validated}
    hass.config_entries.async_update_entry(root_entry, options=merged_options)
    hass.async_create_task(hass.config_entries.async_reload(root_entry.entry_id))
    connection.send_result(msg["id"], {"updated": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "abstractor/logical_rename",
        vol.Required("subentry_id"): str,
        vol.Required("logical_name"): str,
        vol.Optional("object_id"): str,
        vol.Optional(CONF_ENTITY_NAME): vol.Any(None, str),
        vol.Optional("rename_entity", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_logical_rename(hass, connection, msg) -> None:
    if not _require_admin(connection, msg):
        return
    root_entry = _async_root_entry(hass)
    if root_entry is None or msg["subentry_id"] not in root_entry.subentries:
        connection.send_error(msg["id"], "not_found", "Abstractor subentry not found")
        return
    subentry = root_entry.subentries[msg["subentry_id"]]
    current = dict(subentry.data)
    logical_name = str(msg["logical_name"]).strip()
    if not logical_name:
        connection.send_error(msg["id"], "invalid", "logical_name is required")
        return
    object_id = msg.get("object_id")
    if object_id and not re.fullmatch(r"[a-z0-9_]+", object_id):
        connection.send_error(msg["id"], "invalid", "object_id must be a slug")
        return
    # Group members sharing the same device_group_id (or the singleton) move
    # together, as decided in the plan.
    group_id = current.get(CONF_DEVICE_GROUP_ID)
    targets = [
        sid
        for sid, s in root_entry.subentries.items()
        if (group_id and s.data.get(CONF_DEVICE_GROUP_ID) == group_id) or (sid == msg["subentry_id"])
    ]
    # If there is no group id, only the current subentry.
    if not group_id:
        targets = [msg["subentry_id"]]
    entity_name = msg.get(CONF_ENTITY_NAME)
    if entity_name is not None:
        entity_name = str(entity_name).strip() or None
    for sid in targets:
        sub = root_entry.subentries[sid]
        merged = dict(sub.data)
        merged["logical_name"] = logical_name
        if object_id:
            merged["object_id"] = object_id
        if CONF_ENTITY_NAME in msg:
            if entity_name:
                merged[CONF_ENTITY_NAME] = entity_name
            else:
                merged.pop(CONF_ENTITY_NAME, None)
        hass.config_entries.async_update_subentry(root_entry, sid, data=merged, title=sub.title)
    # Optional entity registry rename for THIS subentry's entity. The domain
    # is taken from the existing entity_id so a binary_sensor is renamed to
    # binary_sensor.* rather than being forced onto sensor.*, and the entity is
    # looked up by this subentry (not by whatever `sub` the loop last held).
    if msg.get("rename_entity") and object_id:
        registry = er.async_get(hass)
        entity_id = None
        for ent in er.async_entries_for_config_entry(registry, root_entry.entry_id):
            if ent.config_subentry_id == msg["subentry_id"]:
                entity_id = ent.entity_id
                break
        if entity_id is None and subentry.unique_id:
            for platform in ("sensor", "binary_sensor"):
                entity_id = registry.async_get_entity_id(platform, DOMAIN, subentry.unique_id)
                if entity_id:
                    break
        if entity_id is not None:
            domain = entity_id.split(".", 1)[0]
            try:
                registry.async_update_entity(entity_id, new_entity_id=f"{domain}.{object_id}")
            except Exception as exc:  # noqa: BLE001
                connection.send_error(msg["id"], "invalid", str(exc))
                return
    connection.send_result(msg["id"], {"renamed": True, "group_size": len(targets)})


@websocket_api.websocket_command({vol.Required("type"): WS_YAML_SCAN})
@websocket_api.async_response
async def ws_yaml_scan(hass, connection, msg) -> None:
    """Read-only scan of hand-written ``template:`` sensor packages (UF-05).

    Scans the config root's top-level ``*.yaml`` files (never ``data/`` or
    secret files) and reports migration-candidate rows for the Migrate tab.
    Open to every user like the other read paths; it exposes only config the
    user can already see.
    """
    try:
        rows, scanned = scan_config_dir(str(hass.config_dir))
    except OSError as exc:
        _LOGGER.error("Abstractor YAML scan failed: %s", exc)
        connection.send_error(msg["id"], "invalid", f"YAML scan failed: {exc}")
        return
    connection.send_result(
        msg["id"],
        {
            "sensors": rows,
            "scanned_paths": scanned,
            "scanned_at": dt_util.utcnow().isoformat(),
        },
    )


@websocket_api.websocket_command({vol.Required("type"): "abstractor/types"})
@websocket_api.async_response
async def ws_get_types(hass, connection, msg) -> None:
    """Serve the shipped type catalogue (WS-2: one source of truth for the
    panel — the JS must not hardcode a list that can drift from this)."""
    connection.send_result(msg["id"], _build_type_catalogue())


@websocket_api.websocket_command({vol.Required("type"): WS_OPTIONS_READ})
@websocket_api.async_response
async def ws_options_read(hass, connection, msg) -> None:
    """Read the root entry's options (WS-3: open read with credential redaction).

    The Settings tab must show the current poll interval etc. without an
    admin round-trip (UF-04 family). Exporter credentials (``influx_token``)
    are only visible to admins — a user may never read back their own secret.
    """
    root_entry = _async_root_entry(hass)
    if root_entry is None:
        connection.send_error(msg["id"], "not_found", "Abstractor root entry not found")
        return
    options = dict(getattr(root_entry, "options", None) or {})
    if not _is_admin(connection):
        options.pop(CONF_INFLUX_TOKEN, None)
    connection.send_result(msg["id"], {"options": options})


def _build_type_catalogue() -> dict:
    """Derive the panel catalogue from ``SPEC_REGISTRY`` (shipped platforms)."""
    shipped = [
        spec
        for spec in SPEC_REGISTRY.enabled()
        if spec.platform in ("sensor", "binary_sensor", "switch", "light", "cover")
    ]
    return {
        "device_types": [spec.type_key for spec in shipped],
        "numeric_types": [spec.type_key for spec in shipped if spec.numeric],
        "aggregation_modes": list(AGGREGATION_MODES),
        "display_names": {spec.type_key: spec.display_name for spec in shipped},
    }


def async_register_websocket(hass: HomeAssistant) -> None:
    """Register every websocket command, cross-checked against the table.

    Write commands are authorized solely by the per-command ``_require_admin``
    gate; there is intentionally no separate edit-mode session token. The
    ``WS_COMMAND_TABLE`` classification is asserted against the actual
    registrations so a new command cannot silently miss its gate/redaction
    classification (WS-3 builds on that table).
    """
    commands = (
        ws_get_subentries,
        ws_subentries_subscribe,
        ws_yaml_scan,
        ws_get_types,
        ws_subentry_create,
        ws_subentry_update,
        ws_subentry_delete,
        ws_options_update,
        ws_logical_rename,
        ws_options_read,
    )
    registered = {fn.__name__ for fn in commands}
    if registered != set(WS_COMMAND_TABLE):
        _LOGGER.error(
            "Abstractor WS command table drift: %s",
            sorted(registered ^ set(WS_COMMAND_TABLE)),
        )
        raise ValueError("Abstractor websocket command table drift")
    for fn in commands:
        websocket_api.async_register_command(hass, fn)
