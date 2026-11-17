"""Test coordinator diagnostics notification behavior."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.abstractor.const import (
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
    CONF_POLL_INTERVAL,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    CONF_UPDATE_MODE,
    DEFAULT_SUBENTRY_POLL_INTERVAL,
    POLL_INTERVAL_MAX,
    POLL_INTERVAL_MIN,
    UPDATE_MODE_EVENT,
    UPDATE_MODE_POLLING,
)
from custom_components.abstractor.coordinator import AbstractorDataUpdateCoordinator


def _coordinator_with_states(states: dict[str, str]) -> AbstractorDataUpdateCoordinator:
    coordinator = object.__new__(AbstractorDataUpdateCoordinator)
    coordinator.hass = SimpleNamespace(
        states=SimpleNamespace(
            get=lambda entity_id: (
                SimpleNamespace(state=states[entity_id])
                if entity_id in states
                else None
            ),
            is_state=lambda entity_id, expected: states.get(entity_id) == expected,
        )
    )
    coordinator.rejected_samples = {}
    coordinator._ring_seq = {}
    coordinator.void_sample_ids = set()
    coordinator.value_history = {}
    return coordinator


def test_fallback_condition_met_without_condition_entity() -> None:
    """A fallback source alone is eligible whenever the primary is unavailable."""
    coordinator = _coordinator_with_states({})

    assert coordinator._fallback_condition_met(
        {CONF_FALLBACK_SOURCE_ENTITY_ID: "sensor.alt"}
    )


def test_fallback_condition_requires_matching_condition_state() -> None:
    """A configured condition entity gates the fallback (REQ-COMP-004)."""
    coordinator = _coordinator_with_states({"binary_sensor.charging": "off"})
    config = {
        CONF_FALLBACK_SOURCE_ENTITY_ID: "sensor.alt",
        CONF_FALLBACK_CONDITION_ENTITY_ID: "binary_sensor.charging",
        CONF_FALLBACK_CONDITION_STATE: "off",
    }

    assert coordinator._fallback_condition_met(config)

    config[CONF_FALLBACK_CONDITION_STATE] = "on"
    assert not coordinator._fallback_condition_met(config)


def test_fallback_condition_false_without_fallback_source() -> None:
    """No fallback source configured means never eligible."""
    coordinator = _coordinator_with_states({})

    assert not coordinator._fallback_condition_met({})


async def test_debug_event_notifies_configured_target_and_deduplicates() -> None:
    """Debug notifications follow the configured options (B7): the entity_id
    of a notify entity is translated to its notify service, notifications are
    only sent while the configured input_boolean is on, and repeats of the
    same event are deduplicated."""
    services = SimpleNamespace(
        has_service=Mock(return_value=True),
        async_call=AsyncMock(),
    )
    states = SimpleNamespace(is_state=Mock(return_value=True))
    coordinator = object.__new__(AbstractorDataUpdateCoordinator)
    coordinator.hass = SimpleNamespace(states=states, services=services)
    coordinator._last_notified_events = {}
    coordinator.debug_switch_entity_id = "input_boolean.automation_debugger"
    coordinator.notify_entity_id = "notify.adminnotificationgroup"

    await coordinator._async_notify_debug("entry-1", "spike rejected")
    await coordinator._async_notify_debug("entry-1", "spike rejected")

    services.async_call.assert_awaited_once_with(
        "notify",
        "adminnotificationgroup",
        {"message": "Abstractor entry-1: spike rejected"},
        blocking=False,
    )
    states.is_state.assert_called_with("input_boolean.automation_debugger", "on")


async def test_debug_event_skipped_silently_when_options_unset() -> None:
    """B7: with no debug entities configured the whole path is a no-op —
    this must hold even on a coordinator built without ever running
    __init__.py's option application (both attributes default to None)."""
    services = SimpleNamespace(
        has_service=Mock(return_value=True),
        async_call=AsyncMock(),
    )
    coordinator = AbstractorDataUpdateCoordinator(Mock())
    coordinator.hass = SimpleNamespace(
        states=SimpleNamespace(is_state=Mock(return_value=True)),
        services=services,
    )

    await coordinator._async_notify_debug("entry-1", "spike rejected")

    services.async_call.assert_not_awaited()


