# Plan: Activate Dormant Config Surfaces of Abstractor

- **Date:** 2026-08-15
- **Source:** `docs/AUDIT_UI_CONFIG.md` (P0/P2/P3 recommendations) + user-scope decisions (binding)
- **Branch:** `feat/audit-ui-config`
- **Status:** ready for implementation
- **Effort:** deferred to `effort-estimator` (text reference only — not computed in this plan)

## Scope (binding — implement exactly this, no more)

1. **Activate dormant paths + UI:**
   - **InfluxExporter** (`influx_exporter.py: host/token/org/bucket`) — instantiate, attach to the
     coordinator (`coordinator.influx_exporter` is hardcoded `None` at `coordinator.py:60`), and
     enable the write path already gated at `coordinator.py:106-107`. Expose the 4 fields in a new
     OptionsFlow, stored via HA ConfigEntry options with secret-safe handling for the token.
   - **DeviceRegistry** (`repository/device_registry.py: name/manufacturer/model`) — wire
     `register_device` into the device lifecycle, make the fields configurable via OptionsFlow, and
     display them in the read-only sidebar panel.
2. **New OptionsFlow** (`async_step_init`/custom-interval step) on the ROOT `AbstractorConfigFlow`:
   - Polling interval: Select presets 2/5/30 s + a "custom" option that reveals a Number field
     (bounded). `coordinator.update_interval` must be read from options (not the hardcoded
     `timedelta(seconds=30)`).
   - Influx fields + registry fields (from 1).
   - Must accommodate the singleton root entry (`data={}`) cleanly.
3. **GH#18 fields NOT re-added** — `target_device_id` / `create_new_device` stay removed; only the
   existing doc comments (`config_flow.py:159-164, 210-218, 269-274`) remain maintained.
4. **Docs:** extend `docs/ARCHITECTURE.md` (empty-root/singleton design, OptionsFlow contract, panel
   contract) and mark `docs/AUDIT_UI_CONFIG.md` as done/resolved.
5. **DoD:** TDD, config-flow tests stay at 100 % coverage, Ruff/PEP8, Conventional Commits (English).

> **Note on step 4:** `docs/ARCHITECTURE.md` does **not** exist in this repo today (SYSTEM_AUDIT
> already flags it as absent; `AGENTS.md` references it but it was never created). Step 11 therefore
> *creates* it rather than extends it. Flagged as an open question at the end.

## HA-native patterns chosen (decisions)

### A. Options storage of Influx credentials
- Store all four fields in the **root entry's `options`** (never `data`) via `OptionsFlow.async_create_entry`.
- **Token** field uses a **password selector**
  (`selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))`) so
  the HA UI masks it and never echoes it back on a validation re-render.
- **Redact the token from diagnostics**: `diagnostics.py` currently returns `entry.as_dict()`, which
  would leak `options[influx_token]`. Step 8 masks it.
- **Never log the token** (the existing exporter already logs only `bucket`/`entity_id`/`value`).
- **Honest limitation:** HA has **no encryption-at-rest** for config entry options — they live as
  plaintext in `.storage/core.config_entries`. "Secret-safe" therefore means UI masking + log/diagnostics
  hygiene, not encryption. This matches HA core's own integrations (e.g. influxdb, mqtt store
  credentials in options as plaintext).

### B. Coordinator interval update
- Keep `config_entry=None` (must survive subentry reloads — see `coordinator.py` docstring).
- Do **not** recreate the coordinator on options change. Instead add an in-class
  `set_update_interval(seconds: int)` method that sets `self.update_interval = timedelta(seconds=...)`
  and **cancels + reschedules** the periodic timer via the coordinator's own `_schedule_refresh()`
  (private-but-in-class access is the accepted HA pattern). `_async_options_updated` already reloads
  the entry on options change, so `async_setup_entry` re-applies options on every (re)load.
- **Verify against the installed HA** (`DataUpdateCoordinator` internals vary across 2025.3.0 →
  2026.8.x): the worker must confirm `_unsub_refresh`/`_schedule_refresh` are the correct reschedule
  seam for the pinned/installed version; if not, fall back to `update_interval` mutation + a fresh
  `async_request_refresh()`.

### C. DeviceRegistry wiring
- Device creation happens in `sensor.py` when each `AbstractorSensor` builds its `DeviceInfo`
  (`device_key = device_group_id or subentry_id`, identifiers `{(DOMAIN, device_key)}`).
- Populate the in-memory registry there via `registry.register_device(device_key, name, manufacturer, model)`
  using option-driven `manufacturer`/`model` (defaults `"Abstractor"` / `"Abstract sensor"`) and the
  same derived `name` used in `DeviceInfo`.
- The **panel has no API to the in-memory registry** (read-only, no REST/websocket — `frontend.py`).
  It reads HA's own device registry via `hass.devices`. So "display in panel" is satisfied by
  (a) options → `DeviceInfo` → HA device registry, and (b) rendering `manufacturer`/`model`/`name` on
  each card. The panel's current filter `d.manufacturer === 'Abstractor'` **breaks once manufacturer
  becomes configurable**, so it is switched to an **identifier-based filter**
  (`d.identifiers.some(id => id[0] === 'abstractor')`).

