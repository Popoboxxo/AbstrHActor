# Device Bundling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let multiple Abstract sensors (any mix of power/energy/water) share one Home Assistant device, both when creating new sensors and when reorganizing existing ones, with zero effect on existing `unique_id`/`entity_id`/recorder history.

**Architecture:** Adopt Home Assistant's config subentries feature (native since ~2025.2/2025.3). A single singleton "Abstractor" config entry becomes the parent; every Abstract sensor becomes a subentry under it. Multiple subentries supplying the same device-identifier value get merged into one HA device automatically by the device registry — no new merge logic to write. A one-time `async_setup` reconciliation converts existing installations' many flat top-level entries into subentries under a newly-created root entry.

**Tech Stack:** Python 3.12+, Home Assistant custom integration (`homeassistant.config_entries.ConfigSubentryFlow`), `pytest-homeassistant-custom-component` for unit tests, Playwright for E2E.

## Global Constraints

- `homeassistant` minimum version moves from `2025.1.0` to `2025.3.0` in both `hacs.json` and `custom_components/abstractor/manifest.json` (config subentries require it) — per spec `docs/superpowers/specs/2026-08-08-device-bundling-design.md`.
- No existing `unique_id`, `entity_id`, or recorder history may change for any sensor, migrated or not — this is the project's established, non-negotiable stability guarantee (REQ-CORE-001).
- The reconciliation (migration) mechanism is `async_setup`-driven, not `async_migrate_entry` — verified against Home Assistant's own `kitchen_sink` reference integration; `async_migrate_entry` cannot restructure across entries (see spec's "Migration" section for why).
- Naming/nomenclature customization, sidebar-panel write access, configurable update/polling modes, and configurable per-entity source-failure behavior are explicitly out of scope for this plan (see spec's "Out of Scope").

---

## File Structure

- Modify: `custom_components/abstractor/const.py` — add `CONF_DEVICE_GROUP_ID`, `CONF_TARGET_DEVICE_ID`, `SUBENTRY_TYPE_SENSOR`.
- Modify: `custom_components/abstractor/manifest.json` — add `"homeassistant": "2025.3.0"`.
- Modify: `hacs.json` — bump `"homeassistant"` from `"2025.1.0"` to `"2025.3.0"`.
- Modify: `custom_components/abstractor/coordinator.py` — rename entry-keyed dicts to subentry-keyed.
- Modify: `custom_components/abstractor/config_flow.py` — `AbstractorConfigFlow.async_step_user` becomes root-entry-only setup; add `AbstractorSensorSubentryFlowHandler(ConfigSubentryFlow)` with `async_step_user` (create) and `async_step_reconfigure` (edit/move-device, replaces today's `AbstractorOptionsFlowHandler` for sensor-level settings); register it via `async_get_supported_subentry_types`.
- Modify: `custom_components/abstractor/sensor.py` — iterate `entry.subentries` instead of treating the entry itself as one sensor; shared `DeviceInfo` via a device-group helper.
- Modify: `custom_components/abstractor/__init__.py` — `async_setup` reconciliation function that converts legacy flat entries into subentries under a newly-created root entry.
- Test: `tests/test_coordinator.py`, `tests/test_config_flow.py`, `tests/test_sensor.py` (existing files, extended), `tests/test_reconciliation.py` (new).
- Test: `tests_e2e/test_device_bundling_e2e.py` (new).

---

### Task 1: Version floor and new constants

**Files:**
- Modify: `hacs.json`
- Modify: `custom_components/abstractor/manifest.json`
- Modify: `custom_components/abstractor/const.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `CONF_DEVICE_GROUP_ID` (str constant `"device_group_id"`), `CONF_TARGET_DEVICE_ID` (str constant `"target_device_id"`), `SUBENTRY_TYPE_SENSOR` (str constant `"sensor"`) — used by Tasks 3-6.

- [x] **Step 1: Bump the HA version floor**

In `hacs.json`, change:
```json
  "homeassistant": "2025.1.0",
```
to:
```json
  "homeassistant": "2025.3.0",
```

In `custom_components/abstractor/manifest.json`, add a `"homeassistant"` key (currently absent) right after `"documentation"`:
```json
  "documentation": "https://github.com/Popoboxxo/AbstrHActor",
  "homeassistant": "2025.3.0",
```

- [x] **Step 2: Add the new constants**

In `custom_components/abstractor/const.py`, add after the existing `CONF_NET_SUBTRACT_ENTITY_ID` line:
```python
CONF_DEVICE_GROUP_ID: Final = "device_group_id"
CONF_TARGET_DEVICE_ID: Final = "target_device_id"
SUBENTRY_TYPE_SENSOR: Final = "sensor"
```

- [x] **Step 3: Verify the JSON/Python still parse**

Run:
```bash
python3 -c "import json; json.load(open('hacs.json')); json.load(open('custom_components/abstractor/manifest.json')); print('ok')"
python3 -c "from custom_components.abstractor.const import CONF_DEVICE_GROUP_ID, CONF_TARGET_DEVICE_ID, SUBENTRY_TYPE_SENSOR; print('ok')"
```
Expected: both print `ok`.

- [x] **Step 4: Commit**

```bash
git add hacs.json custom_components/abstractor/manifest.json custom_components/abstractor/const.py
git commit -m "feat: bump HA floor to 2025.3.0, add device-bundling constants"
```

---

### Task 2: Coordinator — key by subentry_id instead of entry_id

**Files:**
- Modify: `custom_components/abstractor/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `CONF_DEVICE_GROUP_ID` from Task 1 (not read directly by the coordinator, but the config dict shape now includes it — no coordinator logic needs to special-case it since it's already merged via `{**entry.data, **entry.options}`... this task changes the coordinator to work on `ConfigSubentry` objects instead of `ConfigEntry` objects, so this is now `{**subentry.data}` — subentries have no separate `.options`, so this changes how config is read too).
- Produces: `AbstractorDataUpdateCoordinator.add_subentry(subentry_id: str, subentry_data: dict) -> None`, `remove_subentry(subentry_id: str) -> None`, `self.entries` renamed to `self.subentry_data: dict[str, dict]`, `self.pipelines: dict[str, AbstractorFilterPipeline]` (unchanged shape, subentry_id-keyed) — consumed by Task 5 (sensor.py) and Task 6 (`__init__.py`'s `_save_snapshot`, which reads `coordinator.entries`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_coordinator.py` (read the existing file first — this follows its established `Mock`-based pattern):
```python
async def test_add_and_remove_subentry() -> None:
    """Coordinator tracks pipelines by subentry_id, not entry_id."""
    from custom_components.abstractor.coordinator import AbstractorDataUpdateCoordinator

    coordinator = AbstractorDataUpdateCoordinator(Mock())
    coordinator.add_subentry("subentry-1", {"device_type": "power", "source_entity_id": "sensor.x"})

    assert "subentry-1" in coordinator.subentry_data
    assert "subentry-1" in coordinator.pipelines

    coordinator.remove_subentry("subentry-1")

    assert "subentry-1" not in coordinator.subentry_data
    assert "subentry-1" not in coordinator.pipelines
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coordinator.py::test_add_and_remove_subentry -v`
Expected: FAIL with `AttributeError: 'AbstractorDataUpdateCoordinator' object has no attribute 'add_subentry'`.

- [ ] **Step 3: Rewrite the coordinator**

Replace the whole content of `custom_components/abstractor/coordinator.py`:
```python
"""DataUpdateCoordinator for Abstractor."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
    CONF_NET_SUBTRACT_ENTITY_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    DOMAIN,
)
from .filters import AbstractorFilterPipeline

_LOGGER = logging.getLogger(__name__)

class AbstractorDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Abstractor data."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.subentry_data: dict[str, dict] = {}
        self.pipelines: dict[str, AbstractorFilterPipeline] = {}
        self.influx_exporter = None
        self._last_notified_events: dict[str, str] = {}

    def add_subentry(self, subentry_id: str, subentry_data: dict) -> None:
        """Add a subentry to central polling."""
        config = dict(subentry_data)
        config["device_type"] = config.get("device_type", "power")
        self.subentry_data[subentry_id] = config
        self.pipelines[subentry_id] = AbstractorFilterPipeline(config)

    def remove_subentry(self, subentry_id: str) -> None:
        """Remove a subentry from central polling."""
        self.subentry_data.pop(subentry_id, None)
        self.pipelines.pop(subentry_id, None)
        self._last_notified_events.pop(subentry_id, None)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via central polling."""
        data: dict[str, float | None] = {}
        for subentry_id, config in self.subentry_data.items():
            source_ids = config.get(CONF_SOURCE_ENTITY_IDS) or [
                config.get(CONF_SOURCE_ENTITY_ID)
            ]
            source_ids = [source_id for source_id in source_ids if source_id]
            if not source_ids:
                continue

            raw_states = [
                (state_obj.state if (state_obj := self.hass.states.get(source_id)) else None)
                for source_id in source_ids
            ]

            pipeline = self.pipelines.get(subentry_id)
            if pipeline:
                net_subtract_raw = self._read_state(config.get(CONF_NET_SUBTRACT_ENTITY_ID))
                fallback_raw = self._read_state(config.get(CONF_FALLBACK_SOURCE_ENTITY_ID))
                fallback_condition_met = self._fallback_condition_met(config)
                val = pipeline.process_sources(
                    raw_states,
                    net_subtract_raw=net_subtract_raw,
                    fallback_raw=fallback_raw,
                    fallback_condition_met=fallback_condition_met,
                )
                data[subentry_id] = val
                await self._async_notify_debug(subentry_id, pipeline.last_event)

                if self.influx_exporter and val is not None:
                    await self.influx_exporter.async_push(source_ids[0], val)
        return data

    def _read_state(self, entity_id: str | None) -> str | None:
        """Read a raw HA state string for an optional entity_id."""
        if not entity_id:
            return None
        state_obj = self.hass.states.get(entity_id)
        return state_obj.state if state_obj else None

    def _fallback_condition_met(self, config: dict[str, Any]) -> bool:
        """Evaluate the REQ-COMP-004 fallback condition.

        No fallback source configured -> never eligible. A fallback source
        without a condition entity is always eligible when the primary is
        unavailable. With a condition entity, the fallback is only eligible
        while that entity's state matches the configured expected state.
        """
        if not config.get(CONF_FALLBACK_SOURCE_ENTITY_ID):
            return False
        condition_entity_id = config.get(CONF_FALLBACK_CONDITION_ENTITY_ID)
        if not condition_entity_id:
            return True
        expected_state = config.get(CONF_FALLBACK_CONDITION_STATE)
        return self._read_state(condition_entity_id) == expected_state

    async def _async_notify_debug(self, subentry_id: str, event: str | None) -> None:
        """Send deduplicated debug events through the existing HA notify group."""
        if event is None:
            self._last_notified_events.pop(subentry_id, None)
            return
        if self._last_notified_events.get(subentry_id) == event:
            return
        if not self.hass.states.is_state("input_boolean.automation_debugger", "on"):
            return
        if not self.hass.services.has_service("notify", "adminnotificationgroup"):
            return
        await self.hass.services.async_call(
            "notify",
            "adminnotificationgroup",
            {"message": f"Abstractor {subentry_id}: {event}"},
            blocking=False,
        )
        self._last_notified_events[subentry_id] = event
```

Note what changed from the current file: `ConfigEntry` import dropped (coordinator no longer holds entry objects, just plain dicts — subentries have no `.options` to merge, unlike the old per-entry `{**entry.data, **entry.options}`, since subentry reconfiguration replaces the whole subentry's `data` in one write — see Task 4). `add_entry`/`remove_entry` renamed to `add_subentry`/`remove_subentry`, `self.entries` renamed to `self.subentry_data`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_coordinator.py -v`
Expected: all PASS, including the new test and every pre-existing test in this file (read the file first to confirm none reference the old `add_entry`/`entries` names — if any do, update them to `add_subentry`/`subentry_data` in this same commit, since this is a rename, not new behavior).

- [ ] **Step 5: Commit**

```bash
git add custom_components/abstractor/coordinator.py tests/test_coordinator.py
git commit -m "refactor: key coordinator by subentry_id instead of entry_id"
```

---

### Task 3: Subentry flow — create a new sensor

**Files:**
- Modify: `custom_components/abstractor/config_flow.py`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `CONF_DEVICE_GROUP_ID`, `CONF_TARGET_DEVICE_ID`, `SUBENTRY_TYPE_SENSOR` from Task 1.
- Produces: `AbstractorSensorSubentryFlowHandler(ConfigSubentryFlow)` class with `async_step_user`; `AbstractorConfigFlow.async_get_supported_subentry_types` — consumed by Task 4 (adds `async_step_reconfigure` to the same class) and by HA itself at runtime (Task 5/6 don't call these directly, they're invoked by the HA config-entries UI).
- Produces: module-level helper `_device_group_id_for_device(hass, device_id: str) -> str | None` — given an HA device registry `device_id`, returns the existing `(DOMAIN, X)` identifier's `X` value for that device, or `None` if not found. Consumed by Task 4 too.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config_flow.py` (below the existing `test_form`, following its `hass: HomeAssistant` fixture pattern):
```python
async def test_subentry_create_form(hass: HomeAssistant) -> None:
    """A subentry flow creates a sensor under the root entry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == "form"

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.test_power",
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "Abstract power"
    subentries = list(root_entry.subentries.values())
    assert len(subentries) == 1
    assert subentries[0].data[CONF_DEVICE_TYPE] == "power"
    assert subentries[0].data[CONF_SOURCE_ENTITY_ID] == "sensor.test_power"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_flow.py::test_subentry_create_form -v`
Expected: FAIL — `hass.config_entries.subentries.async_init` errors because `AbstractorConfigFlow` doesn't declare `async_get_supported_subentry_types` yet, so subentry type `"sensor"` is unrecognized for this domain.

- [ ] **Step 3: Add the subentry flow to config_flow.py**

Replace the whole content of `custom_components/abstractor/config_flow.py`:
```python
"""Config flow for Abstractor."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .const import (
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_TYPE,
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
    CONF_FALLBACK_ZERO,
    CONF_INVERT,
    CONF_LEGACY_UNIQUE_ID,
    CONF_NET_SUBTRACT_ENTITY_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    CONF_SPIKE_FILTER,
    CONF_TARGET_DEVICE_ID,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    SENSOR_TYPES,
    SUBENTRY_TYPE_SENSOR,
)

_LOGGER = logging.getLogger(__name__)


def _device_group_id_for_device(hass, device_id: str) -> str | None:
    """Look up this integration's own (DOMAIN, X) identifier for a device_id.

    A user picks a target device via HA's internal registry device_id
    (opaque to us); to bundle a new sensor onto that device we need the
    SAME identifier key an earlier subentry originally registered that
    device under, so the device registry keeps merging them into one
    device instead of creating a second one.
    """
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            return identifier
    return None


class AbstractorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the one-time setup of the Abstractor root entry."""

    VERSION = CONFIG_ENTRY_VERSION

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the singleton root entry; no sensor data is collected here."""
        await self.async_set_unique_id("abstractor_root")
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="Abstractor", data={})

        return self.async_show_form(step_id="user")

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {SUBENTRY_TYPE_SENSOR: AbstractorSensorSubentryFlowHandler}


class AbstractorSensorSubentryFlowHandler(ConfigSubentryFlow):
    """Create or reconfigure one Abstract sensor as a subentry."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Create a new Abstract sensor subentry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            sources = user_input.get(CONF_SOURCE_ENTITY_IDS) or [
                user_input.get(CONF_SOURCE_ENTITY_ID)
            ]
            sources = [source for source in sources if source]
            if not sources:
                errors["base"] = "source_required"
            else:
                data = self._normalize(user_input, sources)
                device_type = data[CONF_DEVICE_TYPE]
                return self.async_create_entry(
                    title=f"Abstract {device_type}", data=data
                )

        return self.async_show_form(
            step_id="user", data_schema=self._schema(), errors=errors
        )

    def _normalize(self, user_input: dict[str, Any], sources: list[str]) -> dict[str, Any]:
        """Shared shaping for both create and reconfigure: sources, legacy id,
        and resolving the picked target device into our own identifier key."""
        data = dict(user_input)
        if len(sources) > 1:
            data[CONF_SOURCE_ENTITY_IDS] = sorted(set(sources))
        else:
            data.pop(CONF_SOURCE_ENTITY_IDS, None)

        legacy_unique_id = data.get(CONF_LEGACY_UNIQUE_ID) or None
        if legacy_unique_id:
            data[CONF_LEGACY_UNIQUE_ID] = legacy_unique_id
        else:
            data.pop(CONF_LEGACY_UNIQUE_ID, None)

        target_device_id = data.pop(CONF_TARGET_DEVICE_ID, None)
        if target_device_id:
            group_id = _device_group_id_for_device(self.hass, target_device_id)
            if group_id:
                data[CONF_DEVICE_GROUP_ID] = group_id
        return data

    @staticmethod
    def _schema() -> vol.Schema:
        """Build the create-sensor schema."""
        return vol.Schema(
            {
                vol.Required(CONF_DEVICE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=SENSOR_TYPES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_SOURCE_ENTITY_ID): selector.EntitySelector(),
                vol.Optional(CONF_SOURCE_ENTITY_IDS): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
                vol.Optional(CONF_LEGACY_UNIQUE_ID): selector.TextSelector(),
                vol.Optional(CONF_TARGET_DEVICE_ID): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(integration=DOMAIN)
                ),
            }
        )
```

Note: `AbstractorOptionsFlowHandler` (the old top-level Options Flow for editing sensor settings) is REMOVED here — Task 4 replaces it with `async_step_reconfigure` on `AbstractorSensorSubentryFlowHandler`. `AbstractorConfigFlow.async_get_options_flow` is also removed since the root entry has no options of its own.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_flow.py -v`
Expected: `test_subentry_create_form` PASSES. `test_form` (the old top-level flow test) now FAILS — expected, since `async_step_user` no longer accepts sensor fields. Update `test_form` in the same commit to match the new root-entry-only behavior:
```python
async def test_form(hass: HomeAssistant) -> None:
    """The top-level flow only creates the singleton root entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"

    with patch(
        "custom_components.abstractor.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {}
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "Abstractor"
    assert result2["data"] == {}
    assert len(mock_setup_entry.mock_calls) == 1
```
Run `pytest tests/test_config_flow.py -v` again. Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/abstractor/config_flow.py tests/test_config_flow.py
git commit -m "feat: add subentry flow for creating Abstract sensors"
```

---

### Task 4: Subentry flow — reconfigure existing sensor (edit settings, move device)

**Files:**
- Modify: `custom_components/abstractor/config_flow.py`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `AbstractorSensorSubentryFlowHandler`, `_device_group_id_for_device`, `_schema`/`_normalize` from Task 3.
- Produces: `AbstractorSensorSubentryFlowHandler.async_step_reconfigure` — invoked by HA's native subentry "reconfigure" UI action, not called directly by other tasks.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config_flow.py`:
```python
async def test_subentry_reconfigure_moves_device(hass: HomeAssistant) -> None:
    """Reconfiguring a subentry can move it onto an existing device."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from homeassistant.config_entries import ConfigSubentry
    from homeassistant.helpers import device_registry as dr

    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    existing_subentry = ConfigSubentry(
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.a"},
        subentry_type="sensor",
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, existing_subentry)

    device_registry = dr.async_get(hass)
    target_device = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=existing_subentry.subentry_id,
        identifiers={(DOMAIN, existing_subentry.subentry_id)},
    )

    another_subentry = ConfigSubentry(
        data={CONF_DEVICE_TYPE: "energy", CONF_SOURCE_ENTITY_ID: "sensor.b"},
        subentry_type="sensor",
        title="Abstract energy",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, another_subentry)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": another_subentry.subentry_id,
        },
    )
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "energy",
            CONF_SOURCE_ENTITY_ID: "sensor.b",
            CONF_TARGET_DEVICE_ID: target_device.id,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"
    updated = root_entry.subentries[another_subentry.subentry_id]
    assert updated.data[CONF_DEVICE_GROUP_ID] == existing_subentry.subentry_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_flow.py::test_subentry_reconfigure_moves_device -v`
Expected: FAIL — `AbstractorSensorSubentryFlowHandler` has no `async_step_reconfigure`, so HA's subentry flow manager can't find the reconfigure step.

- [ ] **Step 3: Add async_step_reconfigure**

In `custom_components/abstractor/config_flow.py`, add this method to `AbstractorSensorSubentryFlowHandler` (after `async_step_user`):
```python
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit an existing Abstract sensor's settings, or move it to another device."""
        errors: dict[str, str] = {}
        current = self._get_reconfigure_subentry()

        if user_input is not None:
            sources = user_input.get(CONF_SOURCE_ENTITY_IDS) or [
                user_input.get(CONF_SOURCE_ENTITY_ID)
            ]
            sources = [source for source in sources if source]
            if not sources:
                errors["base"] = "source_required"
            else:
                data = self._normalize(user_input, sources)
                device_type = data[CONF_DEVICE_TYPE]
                return self.async_update_and_abort(
                    self._get_entry(),
                    current,
                    title=f"Abstract {device_type}",
                    data=data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._schema(), current.data
            ),
            errors=errors,
        )
```

Also extend `_schema()`'s `vol.Optional(CONF_SPIKE_FILTER, ...)`-style pipeline options (currently only in the old `AbstractorOptionsFlowHandler`, which Task 3 removed) — the reconfigure step needs every field the old options flow had, not just what `async_step_user`'s create-time schema covers. Replace `_schema()` entirely with:
```python
    @staticmethod
    def _schema() -> vol.Schema:
        """Build the sensor schema — shared by create and reconfigure."""
        return vol.Schema(
            {
                vol.Required(CONF_DEVICE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=SENSOR_TYPES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_SOURCE_ENTITY_ID): selector.EntitySelector(),
                vol.Optional(CONF_SOURCE_ENTITY_IDS): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
                vol.Optional(CONF_LEGACY_UNIQUE_ID): selector.TextSelector(),
                vol.Optional(CONF_TARGET_DEVICE_ID): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(integration=DOMAIN)
                ),
                vol.Optional(CONF_SPIKE_FILTER, default=False): bool,
                vol.Optional(CONF_INVERT, default=False): bool,
                vol.Optional(CONF_FALLBACK_ZERO, default=False): bool,
                vol.Optional(CONF_NET_SUBTRACT_ENTITY_ID): selector.EntitySelector(),
                vol.Optional(CONF_FALLBACK_SOURCE_ENTITY_ID): selector.EntitySelector(),
                vol.Optional(CONF_FALLBACK_CONDITION_ENTITY_ID): selector.EntitySelector(),
                vol.Optional(CONF_FALLBACK_CONDITION_STATE): selector.TextSelector(),
            }
        )