async def test_debug_event_skipped_when_debug_switch_entity_missing() -> None:
    """B7: a configured debug switch that no longer exists (is_state False
    for a missing entity) silently disables notifications, never fails."""
    services = SimpleNamespace(
        has_service=Mock(return_value=True),
        async_call=AsyncMock(),
    )
    states = SimpleNamespace(is_state=Mock(return_value=False))
    coordinator = object.__new__(AbstractorDataUpdateCoordinator)
    coordinator.hass = SimpleNamespace(states=states, services=services)
    coordinator._last_notified_events = {}
    coordinator.debug_switch_entity_id = "input_boolean.gone"
    coordinator.notify_entity_id = "notify.adminnotificationgroup"

    await coordinator._async_notify_debug("entry-1", "spike rejected")

    services.async_call.assert_not_awaited()


async def test_debug_event_skipped_when_notify_service_missing() -> None:
    """B7: a configured notify entity whose service is gone (e.g. the
    integration providing it was removed) is skipped, never fails."""
    services = SimpleNamespace(
        has_service=Mock(return_value=False),
        async_call=AsyncMock(),
    )
    states = SimpleNamespace(is_state=Mock(return_value=True))
    coordinator = object.__new__(AbstractorDataUpdateCoordinator)
    coordinator.hass = SimpleNamespace(states=states, services=services)
    coordinator._last_notified_events = {}
    coordinator.debug_switch_entity_id = "input_boolean.automation_debugger"
    coordinator.notify_entity_id = "notify.gone"

    await coordinator._async_notify_debug("entry-1", "spike rejected")

    services.async_call.assert_not_awaited()


async def test_debug_event_skipped_for_non_notify_entity_id() -> None:
    """B7: a hand-edited option that is not a notify entity_id is skipped
    defensively instead of calling an arbitrary service."""
    services = SimpleNamespace(
        has_service=Mock(return_value=True),
        async_call=AsyncMock(),
    )
    states = SimpleNamespace(is_state=Mock(return_value=True))
    coordinator = object.__new__(AbstractorDataUpdateCoordinator)
    coordinator.hass = SimpleNamespace(states=states, services=services)
    coordinator._last_notified_events = {}
    coordinator.debug_switch_entity_id = "input_boolean.automation_debugger"
    coordinator.notify_entity_id = "script.not_a_notify_target"

    await coordinator._async_notify_debug("entry-1", "spike rejected")

    services.async_call.assert_not_awaited()


async def test_debug_event_none_resets_dedup_for_subentry() -> None:
    """A None event (pipeline healthy again) clears the dedup entry, so the
    next occurrence of a previously notified event is delivered again."""
    services = SimpleNamespace(
        has_service=Mock(return_value=True),
        async_call=AsyncMock(),
    )
    states = SimpleNamespace(is_state=Mock(return_value=True))
    coordinator = object.__new__(AbstractorDataUpdateCoordinator)
    coordinator.hass = SimpleNamespace(states=states, services=services)
    coordinator._last_notified_events = {}
    coordinator.debug_switch_entity_id = "input_boolean.automation_debugger"
    coordinator.notify_entity_id = "notify.adminnotificationgroup"

    await coordinator._async_notify_debug("entry-1", "spike rejected")
    await coordinator._async_notify_debug("entry-1", None)
    await coordinator._async_notify_debug("entry-1", "spike rejected")

    assert services.async_call.await_count == 2


async def test_add_and_remove_subentry() -> None:
    """Coordinator tracks pipelines by subentry_id, not entry_id."""
    coordinator = AbstractorDataUpdateCoordinator(Mock())
    coordinator.add_subentry(
        "subentry-1", {"device_type": "power", "source_entity_id": "sensor.x"}
    )

    assert "subentry-1" in coordinator.subentry_data
    assert "subentry-1" in coordinator.pipelines

    coordinator.remove_subentry("subentry-1")

    assert "subentry-1" not in coordinator.subentry_data
    assert "subentry-1" not in coordinator.pipelines


