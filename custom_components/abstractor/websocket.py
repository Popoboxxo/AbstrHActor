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

from custom_components.abstractor.config_flow import (
    _build_new_subentry_data,
    _device_group_id_for_device,
    _normalize_subentry_data,
)
from custom_components.abstractor.const import (
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    CONF_TARGET_DEVICE_ID,
    DOMAIN,
    SUBENTRY_TYPE_SENSOR,
    WS_GET_SUBENTRIES,
    WS_SUBSCRIBE_SUBENTRIES,
    WS_YAML_SCAN,
)
from custom_components.abstractor.specs import SPEC_REGISTRY

_LOGGER = logging.getLogger(__name__)


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


def _async_root_entry(hass: HomeAssistant):
    return next(
        (
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.unique_id == "abstractor_root"
        ),
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
                "source_entity_ids": data.get(CONF_SOURCE_ENTITY_IDS)
                or [data.get(CONF_SOURCE_ENTITY_ID)],
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
    if not _require_admin(connection, msg):
        return
    connection.send_result(msg["id"], {"subentries": _build_subentries(hass)})


@websocket_api.websocket_command({vol.Required("type"): WS_SUBSCRIBE_SUBENTRIES})
@websocket_api.async_response
async def ws_subentries_subscribe(hass, connection, msg) -> None:
    """Push the subentry list on every coordinator update.

    Read-only and admin-gated like the one-shot ``abstractor/subentries``. The
    coordinator is reused across config-entry reloads (see ``__init__.py``), so
    this listener survives the reload that every subentry add/remove triggers
    and a write is reflected without the panel polling.
    """
    if not _require_admin(connection, msg):
        return
    coordinator = hass.data.get(DOMAIN, {}).get("coordinator")

    @callback
    def _forward() -> None:
        connection.send_event(msg["id"], {"subentries": _build_subentries(hass)})

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
        if spec is None or not spec.enabled or spec.platform not in {"sensor", "binary_sensor"}:
            connection.send_error(msg["id"], "invalid", f"Unsupported device_type: {requested_type}")
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
    {vol.Required("type"): "abstractor/subentry/update", vol.Required("subentry_id"): str, vol.Required("data"): dict}
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
            root_entry, msg["subentry_id"], data=normalized, title=root_entry.subentries[msg["subentry_id"]].title
        )
    except Exception as exc:  # noqa: BLE001
        connection.send_error(msg["id"], "internal_error", str(exc))
        return
    connection.send_result(msg["id"], {"updated": True})


@websocket_api.websocket_command(
    {vol.Required("type"): "abstractor/subentry/delete", vol.Required("subentry_id"): str}
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


@websocket_api.websocket_command(
    {vol.Required("type"): "abstractor/options/update", vol.Required("options"): dict}
)
@websocket_api.async_response
async def ws_options_update(hass, connection, msg) -> None:
    if not _require_admin(connection, msg):
        return
    root_entry = _async_root_entry(hass)
    if root_entry is None:
        connection.send_error(msg["id"], "not_found", "Abstractor root entry not found")
        return
    hass.config_entries.async_update_entry(root_entry, options=dict(msg["options"]))
    hass.async_create_task(hass.config_entries.async_reload(root_entry.entry_id))
    connection.send_result(msg["id"], {"updated": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "abstractor/logical_rename",
        vol.Required("subentry_id"): str,
        vol.Required("logical_name"): str,
        vol.Optional("object_id"): str,
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
        sid for sid, s in root_entry.subentries.items()
        if (group_id and s.data.get(CONF_DEVICE_GROUP_ID) == group_id) or (sid == msg["subentry_id"])
    ]
    # If there is no group id, only the current subentry.
    if not group_id:
        targets = [msg["subentry_id"]]
    for sid in targets:
        sub = root_entry.subentries[sid]
        merged = dict(sub.data)
        merged["logical_name"] = logical_name
        if object_id:
            merged["object_id"] = object_id
        hass.config_entries.async_update_subentry(root_entry, sid, data=merged, title=sub.title)
    # Optional entity registry rename.
    if msg.get("rename_entity") and object_id:
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, sub.unique_id) if sub.unique_id else None
        # Try also other platforms by scanning registry entries.
        if entity_id is None:
            for ent in er.async_entries_for_config_entry(registry, root_entry.entry_id):
                if ent.config_subentry_id == msg["subentry_id"]:
                    entity_id = ent.entity_id
        if entity_id is not None:
            new_entity_id = f"sensor.{object_id}"
            try:
                registry.async_update_entity(entity_id, new_entity_id=new_entity_id)
            except Exception as exc:  # noqa: BLE001
                connection.send_error(msg["id"], "invalid", str(exc))
                return
    connection.send_result(msg["id"], {"renamed": True, "group_size": len(targets)})


@websocket_api.websocket_command({vol.Required("type"): WS_YAML_SCAN})
@websocket_api.async_response
async def ws_yaml_scan(hass, connection, msg) -> None:
    """Read-only placeholder scan result for the Migrate tab."""
    connection.send_result(msg["id"], {"sensors": []})


def async_register_websocket(hass: HomeAssistant) -> None:
    # Write commands are authorized solely by the per-command ``_require_admin``
    # gate; there is intentionally no separate edit-mode session token.
    websocket_api.async_register_command(hass, ws_get_subentries)
    websocket_api.async_register_command(hass, ws_subentries_subscribe)
    websocket_api.async_register_command(hass, ws_subentry_create)
    websocket_api.async_register_command(hass, ws_subentry_update)
    websocket_api.async_register_command(hass, ws_subentry_delete)
    websocket_api.async_register_command(hass, ws_options_update)
    websocket_api.async_register_command(hass, ws_logical_rename)
    websocket_api.async_register_command(hass, ws_yaml_scan)