## New constants (`const.py`)

```python
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_INFLUX_HOST: Final = "influx_host"
CONF_INFLUX_TOKEN: Final = "influx_token"
CONF_INFLUX_ORG: Final = "influx_org"
CONF_INFLUX_BUCKET: Final = "influx_bucket"
CONF_DEVICE_MANUFACTURER: Final = "device_manufacturer"
CONF_DEVICE_MODEL: Final = "device_model"

DEFAULT_POLL_INTERVAL: Final = 30
POLL_INTERVAL_PRESETS: Final = (2, 5, 30)
POLL_INTERVAL_MIN: Final = 1
POLL_INTERVAL_MAX: Final = 3600
DEFAULT_DEVICE_MANUFACTURER: Final = "Abstractor"
DEFAULT_DEVICE_MODEL: Final = "Abstract sensor"
DEFAULT_OPTIONS: Final[dict[str, Any]] = {
    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
    CONF_DEVICE_MANUFACTURER: DEFAULT_DEVICE_MANUFACTURER,
    CONF_DEVICE_MODEL: DEFAULT_DEVICE_MODEL,
}
```

## Ordered steps

| # | Step | Agent | Depends on | Acceptance criteria |
|---|---|---|---|---|
| 1 | Add the new `CONF_*` keys and option defaults listed above to `custom_components/abstractor/const.py` | `developer` | — | `python -c "import custom_components.abstractor.const"` succeeds; each new key is `Final`-typed and referenced nowhere else yet; Ruff passes. |
| 2 | Add `AbstractorOptionsFlow(config_entries.OptionsFlow)` to `custom_components/abstractor/config_flow.py` and hook it via `AbstractorConfigFlow.async_get_options_flow`. `async_step_init` renders all fields (interval Select 2/5/30/custom, 4 Influx fields with password token, 2 registry fields). If `poll_interval == "custom"`, stash the submitted input and show `async_step_poll_interval` (bounded `NumberSelector`, `POLL_INTERVAL_MIN..POLL_INTERVAL_MAX`). Otherwise write `DEFAULT_OPTIONS | submitted` into options. Re-opening reflects a non-preset current interval as "custom" with the Number field pre-filled. GH#18 fields are NOT reintroduced. | `senior-developer` | 1 | `test_form` still passes; a new options-flow happy-path test renders the init form with defaults; saving a preset persists `options[CONF_POLL_INTERVAL] == 2/5/30`; selecting "custom" transitions to a second form with a Number field; saving the number persists an integer interval; a re-open with interval `7` shows "custom" selected and `7` pre-filled. |
| 3 | Add an `"options"` top-level block to `custom_components/abstractor/strings.json` with `step.init`, `step.poll_interval`, and `data`/`data_description` entries for `poll_interval`, `influx_host`, `influx_token`, `influx_org`, `influx_bucket`, `device_manufacturer`, `device_model` | `developer` | 1 | `hassfest` translation validation passes (or manual JSON parse); every selector key in the OptionsFlow has a matching `data` translation; no `unknown`/missing-string warnings in the config flow. |
| 4 | In `custom_components/abstractor/coordinator.py`: drop the hardcoded `update_interval=timedelta(seconds=30)` in favor of `DEFAULT_POLL_INTERVAL`; add `set_update_interval(seconds: int)` that sets `self.update_interval` and cancels + re-`_schedule_refresh()`; leave `config_entry=None` untouched. | `senior-developer` | 1 | A unit test constructs the coordinator, calls `set_update_interval(7)`, and asserts `coordinator.update_interval == timedelta(seconds=7)` and that the reschedule seam was invoked; `config_entry` binding is still `None`. |
| 5 | Add `create_influx_exporter(hass, options) -> InfluxExporter \| None` to `custom_components/abstractor/influx_exporter.py`: obtains the session via `hass.helpers.aiohttp_client.async_get_clientsession(hass)` and returns an instance **only when** `influx_host` and `influx_token` are both non-empty; returns `None` otherwise. | `developer` | 1 | Unit test: returns `InfluxExporter` when host+token set; returns `None` when token or host empty; the exporter's `async_push` still posts to the host/org/bucket from options (reuse existing `test_influx_exporter.py` mocks). |
| 6 | In `custom_components/abstractor/__init__.py` `async_setup_entry`: after ensuring the coordinator exists, call `coordinator.set_update_interval(int(entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)))` and assign `coordinator.influx_exporter = create_influx_exporter(hass, entry.options)` **on every setup** (new + reload). In `async_unload_entry`, set `coordinator.influx_exporter = None` alongside existing teardown. | `senior-developer` | 4, 5 | Lifecycle test: with host+token options set, `coordinator.influx_exporter` is an `InfluxExporter` after setup; with them absent it is `None`; changing options (reload) rebuilds it; unloading clears it; `coordinator.update_interval` reflects the option. |
| 7 | In `custom_components/abstractor/sensor.py`: read `entry.options` for `CONF_DEVICE_MANUFACTURER`/`CONF_DEVICE_MODEL` (fallback to defaults) and pass them into `DeviceInfo(manufacturer=..., model=...)`; call `hass.data[DOMAIN].get("registry")` and, if present, `register_device(device_key, name, manufacturer, model)`. | `developer` | 1, 6 | Updated `test_sensor.py`: `device_info["manufacturer"]`/`["model"]` come from options (and fall back to defaults when absent); a mocked registry's `register_device` is called with the correct `device_key`, name, manufacturer, model. Existing sensor tests still pass (fixtures gain a registry mock or a `.get()` guard). |
| 8 | In `custom_components/abstractor/diagnostics.py`: mask `options[CONF_INFLUX_TOKEN]` (e.g. `"***"`) in the `entry.as_dict()` copy before returning. | `developer` | 1 | A diagnostics test asserts the returned dict never contains the raw token value; the token field is present but masked. |
| 9 | In `custom_components/abstractor/www/abstractor-panel.js`: switch the device filter from `manufacturer === 'Abstractor'` to identifier-based (`identifiers.some(id => id[0] === 'abstractor')`); render `manufacturer`/`model` on each device card alongside `name`. (`frontend.py` itself needs no change.) | `developer` | 7 | Manual/visual verification (no JS test harness): devices still appear in the panel after a configurable manufacturer is set, and each card shows name + manufacturer + model. Flagged as manual-only risk below. |
| 10 | Extend the test suite (`tests/test_config_flow.py` — keep **100 % coverage** — plus `tests/test_coordinator.py`, `tests/test_sensor.py`, `tests/test_lifecycle.py`, `tests/test_influx_exporter.py`) to cover: options-flow form + preset save, custom-interval reveal + save, out-of-bounds/validation path, current-value prefill, `set_update_interval`, exporter build/skip, registry populate, token redaction. | `tester` | 2, 4, 5, 6, 7, 8 | `pytest tests/ -v --cov=custom_components/abstractor --cov-report=term-missing` green; `config_flow.py` reports 100 % coverage; no coverage regression in touched modules. |
| 11 | Create `docs/ARCHITECTURE.md` documenting the empty-root/singleton design, the OptionsFlow contract (fields, two-step custom interval, options storage + token handling), and the panel contract (read-only, identifier-based, P3). Add a "Done/resolved" header to `docs/AUDIT_UI_CONFIG.md` with a one-line summary of what landed. | `documenter` | 2, 6, 9 | `docs/ARCHITECTURE.md` exists and states the three contracts; `docs/AUDIT_UI_CONFIG.md` is marked resolved; no stale claims remain about "no OptionsFlow exists". |

