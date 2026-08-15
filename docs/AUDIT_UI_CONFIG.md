# Audit: Does the HA UI Map the Complete Configuration Surface of Abstracted Devices?

- **Date:** 2026-08-15
- **Type:** Read-only audit (no source code modified, no git operations)
- **Scope:** `custom_components/abstractor` — config-flow surface vs. HA-UI reachability for
  abstracted device (sensor) configuration
- **Auditor:** Documentation Agent (`documenter`), on behalf of the orchestrator

---

## Resolution (2026-08-16)

> **RESOLVED** on branch `feat/audit-ui-config`. The dormant surfaces called out in §4(a) and the
> P0/P2/P3 recommendations of §5 are implemented. The audit body below is preserved as the
> historical record of the state on 2026-08-15; where it still reads "no OptionsFlow exists" or
> lists the Influx/registry/polling surfaces as dormant, that text is superseded by this note.

What landed:

- **InfluxExporter is now instantiated and wired.** `create_influx_exporter` builds it from the
  root entry's options whenever `influx_host` + `influx_token` are set, and it is attached to the
  coordinator on every setup (`__init__.py:404`); the previously gated write path is live
  (`coordinator.py:125-126`). The four fields are exposed via the new OptionsFlow; the token uses a
  password selector, is masked in diagnostics (`diagnostics.py:20-23`), and is never logged.
- **DeviceRegistry is now populated and configurable.** `sensor.py` registers each device from
  options-derived name/manufacturer/model (`sensor.py:122-124`); the three presentation fields
  (`device_name`/`device_manufacturer`/`device_model`) are OptionsFlow-configurable.
- **Polling interval is now configurable via OptionsFlow** (Select presets 2/5/30 + a bounded
  "custom" Number 1..3600). `coordinator.update_interval` is applied from options via
  `set_update_interval` on every setup (`__init__.py:401-403`, `coordinator.py:64-80`).
- **Panel filter is now identifier-based** (`identifiers.some(id => id[0] === 'abstractor')`,
  `www/abstractor-panel.js:34`), so the panel keeps listing devices when a custom manufacturer is
  set, and renders name + manufacturer + model per device card.
- **`docs/ARCHITECTURE.md` now documents the three contracts** (empty-root/singleton design,
  OptionsFlow contract, panel contract) — see that file for the current reference.

---

## 1. Executive Summary

**Coverage: 91.7 %** — of the 12 distinct config dimensions that are *functional* and
*persisted* in the current data model, **11 are reachable through the Home Assistant UI**
(11 / 12). The single unreachable dimension is `device_group_id`, which is internal-only by
design (flow-managed carry-forward, never user-settable). All 11 user-settable sensor fields
(100 %) are exposed through the sensor subentry create/reconfigure flows under
Settings → Devices & Services.