def test_event_mode_subscribes_to_source_state_changes(monkeypatch) -> None:
    """An event-mode sensor gets a state-change listener on its sources and
    no polling timer; removing it unsubscribes the listener again."""
    registered: list[list[str]] = []
    unsubscribe = Mock()
    monkeypatch.setattr(
        "custom_components.abstractor.coordinator.async_track_state_change_event",
        lambda hass, entity_ids, action: registered.append(entity_ids) or unsubscribe,
    )
    timer = Mock()
    monkeypatch.setattr(
        "custom_components.abstractor.coordinator.async_track_time_interval",
        lambda *args: timer,
    )
    coordinator = AbstractorDataUpdateCoordinator(Mock())

    coordinator.add_subentry(
        "s1",
        {
            CONF_SOURCE_ENTITY_IDS: ["sensor.a", "sensor.b"],
            CONF_UPDATE_MODE: UPDATE_MODE_EVENT,
        },
    )

    assert registered == [["sensor.a", "sensor.b"]]
    timer.assert_not_called()
    coordinator.remove_subentry("s1")
    unsubscribe.assert_called_once()


def test_polling_mode_uses_the_per_sensor_interval(monkeypatch) -> None:
    """Polling mode installs its own timer with the sensor's interval in
    seconds (bounded), not the coordinator's old global interval."""
    intervals: list[timedelta] = []
    unsubscribe = Mock()
    monkeypatch.setattr(
        "custom_components.abstractor.coordinator.async_track_time_interval",
        lambda hass, action, interval: intervals.append(interval) or unsubscribe,
    )
    coordinator = AbstractorDataUpdateCoordinator(Mock())

    coordinator.add_subentry(
        "s1",
        {
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_UPDATE_MODE: UPDATE_MODE_POLLING,
            CONF_POLL_INTERVAL: 7,
        },
    )
    coordinator.add_subentry(
        "s2",
        {
            CONF_SOURCE_ENTITY_ID: "sensor.b",
            CONF_UPDATE_MODE: UPDATE_MODE_POLLING,
            CONF_POLL_INTERVAL: 99999,
        },
    )

    assert intervals == [
        timedelta(seconds=7),
        timedelta(seconds=POLL_INTERVAL_MAX),
    ]
    assert coordinator._interval_for({CONF_POLL_INTERVAL: 0}) == POLL_INTERVAL_MIN
    assert coordinator.update_interval is None


async def test_targeted_refresh_pushes_only_the_triggered_sensor() -> None:
    """A source change updates just that subentry's cached value but still
    notifies listeners so entities and the panel see it immediately."""
    coordinator = AbstractorDataUpdateCoordinator(Mock())
    coordinator.hass.states.get = lambda entity_id: (
        SimpleNamespace(state="12.5") if entity_id == "sensor.x" else None
    )
    coordinator.add_subentry(
        "s1",
        {
            "device_type": "power",
            CONF_SOURCE_ENTITY_ID: "sensor.x",
            CONF_UPDATE_MODE: UPDATE_MODE_EVENT,
        },
    )
    pipeline = Mock()
    pipeline.process_sources = Mock(return_value=12.5)
    pipeline.last_event = None
    coordinator.pipelines["s1"] = pipeline
    listener = Mock()
    coordinator.async_add_listener(listener)

    await coordinator.async_refresh_subentry("s1")

    assert coordinator.data["s1"] == 12.5
    listener.assert_called_once()


def _update_coordinator(
    *, source_state: str | None, pipeline_value: float | None
) -> AbstractorDataUpdateCoordinator:
    """Build a coordinator ready for _async_update_data with one subentry.

    The pipeline is stubbed (its behavior is covered by test_filters.py) so
    these tests isolate the coordinator's own trigger: whether a pipeline
    result reaches the attached Influx exporter.
    """
    states = {"sensor.power_plug": source_state} if source_state is not None else {}
    coordinator = _coordinator_with_states(states)
    coordinator.subentry_data = {
        "subentry-1": {CONF_SOURCE_ENTITY_ID: "sensor.power_plug"}
    }
    pipeline = Mock()
    pipeline.process_sources = Mock(return_value=pipeline_value)
    pipeline.last_event = None
    coordinator.pipelines = {"subentry-1": pipeline}
    # Real __init__ seeds these; this helper bypasses it via object.__new__.
    coordinator.meta = {}
    coordinator.rejected_samples = {}
    coordinator._ring_seq = {}
    coordinator.void_sample_ids = set()
    coordinator.value_history = {}
    coordinator._last_notified_events = {}
    coordinator.debug_switch_entity_id = None
    coordinator.notify_entity_id = None
    return coordinator