## Open questions / risks

1. **`docs/ARCHITECTURE.md` is missing** — step 11 creates it rather than extends it. Confirm the
   orchestrator accepts "create" as the interpretation of "extend".
2. **No at-rest encryption for options** — the Influx token will be plaintext in
   `.storage/core.config_entries`. Mitigated via password selector + diagnostics redaction + no
   logging, but if a stronger guarantee is required, a separate secret store (e.g. HA's
   `hass.helpers.storage` or an OS keyring) would be needed — currently out of scope.
3. **`DataUpdateCoordinator` reschedule seam** — `_schedule_refresh()`/`_unsub_refresh` are private
   and version-sensitive; the worker must verify against the installed HA (2025.3.0 floor, 2026.8.x
   observed) and fall back to `update_interval` mutation + `async_request_refresh()` if needed.
4. **DeviceRegistry `name` configurability** — `name` is inherently per-device (derived from
   `device_type`); this plan makes `manufacturer`/`model` configurable and keeps `name` derived,
   populating the registry's `name` field with the derived value. If the intent was for `name` to be
   a user-settable field, add a `device_name_prefix` option (default `"Abstract"`) — confirm before
   implementation.
5. **Panel JS is untested** — the identifier-filter + manufacturer/model rendering change has no
   Python test harness; verified manually only. Consider a minimal DOM-level smoke test if the
   `e2e-tester`/Playwright stack is available.
6. **Existing sensor test fixtures** (`tests/test_sensor.py`) set `hass.data = {DOMAIN: {"coordinator": ...}}`
   without a `registry` key — step 7 must either extend the fixtures or guard with `.get("registry")`.
7. **No commits without separate approval** — per scope item 5, this plan stops at "code + tests +
   docs green"; commit/branch hygiene is a separate, approved `git` step.

## Persisted to

`docs/plan-audit-ui-config.md` (chosen over `knowledge/wiki/plans/<topic>.md` because the Knowledge
Engine's `allowed-types`/`schema.md` define no `Plan` concept type — writing there would produce a
non-conforming OKF artifact; `docs/` matches the existing `docs/` plan/audit convention).
