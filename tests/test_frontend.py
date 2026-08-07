"""Test Abstractor sidebar panel registration (ADR-007)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.abstractor.frontend import (
    async_register_panel,
    async_unregister_panel,
)


def _hass(panel_js_exists: bool = True) -> SimpleNamespace:
    hass = SimpleNamespace(
        data={},
        http=SimpleNamespace(async_register_static_paths=AsyncMock()),
        async_add_executor_job=AsyncMock(return_value=panel_js_exists),
    )
    hass.async_create_task = lambda coro: _run_now(coro)
    return hass


def _run_now(coro):
    """Run a coroutine immediately and wrap it in a completed-task-like object."""
    import asyncio

    return asyncio.ensure_future(coro)


async def test_register_panel_skips_when_js_missing() -> None:
    """No panel JS on disk means no sidebar entry, not a crash."""
    hass = _hass(panel_js_exists=False)

    result = await async_register_panel(hass)

    assert result is False
    assert hass.data.get("abstractor_panel_registered") is not True


async def test_register_panel_is_idempotent() -> None:
    """A second call after successful registration is a cheap no-op."""
    hass = _hass(panel_js_exists=True)
    hass.data["abstractor_panel_registered"] = True

    result = await async_register_panel(hass)

    assert result is True
    hass.http.async_register_static_paths.assert_not_called()


async def test_unregister_panel_noop_when_never_registered() -> None:
    """Unregistering a panel that was never registered must not raise."""
    hass = _hass()

    await async_unregister_panel(hass)  # must not raise

    assert "abstractor_panel_registered" not in hass.data
