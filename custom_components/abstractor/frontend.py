"""Sidebar panel registration for Abstractor (ADR-007).

Serves a single static JS file (custom_components/abstractor/www/
abstractor-panel.js, a dependency-free vanilla Web Component — no Lit, no
build step) and registers it as a built-in sidebar panel. Config/options
themselves stay on the standard HA Config Flow (Settings > Devices &
Services); this panel is a read-only overview across all Abstractor
devices, not a second way to configure them.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_PANEL_JS_NAME = "abstractor-panel.js"
_PANEL_URL = f"/abstractor_panel/{_PANEL_JS_NAME}"
_PANEL_ELEMENT = "abstractor-panel"
_PANEL_URL_PATH = "abstractor"
_PANEL_TASK_KEY = "abstractor_panel_task"
_PANEL_REGISTERED_KEY = "abstractor_panel_registered"


async def _do_register_panel(hass: HomeAssistant, src: Path) -> bool:
    """Register the static path and the sidebar panel as one operation."""
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(_PANEL_URL, str(src), True)]
        )
    except Exception as exc:  # pragma: no cover - defensive, mirrors HA's own pattern
        if "already" not in str(exc).lower():
            _LOGGER.warning("Abstractor panel static path registration failed: %s", exc)
            return False

    try:
        from homeassistant.components import frontend

        version = str(int(src.stat().st_mtime)) if src.exists() else "1"
        frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title="Abstractor",
            sidebar_icon="mdi:layers-outline",
            frontend_url_path=_PANEL_URL_PATH,
            config={
                "_panel_custom": {
                    "name": _PANEL_ELEMENT,
                    "module_url": f"{_PANEL_URL}?v={version}",
                    "embed_iframe": False,
                    "trust_external": False,
                }
            },
            require_admin=False,
        )
        return True
    except Exception as exc:  # pragma: no cover - defensive, mirrors HA's own pattern
        if "already" not in str(exc).lower():
            _LOGGER.warning("Failed to register Abstractor panel: %s", exc)
            return False
        return True


async def async_register_panel(hass: HomeAssistant) -> bool:
    """Serve the panel JS and register the sidebar entry.

    Safe to call on every config entry setup; concurrent/repeat calls share
    the same in-flight task and are no-ops once already registered.
    """
    if hass.data.get(_PANEL_REGISTERED_KEY):
        return True

    src = Path(__file__).parent / "www" / _PANEL_JS_NAME
    if not await hass.async_add_executor_job(src.exists):
        _LOGGER.warning("Panel JS not found at %s — sidebar panel not registered", src)
        return False

    if _PANEL_TASK_KEY not in hass.data:
        hass.data[_PANEL_TASK_KEY] = hass.async_create_task(
            _do_register_panel(hass, src)
        )

    task = hass.data[_PANEL_TASK_KEY]
    try:
        result = bool(await task)
    finally:
        hass.data.pop(_PANEL_TASK_KEY, None)

    hass.data[_PANEL_REGISTERED_KEY] = result
    return result


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar panel when the last config entry is unloaded."""
    if not hass.data.get(_PANEL_REGISTERED_KEY):
        return
    try:
        from homeassistant.components import frontend

        frontend.async_remove_panel(hass, _PANEL_URL_PATH)
    except Exception as exc:  # pragma: no cover - defensive, mirrors HA's own pattern
        _LOGGER.debug("Failed to remove Abstractor panel: %s", exc)
    hass.data.pop(_PANEL_REGISTERED_KEY, None)
