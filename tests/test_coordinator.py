"""Test coordinator diagnostics notification behavior."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.abstractor.const import (
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_ID,
    DEFAULT_POLL_INTERVAL,
)
from custom_components.abstractor.coordinator import AbstractorDataUpdateCoordinator


def _coordinator_with_states(states: dict[str, str]) -> AbstractorDataUpdateCoordinator:
    coordinator = object.__new__(AbstractorDataUpdateCoordinator)
    coordinator.hass = SimpleNamespace(
        states=SimpleNamespace(
            get=lambda entity_id: SimpleNamespace(state=states[entity_id])
            if entity_id in states
            else None
        )
    )
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


async def test_debug_event_notifies_only_when_debug_toggle_is_on() -> None:
    """Debug notifications follow the existing HA toggle and are deduplicated."""
    services = SimpleNamespace(
        has_service=Mock(return_value=True),
        async_call=AsyncMock(),
    )
    states = SimpleNamespace(is_state=Mock(return_value=True))
    coordinator = object.__new__(AbstractorDataUpdateCoordinator)
    coordinator.hass = SimpleNamespace(states=states, services=services)
    coordinator._last_notified_events = {}

    await coordinator._async_notify_debug("entry-1", "spike rejected")
    await coordinator._async_notify_debug("entry-1", "spike rejected")

    services.async_call.assert_awaited_once()


async def test_add_and_remove_subentry() -> None:
    """Coordinator tracks pipelines by subentry_id, not entry_id."""
    coordinator = AbstractorDataUpdateCoordinator(Mock())
    coordinator.add_subentry("subentry-1", {"device_type": "power", "source_entity_id": "sensor.x"})

    assert "subentry-1" in coordinator.subentry_data
    assert "subentry-1" in coordinator.pipelines

    coordinator.remove_subentry("subentry-1")

    assert "subentry-1" not in coordinator.subentry_data
    assert "subentry-1" not in coordinator.pipelines


def test_set_update_interval_updates_interval_and_reschedules() -> None:
    """[REQ-CORE-007] set_update_interval swaps the interval and cancels +
    re-schedules the periodic timer through the coordinator's own seams."""
    coordinator = AbstractorDataUpdateCoordinator(Mock())
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_POLL_INTERVAL)

    coordinator._unsub_refresh = Mock()
    coordinator._schedule_refresh = Mock()

    coordinator.set_update_interval(7)

    assert coordinator.update_interval == timedelta(seconds=7)
    coordinator._unsub_refresh.assert_called_once()
    coordinator._schedule_refresh.assert_called_once()
    assert coordinator.config_entry is None


def test_set_update_interval_falls_back_without_scheduled_timer() -> None:
    """A freshly constructed coordinator has no timer yet (_unsub_refresh is
    None), so the private-seam path cannot run — the fallback requests an
    immediate refresh instead of silently keeping the old interval."""
    coordinator = AbstractorDataUpdateCoordinator(Mock())

    coordinator.set_update_interval(7)

    assert coordinator.update_interval == timedelta(seconds=7)
    coordinator.hass.async_create_task.assert_called_once()
    coroutine = coordinator.hass.async_create_task.call_args.args[0]
    coroutine.close()  # never awaited — only assert the fallback was invoked
    assert coordinator.config_entry is None


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
    coordinator._last_notified_events = {}
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