```

(`self.add_suggested_values_to_schema(schema, current.data)` pre-fills the form with the subentry's current values — the standard Home Assistant helper for exactly this, already imported implicitly via `ConfigSubentryFlow`'s base class; if it's not available on your installed `homeassistant` version, verify with `python3 -c "from homeassistant.config_entries import ConfigSubentryFlow; print(hasattr(ConfigSubentryFlow, 'add_suggested_values_to_schema'))"` and fall back to `self.async_show_form(step_id="reconfigure", data_schema=self._schema(), errors=errors, description_placeholders=None)` without pre-fill if it isn't.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_flow.py -v`
Expected: all PASS, including `test_subentry_reconfigure_moves_device`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/abstractor/config_flow.py tests/test_config_flow.py
git commit -m "feat: add subentry reconfigure flow (edit settings, move device)"
```

---

### Task 5: sensor.py — read subentries, bundle devices

**Files:**
- Modify: `custom_components/abstractor/sensor.py`
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `coordinator.add_subentry`/`subentry_data` from Task 2; `CONF_DEVICE_GROUP_ID` from Task 1.
- Produces: nothing consumed by later tasks in this plan (Task 6 doesn't call into sensor.py).

- [ ] **Step 1: Write the failing test**

Read `tests/test_sensor.py` first to match its existing mocking style, then add:
```python
def test_device_info_uses_shared_group_id() -> None:
    """Two sensors with the same device_group_id share one DeviceInfo identifier."""
    from custom_components.abstractor.sensor import AbstractorSensor

    coordinator = Mock()
    entry = Mock()
    sensor_a = AbstractorSensor(
        coordinator, entry, "power", ["sensor.a"], None,
        subentry_id="subentry-a", device_group_id=None,
    )
    sensor_b = AbstractorSensor(
        coordinator, entry, "energy", ["sensor.b"], None,
        subentry_id="subentry-b", device_group_id="subentry-a",
    )

    assert sensor_a.device_info["identifiers"] == {("abstractor", "subentry-a")}
    assert sensor_b.device_info["identifiers"] == {("abstractor", "subentry-a")}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sensor.py::test_device_info_uses_shared_group_id -v`
Expected: FAIL — `AbstractorSensor.__init__` doesn't accept `subentry_id`/`device_group_id` keyword arguments yet.

- [ ] **Step 3: Rewrite sensor.py**

Replace the whole content of `custom_components/abstractor/sensor.py`:
```python
"""Sensor platform for Abstractor."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    DOMAIN,
)
from .coordinator import AbstractorDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform: one entity per Abstractor subentry."""
    coordinator: AbstractorDataUpdateCoordinator = hass.data[DOMAIN]["coordinator"]

    for subentry_id, subentry in entry.subentries.items():
        device_type = subentry.data.get(CONF_DEVICE_TYPE, "")
        # Identity (unique_id) is derived from subentry.data ONLY. subentry.data
        # is what the create/reconfigure flow writes atomically each time (see
        # config_flow.py); deriving unique_id from anything else would risk
        # changing it on reconfigure, breaking REQ-CORE-001 (stable identity /
        # unbroken recorder history across a hardware swap or device move).
        identity_source_ids = subentry.data.get(CONF_SOURCE_ENTITY_IDS) or [
            subentry.data.get(CONF_SOURCE_ENTITY_ID)
        ]
        identity_source_ids = [source for source in identity_source_ids if source]

        async_add_entities(
            [
                AbstractorSensor(
                    coordinator,
                    entry,
                    device_type,
                    identity_source_ids,
                    subentry.data.get(CONF_LEGACY_UNIQUE_ID),
                    subentry_id=subentry_id,
                    device_group_id=subentry.data.get(CONF_DEVICE_GROUP_ID),
                )
            ],
            config_subentry_id=subentry_id,
        )

