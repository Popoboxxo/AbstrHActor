"""Test coordinator diagnostics notification behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.abstractor.const import (
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
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