async def test_update_data_pushes_value_to_influx_exporter() -> None:
    """[REQ-DATA-002] A non-None pipeline value is pushed to the attached
    Influx exporter with the subentry's first source id and the value."""
    coordinator = _update_coordinator(source_state="12.5", pipeline_value=12.5)
    exporter = Mock()
    exporter.async_push = AsyncMock()
    coordinator.influx_exporter = exporter

    data = await coordinator._async_update_data()

    assert data["subentry-1"] == 12.5
    exporter.async_push.assert_awaited_once_with("sensor.power_plug", 12.5)


async def test_update_data_skips_push_when_value_is_none() -> None:
    """[REQ-DATA-002] A pipeline result of None (source unavailable) must not
    be pushed to the Influx exporter."""
    coordinator = _update_coordinator(source_state=None, pipeline_value=None)
    exporter = Mock()
    exporter.async_push = AsyncMock()
    coordinator.influx_exporter = exporter

    data = await coordinator._async_update_data()

    assert data["subentry-1"] is None
    exporter.async_push.assert_not_awaited()


async def test_add_subentry_seeds_pipeline_from_initial_last_valid_state() -> None:
    """add_subentry passes initial_last_valid_state straight through to the
    new pipeline — this is the seam __init__.py uses to restore the spike
    guard from a persisted snapshot after any coordinator rebuild."""
    coordinator = AbstractorDataUpdateCoordinator(Mock())

    coordinator.add_subentry(
        "subentry-1",
        {"device_type": "energy", "source_entity_id": "sensor.x"},
        initial_last_valid_state=456.7,
    )

    assert coordinator.pipelines["subentry-1"]._last_valid_state == 456.7


async def test_add_subentry_without_seed_defaults_to_none() -> None:
    """No prior value known (e.g. brand-new subentry) -> pipeline starts
    unguarded, exactly as before this change."""
    coordinator = AbstractorDataUpdateCoordinator(Mock())

    coordinator.add_subentry(
        "subentry-1", {"device_type": "power", "source_entity_id": "sensor.x"}
    )

    assert coordinator.pipelines["subentry-1"]._last_valid_state is None


async def test_add_subentry_defaults_aggregation_to_sum() -> None:
    """[B2] Subentries stored before aggregation modes existed carry no
    mode; add_subentry normalizes it to the explicit sum default so the
    pipeline never has to guess (and an explicit mode is passed through)."""
    coordinator = AbstractorDataUpdateCoordinator(Mock())

    coordinator.add_subentry(
        "subentry-1", {"device_type": "power", "source_entity_id": "sensor.x"}
    )
    coordinator.add_subentry(
        "subentry-2",
        {
            "device_type": "power",
            "source_entity_id": "sensor.y",
            "aggregation": "max",
        },
    )

    assert coordinator.subentry_data["subentry-1"]["aggregation"] == "sum"
    assert coordinator.pipelines["subentry-1"].config["aggregation"] == "sum"
    assert coordinator.subentry_data["subentry-2"]["aggregation"] == "max"


def test_add_subentry_logs_warning_when_device_type_missing(caplog) -> None:
    """A corrupted/legacy subentry with no device_type still defaults to
    'power' for polling, but must not do so silently."""
    import logging

    with caplog.at_level(logging.WARNING):
        coordinator = AbstractorDataUpdateCoordinator(Mock())

        coordinator.add_subentry("subentry-1", {"source_entity_id": "sensor.x"})

        assert coordinator.subentry_data["subentry-1"]["device_type"] == "power"
        assert "device_type" in caplog.text
        assert "subentry-1" in caplog.text