class AbstractorSensor(CoordinatorEntity[AbstractorDataUpdateCoordinator], SensorEntity):
    """Abstractor Sensor Entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AbstractorDataUpdateCoordinator,
        entry: ConfigEntry,
        device_type: str,
        identity_source_ids: list[str],
        legacy_unique_id: str | None = None,
        *,
        subentry_id: str,
        device_group_id: str | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._subentry_id = subentry_id
        self._device_type = device_type
        self._identity_source_ids = identity_source_ids

        if legacy_unique_id:
            # REQ-CORE-003: migrated YAML template sensor, keep its old id.
            self._attr_unique_id = legacy_unique_id
        elif len(identity_source_ids) == 1:
            # Keep the first MVP's ID stable for existing single-source entries.
            self._attr_unique_id = f"abstractor_{identity_source_ids[0]}_{device_type}"
        else:
            self._attr_unique_id = (
                f"abstractor_{device_type}_{'_'.join(sorted(identity_source_ids))}"
            )
        self._attr_name = device_type.capitalize()
        # device_group_id set -> this sensor joins an existing device (the
        # subentry that originally registered it under this identifier).
        # Not set -> this sensor gets its own device, keyed by its own
        # subentry_id — identical to today's one-device-per-sensor default.
        device_key = device_group_id or subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            name=f"Abstract {device_type.capitalize()}",
            manufacturer="Abstractor",
            model="Abstract sensor",
        )

        if device_type == "power":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = "W"
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif device_type == "energy":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "kWh"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif device_type == "water":
            self._attr_device_class = SensorDeviceClass.WATER
            self._attr_native_unit_of_measurement = "L"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._subentry_id)
```

Note what changed: `AddEntitiesCallback` → `AddConfigEntryEntitiesCallback` (the subentry-aware type, per Home Assistant's own `kitchen_sink` reference integration), one loop iteration per subentry instead of one entity per whole entry, `config_subentry_id=subentry_id` passed to `async_add_entities`, `native_value` reads `coordinator.data[self._subentry_id]` instead of `coordinator.data[self.entry.entry_id]` (matches Task 2's coordinator key rename), and the new `device_group_id`-aware `DeviceInfo`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sensor.py -v`
Expected: all PASS, including the new test. If any pre-existing test in this file constructs `AbstractorSensor` without the new required keyword-only `subentry_id` argument, update those call sites in this same commit (they're this task's own callers, not a separate concern).

- [ ] **Step 5: Commit**

```bash
git add custom_components/abstractor/sensor.py tests/test_sensor.py
git commit -m "feat: read subentries in sensor.py, support device bundling"
```

---

### Task 6: `__init__.py` — reconciliation (migrate legacy flat entries)

**Files:**
- Modify: `custom_components/abstractor/__init__.py`
- Test: `tests/test_reconciliation.py` (new)

**Interfaces:**
- Consumes: nothing new from earlier tasks (uses `hass.config_entries.async_add`/`async_add_subentry`/`async_remove` directly — standard HA API, not project-specific).
- Produces: `_async_reconcile_legacy_entries(hass: HomeAssistant) -> None`, called once from `async_setup`.

This is the highest-risk task — it restructures real installations' data. Test it thoroughly before moving on.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reconciliation.py`:
```python
"""Test the one-time legacy-entry reconciliation (device bundling migration).

