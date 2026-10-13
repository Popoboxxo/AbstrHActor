"""Tests for the Abstractor websocket API (Phase UI-1)."""

from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.abstractor import websocket


def _hass(root_entry=None):
    return SimpleNamespace(
        data={"coordinator": None},
        config_entries=SimpleNamespace(async_entries=lambda domain: [root_entry] if root_entry else []),
    )


async def test_register_websocket_registers_commands_without_token() -> None:
    calls = []
    original = websocket.websocket_api.async_register_command

    def capture(hass, handler):
        calls.append(handler.__name__)

    websocket.websocket_api.async_register_command = capture
    try:
        websocket.async_register_websocket(SimpleNamespace())
    finally:
        websocket.websocket_api.async_register_command = original

    assert "ws_get_subentries" in calls
    assert "ws_subentry_create" in calls
    assert "ws_subentry_update" in calls
    assert "ws_subentry_delete" in calls
    # The decorative edit-mode token was removed; write commands are gated by
    # _require_admin instead.
    assert "ws_mode_token" not in calls


async def test_ws_get_subentries_empty_when_no_root() -> None:
    hass = _hass()
    connection = SimpleNamespace(
        user=SimpleNamespace(is_admin=True), send_result=Mock(), send_error=Mock()
    )
    # __wrapped__ bypasses the async_response scheduler decorator, which needs a
    # real hass to create a background task.
    await websocket.ws_get_subentries.__wrapped__(hass, connection, {"id": 42})
    connection.send_result.assert_called_once_with(42, {"subentries": []})


async def test_ws_get_subentries_rejects_non_admin() -> None:
    hass = _hass()
    connection = SimpleNamespace(
        user=SimpleNamespace(is_admin=False), send_result=Mock(), send_error=Mock()
    )
    await websocket.ws_get_subentries.__wrapped__(hass, connection, {"id": 5})
    connection.send_error.assert_called_once()
    connection.send_result.assert_not_called()


# --- write commands (M7) --------------------------------------------------


def _admin_connection():
    return SimpleNamespace(
        user=SimpleNamespace(is_admin=True), send_result=Mock(), send_error=Mock()
    )


def _root(subentries=None, entry_id="root-1"):
    return SimpleNamespace(entry_id=entry_id, subentries=dict(subentries or {}))


def _hass_cfg(root_entry, coordinator=None):
    entries = [root_entry] if root_entry is not None else []
    return SimpleNamespace(
        data=(
            {"abstractor": {"coordinator": coordinator}}
            if coordinator is not None
            else {}
        ),
        config_entries=SimpleNamespace(
            async_entries=lambda domain: entries,
            async_add_subentry=Mock(),
            async_update_subentry=Mock(),
            async_remove_subentry=Mock(),
            async_update_entry=Mock(),
            async_reload=Mock(),
        ),
        async_create_task=Mock(),
    )


def test_validate_device_mapping_is_read_only(monkeypatch) -> None:
    hass = _hass_cfg(_root())
    # No mapping intent -> nothing to validate, no registry access.
    assert websocket._validate_device_mapping(hass, {}) == {}

    monkeypatch.setattr(
        websocket, "_device_group_id_for_device", lambda _hass, _dev: None
    )
    assert websocket._validate_device_mapping(
        hass, {"target_device_id": "dev-1"}
    ) == {"base": "device_mapping_conflict"}

    monkeypatch.setattr(
        websocket, "_device_group_id_for_device", lambda _hass, _dev: "group-1"
    )
    assert websocket._validate_device_mapping(hass, {"target_device_id": "dev-1"}) == {}


async def test_ws_subentry_create_requires_admin() -> None:
    hass = _hass_cfg(_root())
    connection = SimpleNamespace(
        user=SimpleNamespace(is_admin=False), send_result=Mock(), send_error=Mock()
    )
    await websocket.ws_subentry_create.__wrapped__(
        hass, connection, {"id": 1, "data": {"source_entity_id": "sensor.x"}}
    )
    connection.send_error.assert_called_once()
    hass.config_entries.async_add_subentry.assert_not_called()


