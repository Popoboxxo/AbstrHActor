# System Audit — AbstrHActor (UI focus + value-management enrichment)

**Audit date:** 2026-11-07
**Auditor:** Main-chat orchestrator (read-only audit; no source modified, nothing committed on this audit except this document's later commit)
**Baseline:** branch `docs/system-audit` @ `788e16f` (merge PR #54 — naming & identity templates), `manifest.json` working-tree version `1.4.0`
**Scope:** `custom_components/abstractor/**` (config flow, Options flow, subentry flows, WS API, panel JS, coordinator, filters, specs, services), `tests/`, `tests_e2e/`, `tests/frontend/`, `.github/workflows/`, plus the issue pattern catalog of the sibling project `Popoboxxo/ha-health-o-mat` (#28–#73) as feature-inspiration reference
**Supersedes:** `docs/system-audit-2026-09-06.md`, `docs/system-review-2026-10.md` (those remain as history; superseded statements are noted where relevant)

---

## 1. Executive summary

The core (singleton root + subentries, shared coordinator, per-subentry filter pipeline, pinned `CONF_LEGACY_UNIQUE_ID` identity, safe device-mapping transaction) is healthy and now well tested (17 pytest modules, 8 E2E tests, WS command tests, frontend unit harness). The user-facing **management surface has grown substantially since the 2026-10 review** — tabbed panel, edit-mode drawers, WS write API — and with it several new inconsistencies appeared:

| Severity | Finding | Where |
|---|---|---|
| **High** | UF-01 Device-type drift: `panel.js` hardcodes 6 device types, but `SPEC_REGISTRY` ships 9 enabled specs | `www/abstractor-panel.js:3` vs `specs.py:83-97` |
| **High** | UF-02 `riemann_energy` is *implicitly enabled* (missing `enabled=False`) contrary to the module's own contract comment | `specs.py:87`, default at `specs.py:40` |
| **High** | UF-04 The WS read/subscribe API is admin-gated, so non-admin users see an empty "Administrator access required" panel | `websocket.py:146-152`, `panel.js:351`, `panel.js:629-635` |
| **Medium** | UF-03 WS write paths skip the voluptuous schemas the config flow owns — `ws_options_update` persists an arbitrary dict; `ws_subentry_update` merges unvalidated types | `websocket.py:234-275`, `websocket.py:297-310` |
| **Medium** | UF-05 `abstractor/yaml_scan` is a permanent placeholder returning `[]` — the Migrate tab can never show anything | `websocket.py:387-391` |
| **Medium** | UF-06 Panel detail drawer renders raw subentry keys and `JSON.stringify` values (technical debt, untranslated, leaks registry shape to users) | `panel.js:555-565` |
| **Medium** | UF-07 Value display has no unit, no precision, no last-update time, no delta — `meta` counters (`spike_rejections`, `fallbacks`, `source_states`) travel to the panel but are never rendered | `panel.js:714-719`, `websocket.py:79-96` |
| **Medium** | UF-08 Panel edit form cannot set the `entity_name` override at all; the rename drawer forces a `logical_name` and only offers `object_id` | `panel.js:879-994`, `panel.js:1024-1119` |
| **Medium** | UF-09 Panel header offers Import (file input) even in read-only mode; gating happens only server-side | `panel.js:486-490` |
| **Low** | UF-10 Full-shadow-DOM re-render on every state update (`innerHTML` + listener re-attach) — flicker/O(n·m) issue from the Oct review is *still unfixed* | `panel.js:497`, `panel.js:508-527` |
| **Low** | UF-11 `SubentryMeta.stale` is defined and transmitted but never set anywhere — dead health signal | `coordinator.py:39` (never `stale=True`) |
| **Low** | UF-12 German panel i18n strips umlauts ("hinfuegen", "Loeschen", "Tuerkontakt") | `panel.js:187-256` |
| **Low** | UF-13 No E2E proof of the WS admin gate with a non-admin account (the ha-health-o-mat #28 pattern was never ported) | `tests_e2e/` has no `create-user`/non-admin test |
| **Low** | O-01 Working-tree hygiene: uncommitted `CHANGELOG.md`/`manifest.json` bump to 1.4.0, dirty submodule, stray `.write-probe` untracked file | `git status` |

**Verdict:** Not a defect audit of the core (core identity/polling path is sound and E2E-tested), but the **UI layer as shipped today has one functional break (UF-01/UF-02 pair) and several reachability/consistency gaps**. All P0 items below are small, local fixes; everything else is enrichment (section 6), which is what the owner asked for: more functions for *managing and presenting the abstracted values*.

---

## 2. UI surface — state of the art today

### 2.1 Native config surfaces (healthy)

- Root `ConfigFlow` (singleton, `ROOT_UNIQUE_ID`), OptionsFlow (poll interval presets + bounded custom, Influx host/token/org/bucket with password selector, device presentation, naming template, debug gate + notify entities) — `config_flow.py:362-564`.
- Subentry create (`user` → `details`) and reconfigure with **type-aware schemas** (`_schema_for` hides numeric pipeline fields for pass-through specs, drops `legacy_unique_id` once pinned) — `config_flow.py:566-1230`.
- Device mapping (target-device selector + create-new-device) restored since the 2026-08 audit, with the fail-loud ownership transaction and the feature-detected registry capability model — `config_flow.py:753-1123`.
- `strings.json` + `translations/de.json` cover all flow fields (verified complete for both create and reconfigure).

Coverage against the 2026-08 `AUDIT_UI_CONFIG.md` denominator: **now 100%** of functional+persisted dimensions are UI-reachable via native flows (`target_device_id`/`create_new_device` are back, Influx/DeviceRegistry/poll interval are live via OptionsFlow). The remaining audit value is in the *panel* surface, described next.

### 2.2 WS API surface (8 commands, `websocket.py`)

| Command | Gate | Notes |
|---|---|---|
| `abstractor/subentries` | admin | read — but should be user-visible read-only (UF-04) |
| `abstractor/subentries/subscribe` | admin | event push per coordinator update, survives reload (coordinator reuse) — good |
| `abstractor/subentry/create` | admin | shares `_build_new_subentry_data` (pins identity UUID at creation) — good |
| `abstractor/subentry/update` | admin | merges current data; **no schema validation** (UF-03); cannot perform device moves (config-flow only, acceptable) |
| `abstractor/subentry/delete` | admin | |
| `abstractor/options/update` | admin | **persists arbitrary dict** + full reload (UF-03) |
| `abstractor/logical_rename` | admin | group-coupled rename + optional entity-id rename with slug guard — good |
| `abstractor/yaml_scan` | admin | **placeholder returning `[]`** (UF-05) |

Edit mode in the panel is a client-side toggle only (`panel.js:407-415`); the write gate is per-command `_require_admin` (`websocket.py:395-397` documents this as deliberate). That decision is acceptable — but then the toggle should be presented as "advanced actions", not as if it armed a server-side edit token.

### 2.3 Panel (`frontend.py` + `www/abstractor-panel.js`, 1175 lines)

Structure: `AbstractorStore` (single state object + subscribers) → full re-render → tabs (Devices/Health/Settings/Migrate), filter chips, per-sensor card (health dot, value, entity/source/unique-id hints, Details/Edit/Configure/Rename/Delete buttons), rename + sensor forms as right drawers with `ha-entity-picker`, export/import via services with `return_response` for export. The Oct-review recommendations F1 (read API), F3 (store) and part of F2 (tabs) have *landed*; memoized rendering and the detail drawer's structured pipeline view have *not*.

---

## 3. Value management & customisation — what a user can do today

Per subentry (create/reconfigure + edit-mode drawer, WS-backed): type (9 enabled specs), sources (single/multi), aggregation (`sum|max|min|first_available`), spike filter, invert, `fallback_zero`, `fallback_on_zero`, net-subtract entity, fallback source + condition entity + expected state, device group move/detach (config flow only), `logical_name`/`object_id` overrides (+ `entity_name` via config flow only — UF-08), identity pinned via `legacy_unique_id`.
Root options: poll interval, Influx export, device presentation, naming template files, debug gate/notify.
Global: snapshot export/import (JSON), delete via service or WS, rename via WS.

**Not customizable today (enrichment axis, see §6):** display unit/unit conversion, numeric precision, per-sensor warning thresholds, value history/visualization, manual sample void/restore, CSV round-trip, options visibility in panel, migrate-tab reality (UF-05).

---

## 4. Sibling-project pattern map (`Popoboxxo/ha-health-o-mat` issues → AbstrHActor)

| Issue | Pattern there | AbstrHActor equivalent today | Action here |
|---|---|---|---|
| #28 | E2E admin-gate verified with a real non-admin account (`--create-user`) | missing (UF-13) | **port**: non-admin E2E asserting `unauthorized` for every admin-only WS command + coverage test over the command table |
| #29 | Breaking-change communication (unit/state_class migration note) | `docs/RELEASE_PROCESS.md` exists | keep; add state_class/unit-change policy note when units land (E1) |
| #30 | Backup/restore service with whitelist + REPLACE confirmation | JSON snapshot export/import exists | extend import with dry-run + explicit recreate report (E4) |
| #31 | Panel/Card Playwright smoke tests in CI with `pageerror`/`console.error` collection | `tests_e2e/test_sidebar_panel_smoke_e2e.py` exists | add pageerror/console-error collection to it (P1 hygiene) |
| #32 | CHANGELOG.md kept current | present (dirty on 1.4.0) | commit hygiene (O-01) |
| #70 | `list_history` pagination (`limit/offset/has_more`, caps fail loud) + void/restore of entries via exposed ids | no value-history read API, no manual void (UF-07, enrichment E2/E3) | **build** `abstractor/history` read command with same pagination contract; spike rejections get ids so a user can void/restore single samples (E2) |
| #71 | Services registered `SupportsResponse.OPTIONAL` with flat response contract | only `export_data` responds (`__init__.py:490`); `import_data`/`delete_sensor` report nothing to callers | register `OPTIONAL` + response contract: import → `{recreated[], kept[], errors[]}`, delete → `{entity_id, device_id, history_preserved}` (E4) |
| #72 | CSV import from outside: exactly-one-source rule (`filename` xor `content`), UTF-8 size cap, admin-only, export dir readable as import dir | values are JSON-snapshot only | **build** CSV export/import of abstracted values with the same guard rails (E5) |
| #73 | Catalog extension + `require_explicit_unit` + tolerant unit equivalence (`umol/L`≡`µmol/L`) | units are spec-fixed (`specs.py:83-97`), source unit is never checked | **build**: unit detection vs spec unit, explicit-unit option, tolerant comparison table (E1) |
| #33 | Options-flow menu step (`async_show_menu`) | flows are step-split already | optional, not needed |

---

## 5. Prioritized remediation (existing surface)

**P0 (fix drift/break, small):**
1. **UF-01** Single-source the device-type catalogue into JS: export `window.AbstractorTypes = {device_types, aggregation_modes}` from Python (the `window.AbstractorI18n` channel already exists at `panel.js:270-273` as precedent — mirror it), or fetch via a WS command `abstractor/types` on load. Until then switch/light/cover sensors are unfilterable and uncreatable in the panel and get rejected by `validateSensorForm` (`panel.js:13-16`).
2. **UF-02** Mark `riemann_energy` `enabled=False` (`specs.py:87`) — today it is enabled by default, offered in the native flow, and unmodellable in the panel. Decide: enable fully (with its integration dependency `riemann_left`) or disable; the comment claims disable.
3. **UF-03** Validate WS payloads with the schemas the config flow owns: extract `AbstractorSensorSubentryFlowHandler._schema_for` into a reusable validator used by `ws_subentry_update`/`ws_subentry_create`, and validate `ws_options_update` payloads against the OptionsFlow init schema. Today `aggregation: "banana"` or `poll_interval: "999999"` is persisted verbatim.
4. **UF-04** Make read paths user-visible: `ws_get_subentries` without admin gate returns redacted payloads (drop `legacy_unique_id`, `device_group_id` internals), admin gate only on writes and only for the unredacted view; panel renders devices read-only for everyone (mirrors ha-health-o-mat #70's "externally controllable interface" principle).
5. **UF-05** Implement real `yaml_scan` (walk `config/` for legacy template sensors matching the migration M1 schema; it must be read-only scan + status), or drop the Migrate tab; shipping a permanently-empty tab is UI debt.

**P1 (observability hygiene):** UF-06 structured drawer (label map, pipeline stage list, see E6), UF-07 render units/last-update/delta + start consuming `meta` (counters + `source_states` chips), UF-08 expose `entity_name` in rename drawer, UF-09 gate the header import file-input behind edit mode, UF-10 memoize render (store-level, per Oct-review §6.2), UF-11 remove `stale` or set it (poll-time based), UF-12 correct umlauts in `de` dictionary, UF-13 port the non-admin E2E gate test, extend `tests/frontend/` beyond `sensor-form.test.mjs` to store/selector units.

---

## 6. Feature-enrichment backlog — managing & presenting abstracted values (owner request)

Shaped from the ha-health-o-mat patterns; every item keeps the constraints (no second source of truth, vanilla panel, admin-gated writes, pinned identity).

| # | Feature | Sketch | Maps to | Cost |
|---|---|---|---|---|
| E1 | **Unit & display options per subentry**: `display_unit` (e.g. energy: kWh↔Wh), `display_precision`, explicit unit declaration with `require_explicit_unit`-style error when the source unit mismatches the spec unit, tolerant unit equivalence table (kWh/kwh/KWH, m³/m3) | new optional subentry fields + schema additions in `_schema_for`, conversion applied at panel render and Influx push boundary; source unit read from entity (`unit_of_measurement` in state obj) | #73 | M |
| E2 | **Manual sample control**: spike rejections get stable ids in `meta`; new WS commands `abstractor/history` (paginated: `limit/offset/has_more`, caps reject loud) + `abstractor/void_sample`/`abstractor/restore_sample` | coordinator records rejected samples (bounded ring per subentry); panel Health tab gains per-sensor "rejected samples" list with void/restore buttons | #70 | M |
| E3 | **Warning thresholds**: per-sensor `warn_above`/`warn_below` (+ optional condition entity gate) → derived `ok/warn/bad` health feeds the existing Health tab; optionally a companion warn `binary_sensor` per subentry ("..._lab_warning_*" analog) | subentry data + coordinator `meta.health` computation; WS payload already carries `health` | warn-entity pattern | M |
| E4 | **Structured service responses**: `import_data`/`delete_sensor` with `SupportsResponse.OPTIONAL` flat contract (`recreated[]`, `kept[]`, `errors[]` ≤20 texts, no raw sensor values in error texts — the #71 privacy rule) | service registration + contract doc; panel Import shows the response summary instead of silence | #71, #30 | S |
| E5 | **CSV round-trip of values**: `export_csv`/`import_csv` services (admin-only, exactly-one-source rule `filename` xor `content`, UTF-8 ≤2 MiB, `;` separator, export dir importable) | new services + services.yaml selectors; panel Settings tab gains CSV actions | #72 | M |
| E6 | **Pipeline visualization in the drawer**: stage list (sources → aggregation → spike → invert → net-subtract → fallback → value) with the *active* stages highlighted and last event annotated; replaces raw-key rendering (UF-06) | pure selector over existing subentry data + `meta`; unit-testable in `tests/frontend` | §5.4 plan, never shipped | M |
| E7 | **Sparkline + delta in value cards**: 60-sample ring buffer per subentry inside the store (fed from the existing subscribe stream — no extra WS traffic), delta vs previous poll, relative time since last update | panel store only (JS), plus optional `updated_at` in WS payload from coordinator | plan §5.5 | S |
| E8 | **Summary report service**: `summary` returning per-sensor aggregates (current value, unit, min/max/avg over N days from recorder, spike/fallback counters) with a response contract — foundation for dashboards and future weekly reports | new `SupportsResponse.ONLY` service reading `hass.states`/recorder data | #71 `weekly_report` | M |
| E9 | **Options visibility**: Settings tab renders current root options read-only (interval, export enabled y/n, template name) from a new redacted WS read command, with deep links for editing | WS read + tab renderer | — | S |
| E10 | **Panel value management on the same screen**: Devices tab row gains: value + unit + updated_at + delta + health chip + sparkline; drawer gains E6 — the card becomes a value-management read view, edit stays deep-linked | composes E6/E7 | — | S |

**Recommended first sprint:** P0 items 1–5 (all small, flow- and test-local) → then E1 + E7 (value correctness on screen) → then E2 (sample control, the only medium-risk backend addition) → E3/E4 afterwards.

---

## 7. Working-tree observations (audit context)

- `CHANGELOG.md` and `manifest.json` modified but uncommitted (v1.4.0 bump), `external/ReqogniLoom` submodule pointer dirty — land these in the next release commit, not bundled with an audit commit.
- `.write-probe` untracked stray file — delete or `.gitignore`.
- `__pycache__` dirs present but untracked (gitignore coverage OK).

## 8. Method & limitations

Static read of every UI/WS/pipeline module in full; ha-health-o-mat issues fetched live (10 issues #28–#73, all closed, comments read for the resolution patterns). No HA runtime was executed; WS/panel statements are from code. No SCA run. Frontend unit harness (`tests/frontend/sensor-form.test.mjs`) exists but was not executed here.