Verifies the mechanism documented in
docs/superpowers/specs/2026-08-08-device-bundling-design.md's "Migration"
section: async_setup (not async_migrate_entry, which can't restructure
across entries) converts existing flat top-level entries into subentries
under a newly-created singleton root entry.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abstractor import _async_reconcile_legacy_entries
from custom_components.abstractor.const import CONF_DEVICE_TYPE, CONF_SOURCE_ENTITY_ID, DOMAIN


async def test_reconciliation_converts_legacy_entries_to_subentries(
    hass: HomeAssistant,
) -> None:
    """Two legacy flat entries become two subentries under one new root entry."""
    legacy_a = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_power_sensor.a",
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.a"},
    )
    legacy_a.add_to_hass(hass)
    legacy_b = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_energy_sensor.b",
        data={CONF_DEVICE_TYPE: "energy", CONF_SOURCE_ENTITY_ID: "sensor.b"},
    )
    legacy_b.add_to_hass(hass)

    await _async_reconcile_legacy_entries(hass)

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    root_entry = entries[0]
    assert root_entry.unique_id == "abstractor_root"
    assert len(root_entry.subentries) == 2

    subentry_data = {s.data[CONF_SOURCE_ENTITY_ID]: s.data for s in root_entry.subentries.values()}
    assert subentry_data["sensor.a"][CONF_DEVICE_TYPE] == "power"
    assert subentry_data["sensor.b"][CONF_DEVICE_TYPE] == "energy"