**Verdict:** The UI mapping of the *active* configuration surface is essentially complete.
The integration deliberately ships a slim UI: the root setup form is empty
(`config_flow.py:76-79`), there is no OptionsFlow, no YAML configuration
(`CONFIG_SCHEMA = cv.config_entry_only_config_schema`, `__init__.py:51`), and the custom
sidebar panel is a read-only overview (`www/abstractor-panel.js:87-89`). The remaining gaps
are concentrated in *dormant/inert* code paths — an uninstantiated InfluxExporter, a
never-populated DeviceRegistry, and two device-bundling fields removed from the form
(GH#18) — none of which affect runtime behaviour today. No user-facing configuration is
silently locked away; the only truly unconfigurable runtime parameter (polling interval,
hardcoded 30 s at `coordinator.py:56`) is a constant, not a config dimension. The verdict is
"complete for the intended UI scope", with the caveat that any future activation of the
dormant Influx/registry paths must add corresponding UI, and that device bundling is
currently only adjustable by recreating a sensor.

---

## 2. Methodology

### Question
Does the HA UI (config flow, options flow, entity dialog, panel) map the complete
configuration surface of abstracted devices?

### Definitions
- **Config dimension:** one discrete, externally-meaningful setting a user could plausibly
  want to view or change for an abstracted device.
- **Functional dimension:** a dimension that is (a) actually persisted in the subentry data
  model AND (b) has a runtime effect (read by `coordinator.py`/`sensor.py`).
- **UI-reachable:** the user can set or modify the value through a supported HA surface
  (config-flow form, options flow, entity dialog, panel, or integration service) without
  editing files.

### Denominator (12)
Distinct **functional + persisted** config dimensions carried in the sensor subentry data:

| # | Dimension |
|---|-----------|
| 1–11 | `device_type`, `source_entity_id`, `source_entity_ids`, `legacy_unique_id`, `spike_filter`, `invert`, `fallback_zero`, `net_subtract_entity_id`, `fallback_source_entity_id`, `fallback_condition_entity_id`, `fallback_condition_state` (schema at `config_flow.py:285-311`) |
| 12 | `device_group_id` (persisted, functionally bundles the sensor to a device; only ever set by flow logic, never by a form field — `config_flow.py:257-258`) |

### Numerator (11)
Dimensions the user can set/modify through the HA UI — the 11 sensor fields, all offered in
both the create (`async_step_user`, `config_flow.py:93-114`) and reconfigure
(`async_step_reconfigure`, `config_flow.py:130-179`) subentry flows of
`AbstractorSensorSubentryFlowHandler`.

**Coverage = 11 / 12 = 91.7 %**

### Excluded from the denominator (explicitly NOT counted against coverage)
Dimensions that exist in code but have **no current runtime effect** — they are inert,
dormant, or constants, and including them would misrepresent the active surface:

- `target_device_id`, `create_new_device` — removed from the form (GH#18), and `_normalize`
  pops them out of the persisted data (`config_flow.py:248-249`), so no current entry can
  carry them. Dead code paths documented at `config_flow.py:159-164` and `210-218`.
- `DeviceRegistry.name/manufacturer/model` — fields defined in
  `repository/device_registry.py:11-17`, but `register_device` is never called anywhere in
  the codebase; the registry is instantiated (`__init__.py:396`) and never populated.
- `InfluxExporter(host, token, org, bucket)` — class defined (`influx_exporter.py:17-29`),
  never instantiated; `coordinator.influx_exporter` is hardcoded `None`
  (`coordinator.py:60`).
- Polling interval (30 s) — a hardcoded constant (`coordinator.py:56`), not a config field.

### Sensitivity / alternative readings
- **100 % of user-settable fields** are UI-reachable (11/11). The 91.7 % figure is strictly
  attributable to `device_group_id`, which is deliberately flow-managed.
- If the dormant/inert dimensions above were counted as "unmapped", coverage would drop to
  ~50 % (11/22) — that figure is reported here for transparency only and is **not** the
  audit's headline, because none of those dimensions is functional today.

### Assumptions
- HA core's own per-entity dialog (friendly name / icon / area / enabled toggle) counts as a
  UI surface for entities — but it is provided by HA core, not by this integration, and is
  therefore excluded from the integration's own mapping assessment.
- The two integration services (`export_data`, `import_data`) are write-capable but do not
  configure devices: `export_data` takes no parameters (`__init__.py:442-446`),
  `import_data` accepts a validated snapshot and explicitly does **not** recreate config
  entries (`__init__.py:579-585`). Neither contributes config dimensions.

---

## 3. Coverage Table

Legend — **Layer:** where the dimension lives. **Settable:** a user can set it via any
supported path. **UI-reachable:** reachable through a supported HA UI surface of this
integration. Evidence cited as `file:line`.

| # | Config dimension | Layer | Settable | UI-reachable | UI path | Evidence |
|---|------------------|-------|----------|--------------|---------|----------|
| 1 | `device_type` | Subentry data (sensor) | Yes | Yes | Create/reconfigure subentry → dropdown selector | `config_flow.py:286-291` |
| 2 | `source_entity_id` | Subentry data | Yes | Yes | Create/reconfigure → entity selector | `config_flow.py:292` |
| 3 | `source_entity_ids` | Subentry data | Yes | Yes | Create/reconfigure → multi-entity selector | `config_flow.py:293-295` |
| 4 | `legacy_unique_id` | Subentry data | Yes (set once; pinned afterwards) | Yes (create only; field hidden once pinned) | Create/reconfigure → text selector; dropped from form when pinned | `config_flow.py:297-298`, `172-174` |
| 5 | `spike_filter` | Subentry data | Yes | Yes | Create/reconfigure → boolean (default False) | `config_flow.py:301` |
| 6 | `invert` | Subentry data | Yes | Yes | Create/reconfigure → boolean (default False) | `config_flow.py:302` |
| 7 | `fallback_zero` | Subentry data | Yes | Yes | Create/reconfigure → boolean (default False) | `config_flow.py:303` |
| 8 | `net_subtract_entity_id` | Subentry data | Yes | Yes | Create/reconfigure → entity selector | `config_flow.py:304` |
| 9 | `fallback_source_entity_id` | Subentry data | Yes | Yes | Create/reconfigure → entity selector | `config_flow.py:305` |
| 10 | `fallback_condition_entity_id` | Subentry data | Yes | Yes | Create/reconfigure → entity selector | `config_flow.py:306-308` |
| 11 | `fallback_condition_state` | Subentry data | Yes | Yes | Create/reconfigure → text selector | `config_flow.py:309` |
| 12 | `device_group_id` | Subentry data | No (flow-managed carry-forward only) | No | — (set automatically by `_normalize` from prior data) | `config_flow.py:257-258` |
| — | `target_device_id` | Removed from form (GH#18) | No | No | — (never rendered; popped at `_normalize`) | `config_flow.py:159-164`, `248` |
| — | `create_new_device` | Removed from form (GH#18) | No | No | — (never rendered; popped at `_normalize`) | `config_flow.py:159-164`, `249` |
| — | `DeviceRegistry.name/manufacturer/model` | In-memory repository | No | No | — (never populated; `register_device` uncalled) | `repository/device_registry.py:11-17`, `__init__.py:396` |
| — | `InfluxExporter.host/token/org/bucket` | Runtime class (uninstantiated) | No | No | — (`coordinator.influx_exporter` hardcoded `None`) | `influx_exporter.py:17-29`, `coordinator.py:60` |
| — | Polling interval (30 s) | Coordinator constant | No | No | — (hardcoded) | `coordinator.py:56` |
| — | Root entry (`data={}`, `options={}`) | Root config entry | No (empty by design) | No (empty form) | Root setup form is blank; no OptionsFlow exists | `config_flow.py:76-79`, `__init__.py:315-316` |
| — | Entity friendly name / icon / area / enabled | HA core entity registry | Yes | Yes | HA core entity dialog (per entity, not integration) | provided by HA core — outside integration code |

> **Update (2026-08-16):** the `—` rows for `DeviceRegistry.name/manufacturer/model`,
> `InfluxExporter.host/token/org/bucket`, and the polling interval are now **functional and
> UI-reachable**: all of them are configured through the new OptionsFlow on the root entry (see
> Resolution above). The rows are retained as the historical 2026-08-15 snapshot.

**Non-dimension surfaces (verified, no config impact):**
- No OptionsFlow: no `async_step_options` exists anywhere in `config_flow.py`.
  > **Update (2026-08-16):** superseded — `AbstractorOptionsFlow`
  > (`async_step_init` + `async_step_poll_interval`) now exists and is hooked via
  > `AbstractorConfigFlow.async_get_options_flow`; see `docs/ARCHITECTURE.md` §4.
- No YAML configuration: `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`
  (`__init__.py:51`).
- Sidebar panel is 100 % read-only: subtitle "read-only overview. Configure via Settings →
  Devices & Services." (`www/abstractor-panel.js:87-89`); `frontend.py` only registers a
  static path and the sidebar panel (`frontend.py:27-65`) — no REST/websocket/write API.
- Services do not configure: `export_data` (no params, `__init__.py:442-446`),
  `import_data` (validated `data` param, `__init__.py:447-452`); import does not recreate
  config entries (`__init__.py:585`).

---

## 4. Gap Analysis

### (a) Dormant / unwired — code exists, no runtime effect, no UI
> **Update (2026-08-16):** this gap class is **resolved** — the InfluxExporter and DeviceRegistry
> rows below are now activated and UI-mapped via the new OptionsFlow (see Resolution above and
> `docs/ARCHITECTURE.md` §4). The rows are kept as the historical record.
| Gap | Evidence | Impact | Recommendation |
|-----|----------|--------|----------------|
| `InfluxExporter` config (host/token/org/bucket) | Class defined `influx_exporter.py:17-29`; never instantiated; `coordinator.influx_exporter = None` (`coordinator.py:60`); write path gated on it (`coordinator.py:106-107`) | None today — export is dead code; if activated, four credentials/endpoint fields would need UI | If REQ-DATA-002 export is ever enabled, add the four fields to an OptionsFlow with secret-safe handling (HA `ConfigEntry` sensitive storage); otherwise consider removing the class to avoid drift |
| `DeviceRegistry.name/manufacturer/model` | Defined `repository/device_registry.py:11-17`; `register_device` never called; registry instantiated but unused (`__init__.py:396`) | None — no data flows through it | Either wire it into the device lifecycle (populate on device creation, expose in panel) or delete it; an in-memory registry with no writers is maintenance noise |

### (b) Removed / inert — deliberately disabled, code comments document why
| Gap | Evidence | Impact | Recommendation |
|-----|----------|--------|----------------|
| `target_device_id` (move sensor to a device) | Removed from `_schema()`; resolution logic retained inert — GH#18 comments at `config_flow.py:159-164`, `210-218`, `269-274` | Users cannot bundle/unbundle sensors to devices via the UI; bundling is only inherited (`device_group_id` carry-forward) | Track GH#18; re-introduce a **non-destructive** bundling UI once the entity-registry merge/move hazard is fixed — until then keep it out of the form |
| `create_new_device` (detach sensor) | Same GH#18 removal (`config_flow.py:248-249` pops it) | Detaching a bundled sensor requires deleting and recreating it | Same as above; pair with a "create new device" option only after the destructive merge behaviour is resolved |

### (c) Internal-only — intentional, no user surface required
| Gap | Evidence | Impact | Recommendation |
|-----|----------|--------|----------------|
| `device_group_id` | Carry-forward only (`config_flow.py:257-258`); used as device identity key | None — flow-managed; users never need to set it directly | Keep internal; document in ARCHITECTURE as the bundling key. Revisit only if a bundling UI (b) lands |
| Polling interval (30 s) | Hardcoded `update_interval=timedelta(seconds=30)` (`coordinator.py:56`) | Users cannot tune polling frequency | Acceptable for an abstraction layer; if demand arises, expose via OptionsFlow with a sane min/max bound — but it is a constant today, not a gap in mapping |

> **Update (2026-08-16):** the polling interval row above is superseded — the interval is now an
> OptionsFlow setting (Select presets 2/5/30 + bounded custom 1..3600) applied via
> `set_update_interval`; see `docs/ARCHITECTURE.md` §4.

### (d) Core-UI-only — provided by HA, not the integration
| Gap | Evidence | Impact | Recommendation |
|-----|----------|--------|----------------|
| Friendly name, icon, area, enabled toggle | Entity registry, managed by HA core | Full per-entity UI exists; correctly outside integration scope | None — confirm the panel/entity rows surface the registry names so users see their customizations |

---

## 5. Prioritized Recommendations (suggestions only — no code changes made)

1. **P0 — Resolve the dormant surfaces (a).** Either activate `InfluxExporter`/`DeviceRegistry`
   with matching UI (OptionsFlow + registry wiring) or remove them. Dead code paths with
   config-shaped parameters are the only real risk of a future "configuration the UI cannot
   map" situation.
2. **P1 — Track GH#18 for a non-destructive bundling UI.** Restore
   `target_device_id`/`create_new_device` only after the entity-registry merge/move hazard is
   fixed; until then the current removal is the correct call and should stay.
3. **P2 — Consider an OptionsFlow for the polling interval** only if user demand justifies
   it; otherwise leave the constant.
4. **P3 — Documentation.** Record the empty-root/singleton design and the read-only panel
   contract in `docs/ARCHITECTURE.md` (panel contract already described in
   `frontend.py:1-9`) so future contributors do not mistake the slim UI for missing surface.
5. **P4 — No action:** the 11 sensor fields, HA core entity dialog, and read-only panel
   already cover the complete *active* configuration surface.

---

*Audit methodology, coverage figures, and all evidence were verified against the repository
on 2026-08-15. No files outside this document were modified.*
