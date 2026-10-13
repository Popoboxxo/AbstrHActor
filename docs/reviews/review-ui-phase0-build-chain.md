# Review — `feat/ui-phase0-build-chain` (uncommitted)

**Date:** 2026-10-13
**Reviewer:** opencode (deepseek-v4.1-flash)
**Baseline:** working tree on branch `feat/ui-phase0-build-chain`

**Scope:** new `websocket.py`, `specs.py`, `binary_sensor.py`; changes to
`coordinator.py`, `sensor.py`, `__init__.py`, `const.py`, `frontend.py`;
`frontend/src/abstractor-panel.js` + build chain (`scripts/build-frontend.mjs`,
`package.json`); new tests. `.meta-*`, `.serena/`, `external/` excluded.

## Verification status (facts, not assumptions)

- **pytest could not run locally** — `pytest-homeassistant-custom-component`
  imports `fcntl` (Unix-only); collection aborts with
  `ModuleNotFoundError: No module named 'fcntl'`. New tests are unverified on
  Windows. The real gate is the Ubuntu `pytest` job in
  `.github/workflows/validate.yaml:50`.
- `ruff check custom_components/abstractor scripts` → 8 issues in 6 files, all
  in untracked scratch scripts; `custom_components/abstractor` is clean.
- `node scripts/build-frontend.mjs` succeeds and produces output byte-identical
  to the committed artifact → artifact currently in sync.

## Blockers

**B1 — `node_modules/` is not gitignored.** `git status` lists `?? node_modules/`;
`.gitignore` has no entry. Committing would vendor thousands of files.
Fix: add `node_modules/` to `.gitignore`; commit `package-lock.json`.

## Major

**M1 — Throwaway scratch scripts with invalid syntax.** `scripts/patch_create.py:1`
hardcodes `C:\Repositories\AbstrHActor\...` and does string surgery. Ruff flags
invalid-syntax at `patch_create.py:95`, `patch_add_tmp.py:42`, `patch_health.py:22`
("missing closing quote") and SIM115 at `patch_panel.py:2,68`. Delete these files.

**M2 — Validation can be silently bypassed.** `_validate_device_mapping`
(`websocket.py:37-51`) swallows every exception and returns `{}`, while the real
`_validate_device_mapping` performs registry-mutating side effects
(`config_flow.py:689-719`). A safety check that mutates state and fails open is
dangerous. Fix: surface failures as `send_error`, or use a pure read-only check.

**M3 — Edit-mode token is decorative.** `ws_mode_token` mints a token
(`websocket.py:143-148`) but it is never stored or verified; write commands only
gate on `_require_admin` (`websocket.py:154,197,237`) and the panel never returns
the token. Fix: enforce the token on writes or remove the feature.

**M4 — Panel "Add sensor" can only create `power`.** `_handleAddViaWs`
(`frontend/src/abstractor-panel.js:572-593`) sends no `device_type`; the WS path
defaults to `"power"` (`coordinator.py:135`, `sensor.py:53`). Energy/water and the
new binary types are unreachable from the panel.

**M5 — Mixed-platform `SENSOR_TYPES` in a numeric-only flow.** `const.py:58-64`
adds `door_contact/motion/smoke`; `_schema` offers them with numeric-only options
(spike filter, invert, fallback, net-subtract, aggregation —
`config_flow.py:1056-1097`) that binary sensors ignore (`coordinator.py:135-141`).
Derive per-platform schemas from `SPEC_REGISTRY`.

**M6 — specs.py docstring contradicts reality.** `specs.py:5-6` claims it replaces
the `device_type == "power"` branches in `filters.py`, but `filters.py:126,144,205`
still hardcode it — two sources of truth for the fail contract. Migrate filters to
`spec.fail_contract`, or correct the claim.

**M7 — New write API is untested.** `tests/test_websocket.py` covers only
register/read/token; create/update/delete/options/`logical_rename` have no tests,
`binary_sensor.py` has none, and coordinator `SubentryMeta` accumulation is
untested.