async def test_reconciliation_is_idempotent(hass: HomeAssistant) -> None:
    """Running reconciliation twice (e.g. a restart after partial completion)
    does not create a second root entry or duplicate subentries."""
    legacy = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abstractor_power_sensor.a",
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.a"},
    )
    legacy.add_to_hass(hass)

    await _async_reconcile_legacy_entries(hass)
    await _async_reconcile_legacy_entries(hass)

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert len(entries[0].subentries) == 1


async def test_reconciliation_skips_fresh_install(hass: HomeAssistant) -> None:
    """No legacy entries at all -> no root entry is created by reconciliation
    (a fresh install creates the root entry through the normal config flow
    instead, the first time a user adds the integration)."""
    await _async_reconcile_legacy_entries(hass)

    assert hass.config_entries.async_entries(DOMAIN) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_reconciliation.py -v`
Expected: FAIL on all three with `ImportError: cannot import name '_async_reconcile_legacy_entries'`.

- [ ] **Step 3: Add reconciliation to `__init__.py`**

In `custom_components/abstractor/__init__.py`, add these imports at the top (alongside the existing ones):
```python
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceCall
```
(the file already imports `ConfigEntry`; add `ConfigSubentry` to that same import line.)

Add this function (place it right before `async def async_setup_entry`):
```python
async def _async_reconcile_legacy_entries(hass: HomeAssistant) -> None:
    """One-time structural migration: fold pre-bundling flat top-level
    entries into subentries under a newly-created singleton root entry.

    Not done via async_migrate_entry: that hook receives one existing
    ConfigEntry at a time and can only rewrite that entry's own data/version
    in place — it has no way for an entry to dissolve itself into a
    differently-structured entry elsewhere. This is the pattern Home
    Assistant's own kitchen_sink reference integration uses for the same
    kind of structural change (verified against its source).

    Idempotent and safe to interrupt: converts one legacy entry at a time
    (add its subentry to the root, confirm, THEN remove the legacy entry),
    so a restart mid-run just resumes with whatever legacy entries are
    still standalone — already-converted ones are untouched, since they no
    longer show up in this function's own entry scan.
    """
    existing_root = next(
        (
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.unique_id == "abstractor_root"
        ),
        None,
    )
    legacy_entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.unique_id != "abstractor_root"
    ]
    if not legacy_entries:
        return

    if existing_root is None:
        root_entry = ConfigEntry(
            domain=DOMAIN,
            title="Abstractor",
            data={},
            source="reconciliation",
            unique_id="abstractor_root",
            version=CONFIG_ENTRY_VERSION,
        )
        await hass.config_entries.async_add(root_entry)
    else:
        root_entry = existing_root

    for legacy_entry in legacy_entries:
        subentry = ConfigSubentry(
            data=dict(legacy_entry.data) | dict(legacy_entry.options),
            subentry_type="sensor",
            title=legacy_entry.title,
            unique_id=None,
        )
        hass.config_entries.async_add_subentry(root_entry, subentry)
        await hass.config_entries.async_remove(legacy_entry.entry_id)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Abstractor integration (called once for the whole domain,
    before any per-entry async_setup_entry calls)."""
    await _async_reconcile_legacy_entries(hass)
    return True

```

`CONFIG_ENTRY_VERSION` is already imported by this file's existing `from .const import (...)` block — no new import needed for it.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_reconciliation.py -v`
Expected: all 3 PASS.

Run the full unit suite to check for regressions: `pytest tests/ -v --cov=custom_components/abstractor --cov-report=term-missing`
Expected: all pass. If `test_migration.py`'s existing tests (which construct entries via `Mock(entry_id=..., version=...)`, not `MockConfigEntry`) fail because `async_migrate_entry` itself is untouched by this task, that's a pre-existing test unaffected by this change — investigate only if it actually fails; it shouldn't, since Task 6 doesn't modify `async_migrate_entry`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/abstractor/__init__.py tests/test_reconciliation.py
git commit -m "feat: reconcile legacy flat entries into subentries on setup"
```

---

### Task 7: E2E test — bundle a second sensor onto an existing device

**Files:**
- Create: `tests_e2e/test_device_bundling_e2e.py`

**Interfaces:**
- Consumes: `logged_in_page`, `hass_base_url`, `hass_bearer_token` fixtures from `tests_e2e/conftest.py` (same as every other E2E test in this suite).
- Produces: nothing consumed by later tasks — this is the last task in this plan.

- [ ] **Step 1: Write the test**

```python
"""E2E: adding a second Abstract sensor to an already-existing device
results in both sensors appearing under one Home Assistant device — the
core deliverable of docs/superpowers/specs/2026-08-08-device-bundling-design.md.
"""
from __future__ import annotations

import re

import requests


def test_second_sensor_bundles_onto_existing_device(
    logged_in_page, hass_base_url, hass_bearer_token
):
    page = logged_in_page

    # First-ever setup: adds the singleton root entry (no sensor fields).
    page.goto(f"{hass_base_url}/config/integrations/dashboard")
    page.get_by_text("Add integration", exact=False).click()
    brand_search = page.get_by_placeholder(re.compile("search for a brand", re.I))
    brand_search.fill("Abstractor")
    brand_search.press("Enter")
    page.get_by_role("button", name=re.compile("submit|ok", re.I)).click()
    page.wait_for_timeout(500)

    # Add the first sensor via the subentry "add" action on the new entry.
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name=re.compile("add sensor|add entry", re.I)).click()
    page.get_by_label(re.compile("source_entity_id|source entity$", re.I)).click()
    search_field = page.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially("Fridge Power")
    page.get_by_text("Fridge Power", exact=False).first.click()
    page.get_by_role("button", name=re.compile("submit|ok", re.I)).click()
    page.wait_for_timeout(500)

    devices_before = _abstractor_device_ids(hass_base_url, hass_bearer_token)
    assert len(devices_before) == 1, f"expected exactly one device after the first sensor, got {devices_before}"
    first_device_id = next(iter(devices_before))

    # Add the second sensor, targeting the same device this time.
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name=re.compile("add sensor|add entry", re.I)).click()
    page.get_by_label(re.compile("device_type|device type$", re.I)).click()
    page.get_by_text("Energy", exact=False).click()
    page.get_by_label(re.compile("source_entity_id|source entity$", re.I)).click()
    search_field = page.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially("Fridge Energy")
    page.get_by_text("Fridge Energy", exact=False).first.click()
    page.get_by_label(re.compile("target_device_id|device$", re.I)).click()
    search_field = page.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    page.keyboard.press("Enter")  # single existing device, only one match
    page.get_by_role("button", name=re.compile("submit|ok", re.I)).click()
    page.wait_for_timeout(500)

    devices_after = _abstractor_device_ids(hass_base_url, hass_bearer_token)
    assert devices_after == devices_before, (
        f"expected the second sensor to join the existing device {first_device_id}, "
        f"but a new device appeared: {devices_after}"
    )


def _abstractor_device_ids(hass_base_url: str, token: str) -> set[str]:
    """Distinct device_ids behind every sensor.abstract_* entity, via the
    entity registry (not the states API — device_id isn't in a state)."""
    resp = requests.get(
        f"{hass_base_url}/api/config/entity_registry/list",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return {
        e["device_id"]
        for e in resp.json()
        if e["entity_id"].startswith("sensor.abstract_") and e.get("device_id")
    }
```

Note: `/api/config/entity_registry/list` is a REST endpoint — confirm it's enabled by this project's `default_config:` in `docker/ha_config_e2e/configuration.yaml` (it is; `default_config` includes the `config` integration that registers it). If the "Add sensor"/"add entry" link's accessible name text turns out to differ from `"add sensor|add entry"` once run against a real instance, inspect the actual DOM (same troubleshooting approach documented throughout this suite's other files) and adjust the regex — this is the one part of this task not independently verified against a live HA instance during planning, since Home Assistant's subentry "add" UI's exact link text wasn't confirmed against source in this plan's research.

- [ ] **Step 2: Run it against a fresh E2E instance**

```bash
docker compose -f docker-compose.e2e.yml down -v
docker compose -f docker-compose.e2e.yml build e2e
docker compose -f docker-compose.e2e.yml up -d homeassistant
docker compose -f docker-compose.e2e.yml run --rm e2e tests_e2e/test_device_bundling_e2e.py -v
docker compose -f docker-compose.e2e.yml down -v
```
Expected: PASS. If the "add sensor" link text doesn't match, iterate per the note above — this is expected debugging, not a sign the task is wrong.

- [ ] **Step 3: Run the full E2E suite to check for regressions**

```bash
docker compose -f docker-compose.e2e.yml down -v
docker compose -f docker-compose.e2e.yml build e2e
docker compose -f docker-compose.e2e.yml up -d homeassistant
docker compose -f docker-compose.e2e.yml run --rm e2e tests_e2e/ -v
docker compose -f docker-compose.e2e.yml down -v
```
Expected: all pass, including the pre-existing tests — their `_add_device`-style helpers use the OLD "Add integration" → fill sensor form flow, which after Task 3 only creates the empty root entry. These helpers will need updating to use the new subentry "add" flow instead — treat any failure here as confirmation of that, and update the affected test files' shared add-device sequences to match Task 7 Step 1's new flow (this is expected fallout from Tasks 3-6 changing the config flow shape, not a new task — fix it here since this is the step that surfaces it).

- [ ] **Step 4: Commit**

```bash
git add tests_e2e/test_device_bundling_e2e.py tests_e2e/test_config_flow_e2e.py tests_e2e/test_net_flow_e2e.py tests_e2e/test_unique_id_stability_e2e.py tests_e2e/test_translations_e2e.py
git commit -m "test: add E2E coverage for device bundling, update flows for subentries"
```

---

## Self-Review

**Spec coverage:** Spec's requirements map to tasks as follows — bundle at creation time (Task 3's `CONF_TARGET_DEVICE_ID` field), bundle retroactively (Task 4's reconfigure step), unified flow for both new-sensor cases (Task 3), no `unique_id`/`entity_id` change (Task 5's identity derivation untouched from the original file, only `subentry_id`/`device_group_id` added), migration (Task 6), HA floor bump (Task 1), testing (unit tests in Tasks 2-6, E2E in Task 7). Out-of-scope items (naming, panel, update modes, source-fail behavior) have no corresponding task, correctly.

**Placeholder scan:** No TBD/TODO. Every step has literal, complete code or exact runnable commands. Task 7's one caveat (the "add sensor" link's exact accessible name not independently verified against a live instance) is flagged explicitly as a known research gap with a concrete fallback instruction, not glossed over.

**Type consistency:** `subentry_id` and `device_group_id` are threaded consistently: Task 2 introduces `subentry_id`-keyed coordinator dicts; Task 3/4 write `CONF_DEVICE_GROUP_ID` into subentry `data`; Task 5's `AbstractorSensor.__init__` accepts both as keyword-only args with the same names; Task 6 doesn't touch either (it only moves data, doesn't read sensor-level fields). `async_add_entities` signature (`AddConfigEntryEntitiesCallback`) is consistent between Task 5's import and its usage.
