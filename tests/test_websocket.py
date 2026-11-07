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
    assert "ws_subentries_subscribe" in calls
    assert "ws_subentry_create" in calls
    assert "ws_subentry_update" in calls
    assert "ws_subentry_delete" in calls
    # The decorative edit-mode token was removed; write commands are gated by
    # _require_admin instead.
    assert "ws_mode_token" not in calls


async def test_ws_get_subentries_empty_when_no_root() -> None:
    hass = _hass()
    connection = SimpleNamespace(user=SimpleNamespace(is_admin=True), send_result=Mock(), send_error=Mock())
    # __wrapped__ bypasses the async_response scheduler decorator, which needs a
    # real hass to create a background task.
    await websocket.ws_get_subentries.__wrapped__(hass, connection, {"id": 42})
    connection.send_result.assert_called_once_with(42, {"subentries": []})


async def test_ws_get_subentries_nonadmin_reads_redacted_rows() -> None:
    """WS-3: read path open to every user; identity keys redacted (D-5)."""
    root = _root(
        {
            "sub-1": SimpleNamespace(
                data={
                    "device_type": "power",
                    "source_entity_id": "sensor.x",
                    "legacy_unique_id": "legacy-hyper",
                    "device_group_id": "hyper2000_eg",
                },
                title="t",
                unique_id="u",
            )
        }
    )
    hass = _hass_cfg(root)
    connection = _readonly_connection()
    await websocket.ws_get_subentries.__wrapped__(hass, connection, {"id": 6})
    connection.send_error.assert_not_called()
    rows = connection.send_result.call_args.args[1]["subentries"]
    assert len(rows) == 1
    assert rows[0]["legacy_unique_id"] is None
    assert rows[0]["device_group_id"] is None
    assert rows[0]["subentry_id"] == "sub-1"


# --- write commands (M7) --------------------------------------------------


def _admin_connection():
    return SimpleNamespace(user=SimpleNamespace(is_admin=True), send_result=Mock(), send_error=Mock())


def _readonly_connection():
    """Ordinary user connection: read paths must work, writes must not."""
    return SimpleNamespace(user=SimpleNamespace(is_admin=False), send_result=Mock(), send_error=Mock())


def _root(subentries=None, entry_id="root-1", options=None):
    return SimpleNamespace(
        entry_id=entry_id,
        unique_id="abstractor_root",
        subentries=dict(subentries or {}),
        options=dict(options or {}),
    )


