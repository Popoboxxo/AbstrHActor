# Plan: Full `.local` Sensor Abstraction + Comprehensive Sidebar Panel UI

**Status:** proposed
**Date:** 2026-10-02
**Scope:** `custom_components/abstractor/` (backend + panel), migration of `.local` YAML abstraction layer
**Depends on:** ADR-007 revision (see §4.1), `docs/plan-panel-action-hub.md` (done), `docs/device-mapping-ui-design.md` (done)

---

## 1. Goals

1. **G1 — Full abstraction:** Replace the hand-written template/utility-meter layer in `.local/` (~146 definitions across `energy_power.yaml`, `battery_power_energy.yaml`, `ace1500_power_energy.yaml`, `water_consumption.yaml`, `water_garten_meters.yaml`) with abstractor sensor subentries. Stable `unique_id`s from the YAML map to `CONF_LEGACY_UNIQUE_ID`, preserving recorder history.
2. **G2 — Panel as mission control:** Extend the sidebar panel so **every** backend function (sensor CRUD, options, device mapping, pipeline/filter status, Influx, snapshots, diagnostics) is monitorable and — where the ADR allows — manageable from the UI.

Non-goal: garden valve **template switches** (`water_garten_control.yaml`, 6 switches) stay in YAML; abstractor has no switch/actuator platform (`bridge/` is roadmap only).

---

## 2. Backend gaps blocking the `.local` migration

Verified against `custom_components/abstractor/` (v1.1.0). Ordered by migration criticality.

### B1. Dynamic source groups — **hard blocker**
`.local/energy_power.yaml:30-80` aggregates "Haus Standby" via `expand(search("*_device_power$"))` — a wildcard over ~50 entities that grows automatically when new plugs appear. Abstractor only supports static `source_entity_ids`.
**Options:**
- (a) *Config entry subentry type `source_group`*: a subentry that resolves its sources at poll time via a glob/regex against the entity registry (`re.fullmatch(pattern)`), cached per poll. Matches the YAML semantics exactly.
- (b) UI-side expansion at creation time (snapshot the current matches into a static list). Cheaper, but silently breaks the "new plug appears → automatically included" behavior the YAML gives today.
**Recommendation: (a)** with a `source_group_pattern` field; the coordinator resolves it each poll cycle (cheap: one registry scan).

### B2. Aggregation modes — **hard blocker for batteries**
All multi-source sensors are summed today (`filters.py:62-91`). The Zendure battery templates need:
- `max` (Hyper2000 charge/discharge: take the active channel),
- `first_available` (ACE 1500 output with `ab2000x_33073_power` fallback already handled by REQ-COMP-004 — but Hyper2000 EG/OG have dual-source max-guards in `.local/battery_power_energy.yaml`).
**Work:** add `aggregation: sum | max | min | first_available` (default `sum`) to the subentry schema; implement in `AbstractorFilterPipeline.process_sources` before net-subtract.

### B3. Unit flexibility — **moderate**
- Water hardcoded to `L` (`sensor.py:143`); house water meters report m³ in some setups.
- Energy hardcoded to `kWh`; sources may report Wh.
**Work:** per-subentry unit override (`unit_of_measurement`) + optional scale factor (`unit_factor`, default 1.0) applied in the pipeline after parsing. Validate source unit metadata where available (`state.attributes.unit_of_measurement` mismatch → warning attribute on the entity).

### B4. Spike filter direction — **moderate for power**
Current spike filter only blocks *decreases* (monotonic guard, `filters.py:105-113`) — correct for `TOTAL_INCREASING` energy, but power sensors have no upward-spike protection.
**Work:** `spike_filter_mode: monotonic | band` where `band` takes an optional `max_step` (W or L/s) rejecting |Δ| above the step. Default stays `monotonic` (backwards compatible).

### B5. No sensor delete — **moderate**
Deletion only via HA's native subentry UI. Needed for UI management (G2) and for migration rollback.
**Work:** `delete_sensor` service (`config_entries.async_remove_subentry`? — verify HA API; else disable + orphan-cleanup) + websocket command. E2E-test removal incl. device-registry cleanup.

### B6. Import does not recreate entries — **moderate**
`__init__.py:607-613` stores the snapshot but never recreates config entries — restore is manual.
**Work:** after `validate_snapshot`, iterate entries and call the same creation path as the config flow (reuse `_normalize` + `hass.config_entries.async_add_subentry` via a shared helper). Cover with `tests/test_snapshot.py` round-trip.

### B7. Hardcoded debug entities — **minor**
`coordinator.py:180-183` bakes in `input_boolean.automation_debugger` / `notify.adminnotificationgroup`.
**Work:** move to root options (optional fields); no-op when unset.