## Minor

- **XSS surface:** `_render` injects `s.error` via `innerHTML`
  (`abstractor-panel.js:273`); error text includes server `str(exc)`/`str(errors)`
  (`websocket.py:168,173,187`). Render the error node with `textContent`.
- **Dead code:** `binary_sensor.py:100` computes `device_key`, then line 102
  overwrites it and touches `coordinator.subentry_data` needlessly.
- **No CI guard on the build artifact:** `www/abstractor-panel.js` is a committed
  build product; `validate.yaml` has no frontend job. Add
  `node scripts/build-frontend.mjs && git diff --exit-code` + `npm run typecheck:frontend`.
- **i18n inconsistency:** dead keys (`abstractor-panel.js:31-43`) and hardcoded
  English at lines 263, 391, 398, 465, 474, 481.
- **`ws_get_subentries` not admin-gated** (`websocket.py:93`) while the panel is
  `require_admin=False`; exposes source ids/unique ids to any authenticated user.
- **Inconsistent title:** WS create sets `f"Abstract {device_type}"`
  (`websocket.py:181`) vs. the flow's normalized title.
- **Edit deep-link mismatch:** `_deviceIdFor` matches `id[1] === subentry_id`
  (`abstractor-panel.js:362`), but grouped sensors register under
  `device_group_id` (`binary_sensor.py:102`).
- **No live refresh:** `_maybeFetch` loads only once (`abstractor-panel.js:167-171`).
- **Duplicated type registry:** `const.SENSOR_TYPES` and `SPEC_REGISTRY` both
  enumerate types.

## Nits

- `import re as _re` inside a function (`websocket.py:292`).
- `AbstractorStore` defines `state` accessors after `setState` uses them
  (`abstractor-panel.js:105-110`).
- Coordinator keeps the previous `event_at` when `last_event` is None
  (`coordinator.py:211-213`) — intended, but undocumented.

## Verdict

Solid direction (registry-driven specs, health metadata, WS read API, reproducible
build). Not merge-ready: B1 and M1 are pre-commit hygiene; M2/M3 are security-model
correctness; M4/M5/M6 are functional/consistency defects; M7 is a required coverage
gap.

## Resolution status (post-fix)

| ID | Status | Evidence |
|---|---|---|
| B1 | Fixed | `node_modules/` in `.gitignore`; `package-lock.json` tracked |
| M1 | Fixed | `scripts/patch_*.py` deleted |
| M2 | Fixed | `websocket._validate_device_mapping` is a read-only pre-check (`websocket.py:37`); handlers surface failures via `send_error` |
| M3 | Fixed | decorative token removed (command, `secrets`/`time` imports, const); writes gated by `_require_admin` |
| M4 | Fixed | panel Add flow prompts/validates `device_type` (`abstractor-panel.js:631`) |
| M5 | Fixed | two-step flow (`async_step_user` type → `async_step_details`); `_device_type_options()`/`_schema_for()` from `SPEC_REGISTRY`; `SENSOR_TYPES` registry-derived |
| M6 | Fixed | `filters._is_fail_soft()` consults `spec.fail_contract`; `specs.py` docstring updated |
| M7 | Fixed (unverified locally) | write-command + `_validate_device_mapping` tests in `tests/test_websocket.py`; new `tests/test_binary_sensor.py` |
| Minor: XSS | Fixed | error rendered via `textContent` |
| Minor: dead code | Fixed | `binary_sensor.device_info` single computation |
| Minor: CI guard | Fixed | `frontend` job in `validate.yaml` (typecheck + build + `git diff --exit-code`) |
| Minor: i18n | Fixed | strings routed through `_t()`; new keys added |

**Verification:** `ruff check custom_components/abstractor tests` clean; frontend
build output byte-identical to the committed artifact; `const`/`specs` import
cleanly. `pytest` cannot run on Windows (`fcntl` missing) — new tests are
unverified locally and must be confirmed by the Ubuntu CI `pytest` job.