async def test_poll_records_freshness_and_delta() -> None:
    """[WS-4 UF-07] Each poll stamps updated_at; consecutive values yield a delta."""
    coordinator = _update_coordinator(source_state="12.5", pipeline_value=7.5)
    coordinator.influx_exporter = None
    await coordinator._async_update_data()
    first = coordinator.meta["subentry-1"]
    assert first.updated_at is not None
    assert first.delta is None  # First poll: no previous value to compare against
    assert first.previous_value == 7.5

    await coordinator._async_update_data()
    second = coordinator.meta["subentry-1"]
    assert second.delta == 0.0
    assert second.stale is False


async def test_unavailable_sample_marks_stale() -> None:
    """UF-11: the stale field is no longer dead — it marks value-less polls."""
    coordinator = _update_coordinator(source_state=None, pipeline_value=None)
    coordinator.influx_exporter = None
    data = await coordinator._async_update_data()
    assert data["subentry-1"] is None
    item = coordinator.meta["subentry-1"]
    assert item.stale is True
    assert item.updated_at is not None


async def test_rejected_samples_ring_records_drops_with_reason() -> None:
    """[WS-5 UF-09] A spike-rejected raw sample lands in the ring with reason."""
    coordinator = _update_coordinator(source_state="12.5", pipeline_value=None)
    coordinator.influx_exporter = None
    pipeline = coordinator.pipelines["subentry-1"]
    pipeline.last_event = "spike_rejected: below last valid"
    await coordinator._async_update_data()
    ring = coordinator.rejected_samples["subentry-1"]
    assert len(ring) == 1
    assert ring[0]["id"] == "subentry-1#1"
    assert ring[0]["reason"].startswith("spike")
    assert ring[0]["value"] == "12.5"


async def test_warn_thresholds_flag_health_meta() -> None:
    """[WS-5 UF-10] warn_above marks meta.warn_hit; the condition gates it."""
    coordinator = _update_coordinator(source_state="12.5", pipeline_value=42.0)
    coordinator.influx_exporter = None
    coordinator.subentry_data["subentry-1"]["warn_above"] = 10.0
    await coordinator._async_update_data()
    assert coordinator.meta["subentry-1"].warn_hit is True


async def test_warn_condition_entity_off_suppresses_hit() -> None:
    coordinator = _update_coordinator(source_state="12.5", pipeline_value=42.0)
    coordinator.influx_exporter = None
    coordinator.subentry_data["subentry-1"].update(
        {"warn_above": 10.0, "warn_condition_entity_id": "input_boolean.gate"}
    )
    await coordinator._async_update_data()
    assert coordinator.meta["subentry-1"].warn_hit is False


def test_attribute_only_event_does_not_queue_refresh(monkeypatch) -> None:
    """[H2/v1.5.1] Only real state changes trigger an update; attribute-only
    events (and the very first event with no old_state) must not.
    """
    actions: list = []
    monkeypatch.setattr(
        "custom_components.abstractor.coordinator.async_track_state_change_event",
        lambda hass, ids, action: actions.append(action) or Mock(),
    )
    coordinator = AbstractorDataUpdateCoordinator(Mock())
    coordinator.add_subentry(
        "s1",
        {CONF_SOURCE_ENTITY_ID: "sensor.a", CONF_UPDATE_MODE: UPDATE_MODE_EVENT},
    )
    coordinator._queue_refresh = Mock()

    def event(old: str | None, new: str) -> SimpleNamespace:
        return SimpleNamespace(
            data={
                "old_state": SimpleNamespace(state=old) if old is not None else None,
                "new_state": SimpleNamespace(state=new),
            }
        )

    actions[0](event("12.5", "12.5"))  # attribute-only
    coordinator._queue_refresh.assert_not_called()
    actions[0](event("12.5", "13.0"))  # real change
    actions[0](event(None, "14.0"))  # new entity
    assert coordinator._queue_refresh.call_count == 2


async def test_trigger_burst_coalesces_and_rearms() -> None:
    """[H2/v1.5.1] A burst schedules one task; a trigger arriving while that
    task is in flight is remembered and schedules exactly one follow-up.
    """
    coordinator = AbstractorDataUpdateCoordinator(Mock())
    tasks: list = []
    coordinator.hass.async_create_task = lambda coro: tasks.append(coro)

    coordinator._queue_refresh("s1")
    coordinator._queue_refresh("s1")  # duplicate: remember a follow-up
    assert len(tasks) == 1
    assert coordinator._retrigger_refreshes == {"s1"}

    await tasks[0]
    assert len(tasks) == 2  # follow-up was scheduled after completion
    # The follow-up is pending again while its task has not run yet.
    assert "s1" in coordinator._pending_refreshes

    await tasks[1]
    assert "s1" not in coordinator._pending_refreshes
    assert not coordinator._retrigger_refreshes