### B8. Per-sensor poll interval — **minor**
One global coordinator interval. The `.local` YAML has fast meters (power) and slow meters (water) mixed.
**Work:** optional per-subentry `poll_interval` (≥ global); coordinator schedules sub-groups. Defer if effort explodes the coordinator — global interval is acceptable for v1 of the migration.

---

## 3. Migration plan `.local` → abstractor (G1)

**Phase order is dependency-driven; each phase = one PR-able unit.**

### Phase M1 — Batteries/PV storage (Zendure) — highest pattern complexity
- Hyper2000 EG, Hyper2000 OG, ACE 1500: charge (sum), discharge (max + invert), combined = charge − discharge (native net-subtract).
- ACE 1500 fallback (`output_pack_power == 0` gate → `sensor.ab1000x_33073_power`) → `fallback_source_entity_id` + `fallback_condition_entity_id/state` (REQ-COMP-004) — hand-rolled YAML today, exact feature match.
- ~14 templates + 4 utility meters → expect ~6–8 subentries (power) + 3 energy meters.
- Utility meters (kWh integration of power) → keep HA `utility_meter` on the abstracted power sensor (abstractor correctly does not integrate; Riemann template in `.local/ace1500_power_energy.yaml` is replaced by utility_meter on the subentry sensor).

### Phase M2 — House aggregates
- "Haus Standby Plugs Gesamtleistung" (dynamic wildcard sum) → needs **B1** (source group).
- "Haus Virtual Standby", Riemann W→kWh → utility_meter over the abstracted standby sensor.

### Phase M3 — Per-plug consumers (~50 devices)
- Each plug: power subentry (single source, often invert) + energy subentry or utility_meter.
- Mostly mechanical; bulk-creation script (YAML → `import_data` payload via snapshot format, then **B6** recreates entries) instead of 50 manual config-flow runs.
- Shelly Matter strip "Basteltisch" (4 channels + total): 5 subentries, single device via `device_group_id`.

### Phase M4 — Water
- Garden valve meters 1/2/3/5 + total + dishwasher: `TOTAL_INCREASING`, L, spike filter monotonic — 1:1 mappable today. Validates B3 if any source reports m³.

