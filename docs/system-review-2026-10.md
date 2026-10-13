# System Review and Management UI Roadmap — AbstrHActor

**Date:** 2026-10-13
**Baseline commit:** `919a17d` (Merge PR #39 — *docs: add entity-aliasing and panel UX concept plan*)
**Contributing reference:** `m3tac0de/home-assistant-sofabaton-x1s` (server panel + sidebar panel architecture, test harness, design-token system)

---

## 1. Executive summary

AbstrHActor is a mature, well-architected Home Assistant integration: singleton root entry with subentries, a single shared
`DataUpdateCoordinator`, a per-subentry filter pipeline, stable `CONF_LEGACY_UNIQUE_ID` identity, and an in-memory device
registry. The identity/polling core is solid and largely matches the design intent documented in
`docs/REQUIREMENTS.md` and `docs/plan-logical-identity-and-panel-ux.md`.

The weakest, most user-visible surface today is the **management UI**. `custom_components/abstractor/www/abstractor-panel.js`
is a single-file, fully re-rendered on every `hass` change, dependency-free Web Component that shows a read-only list of
devices and provides only Export/Import/Add deep-links. It does not surface health, pipeline state, identity, or
multi-step workflows, and it has no test coverage beyond Python-side panel *registration*.

The reference repository demonstrates what a "well-managed" integration UI looks like even though its scale differs
(server-backed, build step, TypeScript/Lit). This review extracts the patterns that are transferable **without
violating** our explicit constraints (vanilla, dependency-free, no build step), and converts them into a prioritized,
concrete roadmap.

---

## 2. System baseline (code snapshot)

| Area | State | Evidence |
|---|---|---|
| Platforms | `sensor` only (`PLATFORMS = ["sensor"]`) | `custom_components/abstractor/__init__.py` |
| Coordinator | Single shared, polls all subentries, pruning on subentry add/remove | `__init__.py:async_setup_entry` |
| Filter pipeline | Spike filter, invert, fail-soft/fail-closed, net-subtract, fallback source, pass-through planned | `filters.py`, plan WS-D |
| Identity | `CONF_LEGACY_UNIQUE_ID` pinned at creation, resolver in `sensor.py` planned (`_resolve_identity`) | plan WS-A |
| Snapshot | `values` map + `entries`; config round-trip; restore-missing semantics | `snapshot.py`, `__init__.py:import_data_service` |
| Panel | Read-only card list, full `innerHTML` rebuild per `set hass`, deep-link buttons only | `frontend.py`, `www/abstractor-panel.js` |
| Panel tests | 4 tests, all about registration/no-op; **zero** coverage of rendering or actions | `tests/test_frontend.py` |
| Other e2e/UI tests | `tests_e2e/` present (Playwright) | `docker-compose.e2e.yml` |
| Docs | Plan v3 (identity + panel UX) + 7 supporting docs, gap register G1..G10 | `docs/plan-logical-identity-and-panel-ux.md` |

RNFA/REQ alignment: roughly **60 %** of the documented article target is met; breadth half (domains, semantic
`entity_id`, health surfaces, migration tab) is pending — see plan §1.2.

---

## 3. Architectural strengths (keep)

1. **Singleton root + subentries.** One `ConfigEntry`, many `ConfigSubentry` — keeps the data store singular and the
   panel's edit surface a single API boundary.
2. **Shared coordinator + `meta` split (planned).** Avoids N polls; `coordinator.data` keeps its shape while
   `coordinator.meta` adds health without breaking snapshots or spike-filter reseeding.
3. **Deterministic identity.** `CONF_LEGACY_UNIQUE_ID` pins identity across reconfigure — prerequisite for a rename UI
   that does not orphan recorder history.
4. **No build step / dependency-free panel.** Keeps HACS distribution trivial and reviewable; must be preserved or
   deliberately traded.
5. **Edit-mode gate design (plan §5.3).** Server-issued, short-lived token, admin-checked, TTL-enforced. This is the
   right answer to the read-only-only limitation of ADR-007 and is *better* than what most HACS panels do.

---

## 4. Weak points relevant to UI

### 4.1 Panel rendering performance and correctness
- `_render()` rebuilds the entire shadow DOM and re-attaches all listeners on **every** `hass` update, including
  unrelated state changes. Large installations (27+ sensors) will flicker and lose focus/scroll.
- `_abstractorDevices()` re-scans all devices/entities each render (O(n²)).
- Health is not represented at all (no `meta` consumption), so the "why" behind a value is invisible — the exact
  deficiency the article calls out.

### 4.2 No state boundary
The panel mixes data derivation, DOM construction, and side-effecting services in one class. The reference panel's
split (`PanelApi` → `PanelStore` → `panel-state` selectors → view components) is what makes it testable and incremental.
Adopting a thin store/selectors layer (still vanilla) removes the rebuild-everything problem.

### 4.3 No test net
`tests/test_frontend.py` only covers Python registration. There is no automated check that the panel renders, that
health colours stay consistent, or that the edit-mode gate works. The reference repo's frontend-test harness
(`npm run build:frontend-tests && node --test tests/frontend-dist`) is a model for how to add property-based unit tests
without a browser.

### 4.4 Thin daemon surface / raw controls
Buttons are hand-rolled `<button>`; no progress/disabled states during async calls (`_handleExport`, `_handleImportFile`
fire-and-forget). No per-field validation feedback in the drawer (drawer does not exist yet). Uses the legacy
`�` glyph in places (encoding artefacts, see `strings.json` handling).

### 4.5 No routing/deep links
The panel has no addressable sub-view. Reference panel routes via URL hash and preserves tab across reload. For a
multi-tab management UI this is required (`#devices`, `#health`, `#migrate`, `#settings`).

---

## 5. What the reference repository actually offers

Cloned at `external/sofabaton-x1s`-equivalent location for this review. Its relevant deliverables:

| Reference asset | What it demonstrates | Applicability here |
|---|---|---|
| `server-panel/src/panel-route.ts` + `panel-element.ts` | Payable tab bar, hash routing, tab sub-views under Lit `cache()` so a tab survives switching | **High.** Add hash routing + per-tab custom elements that persist their last content. |
| `panel-store.ts` / `panel-state.ts` / `panel-selectors.ts` | Single store snapshot; views render the snapshot; selectors derive busy/dirty/health; no bespoke data in views | **High.** Vanilla equivalent: one module holding `{devices, meta, route, busy}`, plus pure selector functions. |
| `panel-api.ts` | One typed boundary to the backend (fetch + problem text) | **High.** Map to our planned websocket commands (`abstractor/subentries`, …) in one module. |
| `panel-stream.ts` | SSE/stream for progress + auth events | Medium. We already get state changes via `hass` updates; borrow only for coordinator re-poll / toasts. |
| `bottom-dock.ts` + `operation-progress.ts` | Compact fixed status/progress region | **High.** Better than scattering status in the header. |
| `hub-picker.ts` | Compact object picker with inline add/remove | **High.** For device grouping and command-target selection. |
| `auth-dialog.ts` / `access-view.ts` | Claimed-server auth wall, sign-in overlay on 401 | Medium. Our HA-native panel already inherits HA auth; borrow the *overlay* UX for token expiry. |
| `tests/frontend/*` + `tests/playwright/server-panel.spec.js` | Property/unit tests at the store/selector level + E2E via Playwright harness | **High.** Close our test gap without adding a browser to the unit loop. |
| `audit:contrast` + theme-polarity tests | Automated a11y hygiene | Medium. Add a small contrast budget to CI for badges. |
| Design tokens in `panel-styles.ts` | Consistent elevation, radii, motion, container queries | **High.** Adopt HA-native `ha-card`/`ha-dialog`/`ha-textfield` rather than inventing tokens. |
| Build pipeline (esbuild/ts) | Rich components, type safety | **Medium trade-off.** Improves maintainability but contradicts our no-build constraint and HACS audit simplicity. Evaluate at phase gate. |

**Key takeaway:** the reference does *not* invent more UI concepts than `plan-logical-identity-and-panel-ux.md §5`, but it shows **how** to organize them so they are testable and incremental. Adopting its *structure*, not its dependency stack, is the cheap win.

---

## 6. Target architecture for the management UI

Constraints we keep:
- **No second source of truth.** Every write reuses helpers extracted from `config_flow.py`.
- **Edit-mode is server-verified** (plan §5.3). Client toggle alone is cosmetic.
- **Vanilla, dependency-free, no build step** unless a phase gate explicitly lifts it.

### 6.1 Module decomposition (still one served file)

Split `abstractor-panel.js` into several custom elements loaded from the same static path, defined in separate
concatenated source files at build time *or* as separate static assets. Recommended elements:

- `abstractor-shell` — tabs, routing, auth/health overview, error banner.
- `abstractor-device-card` — device grouping, health dot, badges.
- `abstractor-sensor-row` — semantic name first, technical `entity_id` second, sparkline, expand.
- `abstractor-pipeline-detail` — expand row (sources, pipeline stages, identity).
- `abstractor-drawer` — generic right-docked drawer with focus trap + ESC.
- `abstractor-create-drawer`, `abstractor-rename-drawer` — edit-mode forms.
- `abstractor-toast` — inline error/success surface.

Each is a thin consumer of a shared `AbstractorStore` instance attached to `hass`.

### 6.2 State store (vanilla)

Introduce one store per panel instance:

```js
// AbstractorStore.js (concept)
export class AbstractorStore {
  constructor(hass) { this.hass = hass; this.state = {...}; this.subs = []; }
  // single mutation entry point returning {ok, error}; views never call hass.callService directly
  async invoke(command, payload) { ... }
  subscribe(fn) { ... }
}
```

- Selectors (`healthDot`, `spikeState`, `identityFor`) are pure functions → unit-testable.
- Views re-render **only** when a derived slice changes (memoized by reference), eliminating the full-rebuild flicker.
- Busy flags per command drive disabled states and the bottom dock.

### 6.3 Backend boundary (websocket)

Implement `plan §5.6` commands. Ordering by value:

1. `abstractor/subentries` (read) — required for everything; replace the `hass.devices` traversal.
2. `abstractor/mode/token` + expiry signalling — required for any write UI.
3. `abstractor/subentry/update` — create/edit drawer.
4. `abstractor/subentry/create` / `delete` — close the loop.
5. `abstractor/logical_rename` — rename affordance.
6. `abstractor/options/update` — Settings tab (replaces deep links).
7. `abstractor/yaml_scan` + `abstractor/reload` — Migrate tab + manual refresh.

All handlers live in a new `custom_components/abstractor/websocket.py` sharing the extracted config-flow helpers.

### 6.4 Design system

- Use `ha-card`, `ha-button`, `ha-icon`, `ha-textfield`, `ha-select`, `ha-dialog`, `ha-chip`, `ha-alert` so the panel
  inherits HA's theme tokens and density. Drop the hand-rolled buttons.
- Keep a tiny local stylesheet only for AbstrHActor-specific layout (sparkline, health ring, dense rows). Everything else
  is HA's.
- Replace hardcoded EN strings with a key map (`panel.devices.*`) driven by `hass.language`, matching `strings.json`.

### 6.5 Accessibility (explicit budget)

- Keyboard order matches visual order; drawers trap focus and close on ESC.
- Health conveyed by **icon + text**, never colour alone.
- `aria-live="polite"` region for async toasts/errors.
- Contrast ≥ 4.5:1 on badges (add to CI via the `audit:contrast`-style script).

### 6.6 Testing

Lift the frontend from zero to:
- **Unit (node):** pure selectors + store state transitions, run without HA (reference's harness model).
- **E2E (Playwright):** read-only default → edit toggle → create → appears → rename → entity_id change → delete;
  tab switches preserve content; health chip lights when a source goes unavailable.
- **Python:** websocket handler tests follow the 100 % config-flow convention and cover admin checks, token verify/expiry,
  collision on rename, read-path redaction.

---

## 7. Inspiration-driven improvement backlog (prioritized)

Severity/priority uses the plan's P0/P1/P2/P3 scale.

### P0 — article headline / structural

| # | Change | Cost | Inspired by |
|---|---|---|---|
| A0 | `_resolve_identity` + `object_id` suggestion (A0 spike) | S | plan WS-A |
| B1 | `specs.py` registry replacing the `if/elif` ladder | M | plan WS-B |
| C3  | Domain expansion: real write/listen commands for `power`/`energy` | L | plan WS-C |

### P1 — observability & identity in the UI

| # | Change | Cost | Inspired by |
|---|---|---|---|
| F1 | Backend read API `abstractor/subentries` + meta | M | reference `panel-api.ts`, `panel-selectors.ts` |
| F2 | Tabbed shell (Devices / Health / Migrate / Settings) with routing | L | reference `panel-route.ts`, `panel-element.ts` |
| F3 | Store + memoized view re-render | M | reference `panel-store.ts` |
| Drawer | Sensor detail drawer (identity/sources/pipeline/history) | M | plan §5.4 screen 3, reference `*-view.ts` dialog patterns |
| Edit gate | Server-issued token + write API | M | plan §5.3, reference `auth-dialog.ts` |

### P2 — polish

| # | Change | Cost | Inspired by |
|---|---|---|---|
| HA components | Migrate from raw `<button>` to `ha-button`/`ha-chip`/... | S | HA-native components (not present in reference, better fit) |
| Sparklines | 60-sample in-panel ring buffer | S | plan §5.5, reference metric cards |
| i18n | Key map from `hass.language` | M | plan §5.5, reference `remote-card-translations` |
| A11y CI | Contrast budget script | S | reference `audit:contrast` |
| Frontend tests | Node unit harness + Playwright E2E | M | reference `test:frontend` / `test:playwright:*` |

### P3 — hygiene

| # | Change | Cost | Notes |
|---|---|---|---|
| WS-H docs | Fix stale README / coverage / audit docs | S | Already scheduled |
| ADR update | Replace `frontend.py` ADR-007 docstring with plan §5.3 decision | S | Plan flagged |
| Build gate | Decide esbuild/Lit adoption at WS-F exit | S | Reference uses a full toolchain; revisit |

---

## 8. Concrete first sprint (suggested)

**Goal:** make the abstraction observable and trusted *before* making it editable (article principle 1).

1. Extract `config_flow` helpers into a shared module (no behavior change; keeps 100 % coverage).
2. Add `websocket.py` with `abstractor/subentries` (read only) returning data + `meta` + resolved identity +
   a `health` badge (`ok/warn/bad/idle`).
3. Refactor `abstractor-panel.js` into `abstractor-shell` + store + selectors; consume `abstractor/subentries`
   instead of `hass.devices`; memoize render.
4. Tabbed shell with three tabs: Devices (current list, now with health dot), Health (problem list grouped by failure
   kind), Settings (deep-link shell).
5. Add unit tests for the pure selectors under `tests/frontend/` using a tiny node harness (no build step).
6. Playwright E2E: open panel → health dot renders → empty-state text → tab switching preserves scroll. 

Exit criterion: a user with 27 sensors can open the panel, see *which* sensors are unhealthy and *why*, without reading a
log line — and rendering no longer flickers on unrelated state changes.

### 8b. Implementation note (2026-10-13)

The planned `store.py`/`ws.py` have only an abstract concept established here; the next PR should put them under
`custom_components/abstractor/`. Because the plan already specifies the schema precisely, the backend work (server-side
`abstractor/subentries`) is the highest-value unblocked task, and cheapest where extracted config-flow helpers are reused.

---

## 9. Explicit non-goals / decisions needed

1. **Build toolchain.** Decide at the end of the UI sprint whether the complexity justifies adding esbuild/Lit. Until
   then, "no build step" stays.
2. **`object_id` mandatory?** Plan open question 1 recommends required in the panel drawer, optional in the native flow.
   Confirm before implementing the create drawer.
3. **REQ-UTIL-001 (own statistics).** Verify whether fixing `available`/`state_class` makes it redundant (plan open
   question 2).
4. **Migrate tab timing.** Ship read-only scanner early; full transplant script later (plan open question 3).

---

## 10. References

- `docs/REQUIREMENTS.md` → requirements catalog
- `docs/REQUIREMENTS_COVERAGE.md` → FA-02/FA-09 (G6), FA-12 (G10)
- `docs/plan-logical-identity-and-panel-ux.md` v3 — authoritative plan (gaps, workstreams, panel wireframes)
- `docs/plan-full-abstraction-and-panel-ui.md` §4.1 — edit-mode decision carried into §5.3
- `docs/device-mapping-ui-design.md` — registry transaction / flow integration order
- `docs/plan-panel-action-hub.md` — action hub baseline (superseded by §5)
- `LASTENHEFT_ABSTRAKTIONS_INTEGRATION.md` §2.1 — original Discussion #3402 filing
- Home Assistant Discussion #3402 — Native Entity Aliasing
- Reference: `github.com/m3tac0de/home-assistant-sofabaton-x1s` — server panel architecture, test harness, design-token system