async def test_ws_subentry_create_rejects_unknown_type() -> None:
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    await websocket.ws_subentry_create.__wrapped__(
        hass,
        connection,
        {
            "id": 2,
            "data": {"source_entity_id": "sensor.x", "device_type": "not_a_type"},
        },
    )
    connection.send_error.assert_called_once()
    assert connection.send_error.call_args.args[1] == "invalid"


async def test_ws_subentry_create_requires_source() -> None:
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    await websocket.ws_subentry_create.__wrapped__(hass, connection, {"id": 3, "data": {}})
    connection.send_error.assert_called_once()
    hass.config_entries.async_add_subentry.assert_not_called()


async def test_ws_subentry_create_happy_path(monkeypatch) -> None:
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    monkeypatch.setattr(
        websocket,
        "_build_new_subentry_data",
        lambda _hass, _data, _sources: {
            "device_type": "power",
            "legacy_unique_id": "uid-1",
        },
    )
    monkeypatch.setattr(
        websocket, "ConfigSubentry", lambda **kwargs: SimpleNamespace(**kwargs)
    )
    await websocket.ws_subentry_create.__wrapped__(
        hass, connection, {"id": 4, "data": {"source_entity_id": "sensor.x"}}
    )
    connection.send_error.assert_not_called()
    hass.config_entries.async_add_subentry.assert_called_once()
    assert connection.send_result.call_args.args[1]["created"] is True


async def test_ws_subentry_delete_happy_path() -> None:
    root = _root({"sub-1": SimpleNamespace(data={}, title="t")})
    hass = _hass_cfg(root)
    connection = _admin_connection()
    await websocket.ws_subentry_delete.__wrapped__(
        hass, connection, {"id": 5, "subentry_id": "sub-1"}
    )
    hass.config_entries.async_remove_subentry.assert_called_once()
    connection.send_result.assert_called_once_with(5, {"deleted": True})


async def test_ws_subentry_update_not_found() -> None:
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    await websocket.ws_subentry_update.__wrapped__(
        hass, connection, {"id": 6, "subentry_id": "missing", "data": {}}
    )
    connection.send_error.assert_called_once()
    hass.config_entries.async_update_subentry.assert_not_called()


async def test_ws_options_update_reloads_root_entry() -> None:
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    await websocket.ws_options_update.__wrapped__(
        hass, connection, {"id": 7, "options": {"poll_interval": 30}}
    )
    hass.config_entries.async_update_entry.assert_called_once()
    hass.async_create_task.assert_called_once()
    connection.send_result.assert_called_once_with(7, {"updated": True})


async def test_ws_logical_rename_rejects_bad_slug() -> None:
    root = _root({"sub-1": SimpleNamespace(data={}, title="t", unique_id="u")})
    hass = _hass_cfg(root)
    connection = _admin_connection()
    await websocket.ws_logical_rename.__wrapped__(
        hass,
        connection,
        {
            "id": 8,
            "subentry_id": "sub-1",
            "logical_name": "N",
            "object_id": "Bad Slug",
        },
    )
    connection.send_error.assert_called_once()
    hass.config_entries.async_update_subentry.assert_not_called()


async def test_ws_logical_rename_updates_subentry() -> None:
    root = _root({"sub-1": SimpleNamespace(data={}, title="t", unique_id="u")})
    hass = _hass_cfg(root)
    connection = _admin_connection()
    await websocket.ws_logical_rename.__wrapped__(
        hass, connection, {"id": 9, "subentry_id": "sub-1", "logical_name": "Kitchen"}
    )
    hass.config_entries.async_update_subentry.assert_called_once()
    assert connection.send_result.call_args.args[1]["renamed"] is True
