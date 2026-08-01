"""Test coordinator diagnostics notification behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.abstractor.coordinator import AbstractorDataUpdateCoordinator


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