### Phase M5 — Migration tooling & verification
- `scripts/migrate_local_yaml.py` (dev-only, not shipped): parses the 5 YAML files, emits a snapshot JSON (with `legacy_unique_id` = existing template `unique_id`s → recorder history continuity).
- Parity harness: run old template sensors and new abstractor sensors side-by-side for 48 h; dashboard comparing values (the panel's per-device live view, §5 Phase P1, is the comparison UI).
- Decommission YAML package files only after parity sign-off.

---

## 4. Sidebar panel overhaul (G2)

### 4.1 ADR-007 is abandoned — replaced by explicit read/write mode (user decision 2026-10-02)
`frontend.py:1-9` (ADR-007) and `docs/plan-panel-action-hub.md:104-111` forbade in-panel configuration ("not a second way to configure them"). **Decision: ADR-007 is superseded.** The panel becomes fully manage-capable (CRUD, options, mapping), but writes are gated behind an **explicit read/write mode** so configuration can never be changed accidentally:

- **Default mode: read-only.** Panel behaves exactly like today (monitoring views, deep-links, export). Zero write surface visible.
- **Write mode: conscious opt-in.** A clearly labeled toggle ("Edit mode" / "Bearbeitungsmodus") in the panel header unlocks all write actions. Requirements:
  - Toggle requires **admin** (`hass.user.is_admin`) — non-admins never see it.
  - Toggle state is **session-local** (not persisted across reloads) — every browser session starts read-only again.
  - Entering write mode shows a one-time confirm banner explaining that changes apply immediately (no draft/undo — HA subentries have no transaction rollback; deletion is final).
  - All write controls render disabled with a hint when read-only (not hidden — discoverability, but unmistakably inert).
  - Destructive actions (delete subentry, bulk import with recreate, device remapping) always need a **second inline confirmation** regardless of mode.
- The native HA config flow remains fully supported and untouched — the panel is a *second, explicit way* to configure, not a replacement.

Rationale for abandoning ADR-007: with ~50+ subentries after the `.local` migration, native per-subentry flow editing does not scale for bulk operations and at-a-glance pipeline state; the read/write gate preserves the original safety intent of ADR-007 (no accidental config changes) without its scaling limitation.

### 4.2 Phase P1 — Monitoring (ADR-compatible, no decision needed)
All read-only, no new write API:
1. **Subentry table view:** all subentries with source(s), type, filter flags, aggregation mode, fallback config, live value, last-update age. Data: extend coordinator debug info or a websocket `abstractor/subentries` query reusing `diagnostics.py` redaction.
2. **Pipeline health per sensor:** last parse failure, fallback active (yes/no + since), spike-filter rejections counter, source-unavailable flags. Requires coordinator to record per-subentry pipeline events into `coordinator.data` (extend the dict value from raw float → `{value, meta}` — keep `native_value` read path unchanged).
3. **System card:** poll interval, Influx status (last push success/fail, queue depth if batching added), snapshot stored (date, entry count), options summary.
4. **Diagnostics & snapshot download buttons** (diagnostics via HA native service; snapshot = existing export).
5. **Entity deep-links** per row (→ HA device page, → source entity history).

### 4.3 Phase P2 — Management (write mode, per §4.1)
Backend (Python), all via **websocket commands** (`frontend.py` registers `websocket_api` handlers; avoids duplicating service schemas and keeps services.yaml for YAML/automation users). Every write command **re-checks admin + a per-session write-mode token** sent by the panel (the toggle requests a short-lived capability flag from the backend; commands without it are rejected with `not_allowed`):
- `abstractor/subentry/create | update | delete` — thin wrappers calling the shared normalization/validation helpers extracted from `config_flow.py` (single source of truth; config flow and websocket both call them). Device-mapping ownership transactions **must** go through `_validate_device_mapping` unchanged.
- `abstractor/options/update` — poll interval, Influx, debug-notify entities (B7), device naming.
- `abstractor/reload` — coordinator refresh on demand.
Delete also as HA service (B5) so automations can use it.

Frontend (`www/abstractor-panel.js`, still vanilla, no build step):
- **Mode toggle in header** per §4.1: read-only default; admin-only "Edit mode" switch with confirm banner; session-local.
- Subentry list with inline edit drawer (form fields mirroring the subentry schema; B1 pattern editor with live-match preview, B2 aggregation selector) — controls rendered disabled in read-only mode.
- Delete with confirm; bulk import (file → `import_data` with recreate, B6).
- Options tab (root options).
- Keep everything i18n-ready via `strings.json`-style key lookup (panel currently hardcodes English/German strings — introduce a minimal i18n map).

### 4.4 Tests
- `tests/test_frontend.py`: websocket handler registration, command schema validation, permission checks (admin-only for writes), **write-mode gate** (write commands rejected without/after expiry of the session token; non-admin token request denied).
- `tests/test_services.py`: delete service, import-recreates-entries round-trip (B6).
- `tests_e2e/test_sidebar_panel_e2e.py`: P1 views render; P2 create→appears→edit→delete cycle; import with recreation; options update reflected in coordinator interval; **read-only default** (write controls disabled after fresh load, enabled after explicit toggle + confirm).
- Keep config-flow coverage at 100 % (project convention) — shared helpers keep both paths covered.

---

## 5. Sequencing & effort estimate

| # | Work item | Blocks | Effort |
|---|---|---|---|
| 1 | B7 debug-notify options (quick win) | — | S |
| 2 | B6 import recreates entries | M3/M5 | M |
| 3 | B5 delete service (+ registry cleanup) | P2 | S |
| 4 | B2 aggregation modes | M1 | M |
| 5 | B1 dynamic source groups | M2 | L |
| 6 | B3 units + scale factor | M4 | M |
| 7 | B4 spike band mode | M3 quality | S |
| 8 | M1 battery migration (+ parity run) | 4 | M |
| 9 | M2 standby aggregate migration | 5 | S |
| 10 | M3 bulk consumer migration (script) | 2,6 | L |
| 11 | M4 water migration | 6 | S |
| 12 | P1 monitoring UI (4.2) | — | L |
| 13 | ~~ADR-007 amendment decision~~ **resolved: abandoned, read/write mode per §4.1** | 14 | — (done) |
| 14 | P2 management UI (4.3) | 3,13 | XL |
| 15 | M5 decommission YAML + docs | all M* | S |

S < 1d, M 1–2d, L 3–5d, XL > 5d (rough, single developer).

**Suggested order:** 1 → 2 → 3 → 12 (fast visible value) → 4 → 8 → 5 → 9 → 6 → 11 → 10 → 14 → 15.

**Write-mode gate (new risk item, §4.1):** the write-mode token must be server-issued and short-lived — a client-side-only toggle would be cosmetic security. All websocket write commands verify admin + token server-side.

## 6. Risks

- **B1 registry scans per poll** could get expensive with ~50 matches × pattern groups — mitigate by caching the resolved entity list per subentry and only re-resolving on `entity_registry_updated` events.
- **Shared-helper extraction (P2)** risks diverging config flow vs websocket validation — enforce by having the config flow *call* the same helpers (tests pin both paths).
- **Recorder history**: only preserved if `legacy_unique_id` = old template `unique_id` everywhere in the migration script; add a validation step that every YAML template unique_id appears exactly once in the generated snapshot.
- **HA version seams** (`config_flow.py` feature detection for registry ownership): panel write API must reuse, never reimplement.
