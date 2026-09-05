# Architecture — AbstrHActor

Code-accurate reference for the implemented architecture of the
`custom_components/abstractor` integration. Verified against the source on
2026-08-16 (branch `feat/audit-ui-config`). This is not a roadmap and not a
changelog — it describes what the code actually does today. All evidence is
cited as `file:line` against the current working tree.

---

## 1. Module map

| Module | Responsibility |
|---|---|
| `const.py` | Domain name, root-entry identity, all `CONF_*` keys, option defaults and bounds |
| `config_flow.py` | Root entry flow, `AbstractorOptionsFlow`, sensor subentry create/reconfigure flow |
| `coordinator.py` | `AbstractorDataUpdateCoordinator` (`config_entry=None`, survives subentry reloads); filter pipelines; optional Influx write path |
| `filters.py` | Filter pipeline per subentry (spike, invert, fallback, net-subtract) |
| `sensor.py` | `AbstractorSensor` (CoordinatorEntity) — one entity per subentry; `DeviceInfo` from options |
| `__init__.py` | Lifecycle (`async_setup_entry`/`async_unload_entry`), legacy-entry reconciliation, services, snapshot persistence, panel registration |
| `influx_exporter.py` | InfluxDB v2 line-protocol push + `create_influx_exporter` factory (REQ-DATA-002) |
| `diagnostics.py` | Config-entry diagnostics with Influx token masking |
| `frontend.py` | Static path + sidebar panel registration (read-only) |
| `repository/device_registry.py` | In-memory `DeviceRegistry` (name/manufacturer/model) |
| `www/abstractor-panel.js` | Dependency-free Web Component, read-only device overview |

## 2. Runtime path

```
HA Config Flow (root entry + sensor subentries)
  → AbstractorDataUpdateCoordinator        (singleton, config_entry=None, survives reloads)
      ├─ AbstractorFilterPipeline          (one per subentry)
      └─ InfluxExporter                    (optional, built from options when host+token set)
  → AbstractorSensor (CoordinatorEntity)   (one per subentry; DeviceInfo from options)
  → Sidebar panel                          (frontend.py + www/abstractor-panel.js, read-only)
```

Everything hangs off a **single root config entry**; every sensor is a
**subentry** under it. Polling is central (one coordinator), state is
dispatched to entities via `CoordinatorEntity`, and all configuration happens
through the config/options flow — the sidebar panel is deliberately read-only.

---

## 3. Contract: empty-root / singleton design

- **Identity.** The singleton parent entry is identified by
  `ROOT_UNIQUE_ID = "abstractor_root"` with title `"Abstractor"`
  (`const.py:9-10`). Both the config flow and the legacy-entry reconciliation
  key on that exact value.
- **Creation.** `AbstractorConfigFlow.async_step_user` sets the unique id,
  aborts when it is already configured, and creates the root entry with
  `data={}` — the setup form collects nothing (`config_flow.py:90-100`). The
  root entry is pure structure: it carries no sensor configuration.
- **No YAML schema.** `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`
  (`__init__.py:54`) — the integration is configured through the UI only;
  `async_setup` exists solely for the one-time legacy reconciliation.
- **Sensors live in subentries.** `async_get_supported_subentry_types` exposes
  exactly one type, `SUBENTRY_TYPE_SENSOR`, handled by
  `AbstractorSensorSubentryFlowHandler` (`config_flow.py:102-108`). Each sensor
  is a subentry; the platform creates one `AbstractorSensor` per subentry
  (`sensor.py:43-68`).
- **Coordinator deliberately has no config entry.** It is constructed with
  `config_entry=None` (`coordinator.py:52-58`) to opt out of HA's automatic
  "shut down when the current entry unloads" hook (`config_entries.current_entry`
  would otherwise resolve to the singleton root). Every subentry add/remove/
  reconfigure reloads that same root entry, so the coordinator must survive
  those reloads; a full teardown is gated on `coordinator.subentry_data` being
  empty (`__init__.py:489-508`). `async_setup_entry` reuses the existing
  coordinator on reload (`__init__.py:392-396`) and re-applies options on every
  (re)setup.
- **Historical migration.** Pre-bundling flat top-level entries are folded into
  subentries of the root by `_async_reconcile_legacy_entries`
  (`__init__.py:323-374`); `_async_promote_to_root` turns the healthiest legacy
  entry into the root in place, preserving entry_id, unique_ids, entity_ids and
  device identifiers (`__init__.py:293-320`).

---

## 4. Contract: OptionsFlow

`AbstractorOptionsFlow` (`config_flow.py:111-226`) is hooked to the root entry
via `AbstractorConfigFlow.async_get_options_flow` (`config_flow.py:84-88`). It
is the single place where integration-level (non-sensor) settings are
configured.

### Steps

| Step | Trigger | Contents |
|---|---|---|
| `async_step_init` (`config_flow.py:118-192`) | opening Configure on the root entry | all seven fields below |
| `async_step_poll_interval` (`config_flow.py:194-226`) | selecting **custom** in the interval Select | a single bounded `NumberSelector`, min 1 / max 3600, step 1 |

The custom-interval step stashes the already-submitted fields in
`self._pending_options` (`config_flow.py:133-139`) and only writes the entry
after the number is collected. Persisted options are
`dict(DEFAULT_OPTIONS) | submitted` (`config_flow.py:141-143`, `201-203`), so
defaults always fill gaps. Re-opening reflects a non-preset current interval as
"custom" with the number pre-filled (`config_flow.py:123-128`).