def _hass_cfg(root_entry, coordinator=None):
    entries = [root_entry] if root_entry is not None else []
    return SimpleNamespace(
        data=({"abstractor": {"coordinator": coordinator}} if coordinator is not None else {}),
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


async def test_ws_subentries_subscribe_registers_and_forwards() -> None:
    root = _root(
        {
            "sub-1": SimpleNamespace(
                data={"device_type": "power", "source_entity_id": "sensor.x"},
                title="t",
                unique_id="u",
            )
        }
    )
    unsub = Mock()
    coordinator = SimpleNamespace(
        data={},
        pipelines={},
        last_update_success=True,
        async_add_listener=Mock(return_value=unsub),
    )
    hass = _hass_cfg(root, coordinator=coordinator)
    connection = _admin_connection()
    connection.subscriptions = {}
    connection.send_event = Mock()

    await websocket.ws_subentries_subscribe.__wrapped__(hass, connection, {"id": 20})

    assert connection.subscriptions[20] is unsub
    assert connection.send_result.call_args.args[0] == 20
    # The handler pushes the current snapshot immediately ...
    assert connection.send_event.call_count == 1
    assert "subentries" in connection.send_event.call_args.args[1]
    # ... and again on every coordinator update via the registered listener.
    listener = coordinator.async_add_listener.call_args.args[0]
    listener()
    assert connection.send_event.call_count == 2
    assert connection.send_event.call_args.args[0] == 20


async def test_ws_subentries_subscribe_opens_read_for_nonadmin() -> None:
    """WS-3: the subscription listener is a read path — open, not rejected."""
    hass = _hass_cfg(_root())
    connection = SimpleNamespace(
        user=SimpleNamespace(is_admin=False),
        send_result=Mock(),
        send_error=Mock(),
        send_event=Mock(),
        subscriptions={},
    )
    await websocket.ws_subentries_subscribe.__wrapped__(hass, connection, {"id": 21})
    connection.send_error.assert_not_called()
    connection.send_result.assert_called_once_with(21)
    # Immediate snapshot push (subscribeMessage only delivers events).
    connection.send_event.assert_called_once()
    event_payload = connection.send_event.call_args.args[1]
    assert event_payload["subentries"] == []


def test_validate_device_mapping_is_read_only(monkeypatch) -> None:
    hass = _hass_cfg(_root())
    # No mapping intent -> nothing to validate, no registry access.
    assert websocket._validate_device_mapping(hass, {}) == {}

    monkeypatch.setattr(websocket, "_device_group_id_for_device", lambda _hass, _dev: None)
    assert websocket._validate_device_mapping(hass, {"target_device_id": "dev-1"}) == {
        "base": "device_mapping_conflict"
    }

    monkeypatch.setattr(websocket, "_device_group_id_for_device", lambda _hass, _dev: "group-1")
    assert websocket._validate_device_mapping(hass, {"target_device_id": "dev-1"}) == {}


async def test_ws_subentry_create_requires_admin() -> None:
    hass = _hass_cfg(_root())
    connection = SimpleNamespace(user=SimpleNamespace(is_admin=False), send_result=Mock(), send_error=Mock())
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
    monkeypatch.setattr(websocket, "ConfigSubentry", lambda **kwargs: SimpleNamespace(**kwargs))
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
    await websocket.ws_subentry_delete.__wrapped__(hass, connection, {"id": 5, "subentry_id": "sub-1"})
    hass.config_entries.async_remove_subentry.assert_called_once()
    connection.send_result.assert_called_once_with(5, {"deleted": True})


async def test_ws_subentry_update_not_found() -> None:
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    await websocket.ws_subentry_update.__wrapped__(hass, connection, {"id": 6, "subentry_id": "missing", "data": {}})
    connection.send_error.assert_called_once()
    hass.config_entries.async_update_subentry.assert_not_called()


async def test_ws_options_update_reloads_root_entry() -> None:
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    await websocket.ws_options_update.__wrapped__(hass, connection, {"id": 7, "options": {"poll_interval": 30}})
    hass.config_entries.async_update_entry.assert_called_once()
    hass.async_create_task.assert_called_once()
    connection.send_result.assert_called_once_with(7, {"updated": True})


async def test_ws_get_types_matches_registry_catalogue() -> None:
    """The panel catalogue is derived from SPEC_REGISTRY (WS-2, no JS drift)."""
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    await websocket.ws_get_types.__wrapped__(hass, connection, {"id": 20})
    connection.send_error.assert_not_called()
    payload = connection.send_result.call_args.args[1]
    shipped = [
        spec
        for spec in websocket.SPEC_REGISTRY.enabled()
        if spec.platform in ("sensor", "binary_sensor", "switch", "light", "cover")
    ]
    assert payload["device_types"] == [spec.type_key for spec in shipped]
    assert payload["numeric_types"] == [spec.type_key for spec in shipped if spec.numeric]
    assert "riemann_energy" not in payload["device_types"]
    assert payload["display_names"]["cover_position"] == "Cover position"


async def test_ws_logical_rename_sets_entity_name() -> None:
    """The rename command carries the entity_name override (UF-08 affordance)."""
    root = _root(
        {
            "sub-1": SimpleNamespace(
                data={"device_type": "power", "source_entity_id": "sensor.x"}, title="t", unique_id="u"
            )
        }
    )
    hass = _hass_cfg(root)
    connection = _admin_connection()
    await websocket.ws_logical_rename.__wrapped__(
        hass,
        connection,
        {
            "id": 21,
            "subentry_id": "sub-1",
            "logical_name": "Kitchen",
            "entity_name": "Power usage",
        },
    )
    hass.config_entries.async_update_subentry.assert_called_once()
    persisted = hass.config_entries.async_update_subentry.call_args.kwargs["data"]
    assert persisted["entity_name"] == "Power usage"
    assert persisted["logical_name"] == "Kitchen"
    assert connection.send_result.call_args.args[1] == {"renamed": True, "group_size": 1}


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


async def test_ws_logical_rename_renames_entity_keeping_platform(monkeypatch) -> None:
    """The entity rename must keep the entity's own platform domain, so a
    binary_sensor is renamed to binary_sensor.* not sensor.*."""
    root = _root({"sub-1": SimpleNamespace(data={}, title="t", unique_id="uid-1")})
    hass = _hass_cfg(root)
    connection = _admin_connection()

    updated = []
    registry = SimpleNamespace(
        async_entries_for_config_entry=lambda reg, entry_id: [
            SimpleNamespace(entity_id="binary_sensor.front_door", config_subentry_id="sub-1")
        ],
        async_get_entity_id=lambda platform, domain, unique_id: None,
        async_update_entity=lambda entity_id, new_entity_id=None: updated.append((entity_id, new_entity_id)),
    )
    monkeypatch.setattr(
        websocket,
        "er",
        SimpleNamespace(
            async_get=lambda _hass: registry,
            async_entries_for_config_entry=lambda reg, entry_id: reg.async_entries_for_config_entry(reg, entry_id),
        ),
    )

    await websocket.ws_logical_rename.__wrapped__(
        hass,
        connection,
        {
            "id": 11,
            "subentry_id": "sub-1",
            "logical_name": "Door",
            "object_id": "front_door",
            "rename_entity": True,
        },
    )

    assert updated == [("binary_sensor.front_door", "binary_sensor.front_door")]
    connection.send_error.assert_not_called()


async def test_ws_subentry_create_rejects_bad_aggregation() -> None:
    """Shared-schema validation rejects bad pipeline values before any write."""
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    await websocket.ws_subentry_create.__wrapped__(
        hass,
        connection,
        {
            "id": 13,
            "data": {
                "source_entity_id": "sensor.x",
                "device_type": "power",
                "aggregation": "banana",
            },
        },
    )
    connection.send_error.assert_called_once()
    assert connection.send_error.call_args.args[1] == websocket.WS_ERROR_SCHEMA
    hass.config_entries.async_add_subentry.assert_not_called()


async def test_ws_subentry_create_rejects_unknown_key() -> None:
    """Unknown payload keys never reach persisted subentry data (UF-03)."""
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    await websocket.ws_subentry_create.__wrapped__(
        hass,
        connection,
        {"id": 14, "data": {"source_entity_id": "sensor.x", "bogus_key": True}},
    )
    connection.send_error.assert_called_once()
    assert connection.send_error.call_args.args[1] == websocket.WS_ERROR_SCHEMA
    hass.config_entries.async_add_subentry.assert_not_called()


async def test_ws_subentry_update_rejects_legacy_unique_id_change() -> None:
    """The pinned legacy id can be neither changed nor cleared via the WS."""
    root = _root(
        {
            "sub-1": SimpleNamespace(
                data={
                    "device_type": "power",
                    "source_entity_id": "sensor.x",
                    "legacy_unique_id": "pinned-1",
                },
                title="t",
            )
        }
    )
    hass = _hass_cfg(root)
    connection = _admin_connection()
    await websocket.ws_subentry_update.__wrapped__(
        hass,
        connection,
        {
            "id": 15,
            "subentry_id": "sub-1",
            "data": {"legacy_unique_id": "other-1", "source_entity_id": "sensor.x"},
        },
    )
    connection.send_error.assert_called_once()
    assert connection.send_error.call_args.args[1] == websocket.WS_ERROR_SCHEMA
    hass.config_entries.async_update_subentry.assert_not_called()


async def test_ws_options_update_rejects_out_of_range_interval() -> None:
    """Bounds are enforced at the storage boundary, not after the reload."""
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    await websocket.ws_options_update.__wrapped__(hass, connection, {"id": 16, "options": {"poll_interval": 999999}})
    connection.send_error.assert_called_once()
    assert connection.send_error.call_args.args[1] == websocket.WS_ERROR_SCHEMA
    hass.config_entries.async_update_entry.assert_not_called()
    hass.async_create_task.assert_not_called()


async def test_ws_options_update_rejects_unknown_option_key() -> None:
    hass = _hass_cfg(_root())
    connection = _admin_connection()
    await websocket.ws_options_update.__wrapped__(hass, connection, {"id": 17, "options": {"bogus_interval": 3}})
    connection.send_error.assert_called_once()
    assert connection.send_error.call_args.args[1] == websocket.WS_ERROR_SCHEMA
    hass.config_entries.async_update_entry.assert_not_called()


async def test_ws_options_update_merges_current_options() -> None:
    """A partial options payload keeps untouched options instead of wiping them."""
    root = _root(options={"influx_bucket": "keep-me"})
    hass = _hass_cfg(root)
    connection = _admin_connection()
    await websocket.ws_options_update.__wrapped__(hass, connection, {"id": 18, "options": {"poll_interval": 5}})
    hass.config_entries.async_update_entry.assert_called_once()
    persisted = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert persisted == {"influx_bucket": "keep-me", "poll_interval": 5}
    assert connection.send_result.call_args.args[1] == {"updated": True}


def test_ws_command_table_matches_registrations() -> None:
    """No drift: the classification table covers exactly the registered commands."""
    calls = []
    original = websocket.websocket_api.async_register_command

    def capture(hass, handler):
        calls.append(handler.__name__)

    websocket.websocket_api.async_register_command = capture
    try:
        websocket.async_register_websocket(SimpleNamespace())
    finally:
        websocket.websocket_api.async_register_command = original

    assert set(calls) == set(websocket.WS_COMMAND_TABLE)
    writes = {n for n, kind in websocket.WS_COMMAND_TABLE.items() if kind == "write"}
    assert writes == {
        "ws_subentry_create",
        "ws_subentry_update",
        "ws_subentry_delete",
        "ws_options_update",
        "ws_logical_rename",
    }
    assert {n for n, kind in websocket.WS_COMMAND_TABLE.items() if kind == "read"} == {
        "ws_get_subentries",
        "ws_yaml_scan",
        "ws_get_types",
        "ws_options_read",
    }
    assert {n for n, kind in websocket.WS_COMMAND_TABLE.items() if kind == "subscribe"} == {"ws_subentries_subscribe"}


async def test_ws_logical_rename_without_rename_entity_skips_registry(monkeypatch) -> None:
    root = _root({"sub-1": SimpleNamespace(data={}, title="t", unique_id="uid-1")})
    hass = _hass_cfg(root)
    connection = _admin_connection()

    called = []
    monkeypatch.setattr(
        websocket,
        "er",
        SimpleNamespace(async_get=lambda _hass: called.append("get") or SimpleNamespace()),
    )

    await websocket.ws_logical_rename.__wrapped__(
        hass, connection, {"id": 12, "subentry_id": "sub-1", "logical_name": "Kitchen"}
    )

    assert called == []
    assert connection.send_result.call_args.args[1]["renamed"] is True


async def test_ws_yaml_scan_reports_template_rows(tmp_path) -> None:
    """WS-3: the Migrate tab scan is real, not a placeholder."""
    (tmp_path / "templates.yaml").write_text(
        "template:\n"
        "  sensors:\n"
        "    - name: Hyper2000 EG Aktuelle Leistung\n"
        "      unique_id: hyper2000_eg_power_tpl\n"
        "      unit_of_measurement: W\n"
        "      entity_1:\n"
        "        entity_id: sensor.shelly_power\n"
        "        mapping: raw\n"
        "    - name: OG Gesamtverbrauch\n"
        "      entity_1:\n"
        "        entity_id: sensor.wh_meter\n"
        "utility_meter:\n"
        "  source_aux:\n"
        "    - name: Ignored Meter\n"
        "      unique_id: meter_x\n",
        encoding="utf-8",
    )
    hass = _hass_cfg(_root())
    hass.config_dir = str(tmp_path)
    connection = _readonly_connection()
    await websocket.ws_yaml_scan.__wrapped__(hass, connection, {"id": 31})
    payload = connection.send_result.call_args.args[1]
    assert payload["scanned_paths"] == [str(tmp_path / "templates.yaml")]
    rows = payload["sensors"]
    assert len(rows) == 2
    assert rows[0]["unique_id"] == "hyper2000_eg_power_tpl"
    assert rows[0]["history_preservable"] is True
    assert rows[0]["suggested_object_id"] == "abstractor_hyper2000_eg_aktuelle_leistung"
    assert rows[1]["unique_id"] is None
    assert any("unique_id" in blocker for blocker in rows[1]["blockers"])
    assert not any(row["unique_id"] == "meter_x" for row in rows)


async def test_ws_options_read_redacts_token_for_nonadmin() -> None:
    """Settings read is open, but the exporter token stays admin-only."""
    root = _root(options={"poll_interval": 30, "influx_token": "s3cr3t"})
    hass = _hass_cfg(root)
    connection = _readonly_connection()
    await websocket.ws_options_read.__wrapped__(hass, connection, {"id": 32})
    assert connection.send_result.call_args.args[1] == {"options": {"poll_interval": 30}}


async def test_ws_options_read_shows_token_to_admin() -> None:
    root = _root(options={"poll_interval": 30, "influx_token": "s3cr3t"})
    hass = _hass_cfg(root)
    connection = _admin_connection()
    await websocket.ws_options_read.__wrapped__(hass, connection, {"id": 33})
    assert connection.send_result.call_args.args[1] == {"options": {"poll_interval": 30, "influx_token": "s3cr3t"}}


async def test_ws_write_still_rejects_nonadmin_after_read_opening() -> None:
    """WS-3 opened the READ paths; the WRITE gates must not leak with them."""
    root = _root({"sub-1": SimpleNamespace(data={"device_type": "power"}, title="t", unique_id="u")})
    hass = _hass_cfg(root)
    connection = _readonly_connection()
    await websocket.ws_subentry_delete.__wrapped__(hass, connection, {"id": 34, "subentry_id": "sub-1"})
    connection.send_error.assert_called_once()
    hass.config_entries.async_remove_subentry.assert_not_called()