async def test_targeted_refresh_error_is_booked() -> None:
    """[M3/v1.5.1] A failing targeted update sets coordinator error state
    instead of escaping as an unhandled fire-and-forget task.
    """

    async def boom(*_args, **_kwargs) -> None:
        raise RuntimeError("boom")

    coordinator = AbstractorDataUpdateCoordinator(Mock())
    coordinator.async_refresh_subentry = boom  # type: ignore[method-assign]
    coordinator.async_set_update_error = Mock()

    await coordinator._async_refresh_queued("s1")

    coordinator.async_set_update_error.assert_called_once()


def test_legacy_mode_uses_polling_with_root_interval() -> None:
    """[T3/v1.5.1] A subentry without update_mode stays a legacy polling
    sensor; an invalid interval falls back to the built-in default.
    """
    coordinator = AbstractorDataUpdateCoordinator(Mock())
    coordinator.legacy_poll_interval = 17
    config = {CONF_SOURCE_ENTITY_ID: "sensor.a"}

    assert coordinator._update_mode_for(config) == UPDATE_MODE_POLLING
    assert coordinator._interval_for(config) == 17
    assert (
        coordinator._interval_for({CONF_POLL_INTERVAL: "abc"})
        == DEFAULT_SUBENTRY_POLL_INTERVAL
    )


async def test_targeted_refresh_isolates_other_sensors() -> None:
    """[T4/v1.5.1] Refreshing one sensor leaves all other cached values and
    the listener count untouched; unknown ids are a silent no-op.
    """
    states = {"sensor.a": "2.0", "sensor.b": "3.0"}
    coordinator = AbstractorDataUpdateCoordinator(Mock())
    coordinator.hass.states.get = lambda entity_id: (
        SimpleNamespace(state=states[entity_id]) if entity_id in states else None
    )
    for subentry_id, source in (("s1", "sensor.a"), ("s2", "sensor.b")):
        coordinator.add_subentry(
            subentry_id,
            {
                CONF_SOURCE_ENTITY_ID: source,
                CONF_UPDATE_MODE: UPDATE_MODE_EVENT,
            },
        )
    pipeline = Mock()
    pipeline.process_sources = Mock(
        side_effect=lambda raw, **_kwargs: (
            float(raw[0]) if raw and raw[0] is not None else None
        )
    )
    pipeline.last_event = None
    coordinator.pipelines = {"s1": pipeline, "s2": pipeline}
    await coordinator.async_full_refresh()

    listener = Mock()
    coordinator.async_add_listener(listener)
    states["sensor.a"] = "7.0"
    await coordinator.async_refresh_subentry("s1")
    await coordinator.async_refresh_subentry("ghost")

    assert coordinator.data["s1"] == 7.0
    assert coordinator.data["s2"] == 3.0
    listener.assert_called_once()


async def test_full_refresh_publishes_all_values_once() -> None:
    """[H1/v1.5.1] The full refresh publishes under the same lock as targeted
    updates and notifies listeners exactly once.
    """
    coordinator = AbstractorDataUpdateCoordinator(Mock())
    coordinator.hass.states.get = lambda entity_id: (
        SimpleNamespace(state="4.5") if entity_id == "sensor.a" else None
    )
    coordinator.add_subentry(
        "s1",
        {CONF_SOURCE_ENTITY_ID: "sensor.a", CONF_UPDATE_MODE: UPDATE_MODE_EVENT},
    )
    pipeline = Mock()
    pipeline.process_sources = Mock(return_value=4.5)
    pipeline.last_event = None
    coordinator.pipelines["s1"] = pipeline
    listener = Mock()
    coordinator.async_add_listener(listener)

    await coordinator.async_full_refresh()

    assert coordinator.data["s1"] == 4.5
    assert coordinator.last_update_success is True
    listener.assert_called_once()