### Fields

| Field | Selector | Default | Notes |
|---|---|---|---|
| `poll_interval` | Select (2 / 5 / 30 / custom) | 30 | presets `POLL_INTERVAL_PRESETS` (`const.py:53`); custom reveals Number bounded by `POLL_INTERVAL_MIN`/`POLL_INTERVAL_MAX` = 1..3600 (`const.py:54-55`) |
| `influx_host` | Text | "" | |
| `influx_token` | Text, `PASSWORD` type (`config_flow.py:163-169`) | "" | masked in the UI |
| `influx_org` | Text | "" | |
| `influx_bucket` | Text | "" | |
| `device_name` | Text | `"Abstract {device_type}"` (`const.py:56`) | `{device_type}` placeholder substituted per sensor (`sensor.py:109-111`) |
| `device_manufacturer` | Text | `"Abstractor"` (`const.py:57`) | |
| `device_model` | Text | `"Abstract sensor"` (`const.py:58`) | |

### Storage caveat (honest)

Options are stored **plaintext** in HA's `.storage/core.config_entries` — HA
has no at-rest encryption for config-entry options. "Secret-safe" handling of
the Influx token therefore means **UI masking + log/diagnostics hygiene, not
encryption**:

- the token uses a password selector so the UI masks it (`config_flow.py:163-169`);
- diagnostics redact it to `"***"` in the `entry.as_dict()` copy
  (`diagnostics.py:20-23`);
- it is never logged — the exporter logs only bucket/entity_id/value
  (`influx_exporter.py:57`, `84-93`).

### Application on (re)load

- **Polling interval:** `coordinator.set_update_interval(...)` is called on
  every setup with `entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)`
  (`__init__.py:401-403`). The method sets `self.update_interval` and reschedules
  the timer via the in-class `_unsub_refresh`/`_schedule_refresh` seams
  (`coordinator.py:64-80`), falling back to `async_request_refresh()` where those
  are unavailable.
- **InfluxExporter:** `coordinator.influx_exporter = create_influx_exporter(hass, dict(entry.options))`
  on every setup (`__init__.py:404`). The factory returns `None` unless
  `influx_host` **and** `influx_token` are both non-empty (`influx_exporter.py:23-38`);
  the write path is gated on the instance (`coordinator.py:125-126`) and cleared
  on unload (`__init__.py:494`).
- **Device presentation:** `sensor.py` reads `device_name`/`device_manufacturer`/
  `device_model` from `entry.options` (defaults from `const.py:56-58`) into
  `DeviceInfo` with identifiers `{(DOMAIN, device_key)}` where
  `device_key = device_group_id or subentry_id` (`sensor.py:108-121`), and
  populates the in-memory `DeviceRegistry` with the same values
  (`sensor.py:122-124`).
- **Options change trigger:** the update listener `_async_options_updated`
  reloads the entry, which re-applies everything above (`__init__.py:548-550`).

---

## 5. Contract: sidebar panel

- **Registration.** `frontend.py` serves the static JS file
  (`www/abstractor-panel.js`) and registers a built-in sidebar panel titled
  "Abstractor" (`mdi:layers-outline`) via `async_register_panel` /
  `async_unregister_panel` (`frontend.py:27-65`, `68-107`), called from
  `async_setup_entry`/`async_unload_entry` (`__init__.py:462`, `508`).
- **Read-only, no write API.** `frontend.py` only registers a static path and
  the panel — there is no REST, websocket, or write endpoint. The panel's
  subtitle states: "read-only overview. Configure via Settings → Devices &
  Services" (`abstractor-panel.js:93-95`).
- **Identifier-based device filter.** The panel filters HA's device registry
  (`hass.devices`) by the integration identifier —
  `d.identifiers.some((id) => id[0] === 'abstractor')` (`abstractor-panel.js:34`).
  It is deliberately **not** manufacturer-based, because `device_manufacturer`
  is now configurable via the OptionsFlow.
- **Rendering.** One card per Abstractor device showing name (user override
  falls back to the registry name), manufacturer, and model
  (`abstractor-panel.js:47-53`, `107-117`), plus a table of that device's
  Abstractor entities with current state and unit. All registry/state values are
  inserted via `textContent`, never interpolated into markup
  (`abstractor-panel.js:82-85`).
- **No registry API.** The panel reads HA's own device registry (`hass.devices`);
  it has no access path to the in-memory `DeviceRegistry` and does not need one —
  options flow into `DeviceInfo` → HA device registry → panel.
- **Configuration surface.** All configuration happens exclusively through the
  HA Config Flow / OptionsFlow (Settings → Devices & Services); the panel does
  not duplicate it.

---

## 6. Related documents

| Document | Relation |
|---|---|
| `docs/AUDIT_UI_CONFIG.md` | UI-mapping audit that motivated the OptionsFlow/registry/panel changes (resolved 2026-08-16) |
| `docs/plan-audit-ui-config.md` | Implementation plan for activating the dormant surfaces (scope + decisions) |
| `docs/REQUIREMENTS.md` | Requirement baseline (owned by the Requirements Engineer) |
| `README.md` | Project overview, setup, commands |
