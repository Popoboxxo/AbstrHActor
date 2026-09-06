# System Audit — AbstrHActor (2026-09-06)

Branch `feat/device-mapping-ui` (PR #30) · read-only audit · method: 6 parallel research workers → consolidated evidence → synthesis + code-review pass → this final report.

## Executive summary

1. The remediation branch `fix/system-audit-remediation-2026-09-04` (security, stable identity, snapshot, diagnostics, CI fixes) is not part of PR #30 — merging the device-mapping UI alone would ship without those protections and likely with red pytest CI (**Critical**).
2. Unhandled `asyncio.TimeoutError` in the Influx push can propagate into `_async_update_data` and crash the poll loop, knocking every sensor offline when the Influx host is slow (**High**).
3. The promised Bridge and Strategy architecture is not present; the current implementation is a coordinator plus hardcoded sensor branching (**High**).
4. A single failing subentry can currently fail the coordinator refresh and make all Abstractor entities unavailable (**High**).
5. Non-legacy source reconfiguration re-derives the unique ID, risking orphaned entities and lost recorder history (GH#19) (**High**).
6. `source_required` is missing from the subentry translation namespace and can render as a blank/untranslated error (**High**).
7. The monotonic "spike filter" rejects all decreases, freezes live power at a prior peak, and conflates unavailable power with zero — the `fallback_zero` toggle has no effect for power devices (**Medium**).
8. Polling is blocked by serial notify and Influx awaits, making cadence and future debug traces unreliable (**Medium**).
9. README and architecture guidance describe obsolete flows and overstate implemented patterns (**Medium**).
10. The shared HA instance never loaded Abstractor on this branch, so runtime behavior remains unverified — a workflow limitation, not a code defect (**Medium**, re-rated).

## Severity-ranked findings

| Severity | Finding | Evidence (file:line) | Recommendation | Effort |
|---|---|---|---|---|
| Critical | Remediation branch is not part of PR #30 | `raw-findings.md:136`; remediation branch carries `ac9963e` (security), `c9de187` (stable identity, GH#19), `059c5fc` (filter snapshot restore), `445027b` (diagnostics), `2a37a85` (CI unblock) | Merge/rebase the remediation branch into PR #30 or main before merging the device-mapping UI; re-run CI and review the combined diff | M |
| High | Unhandled `asyncio.TimeoutError` in Influx push crashes the poll loop | `influx_exporter.py:74-93` catches only `aiohttp.ClientError`; the 10 s `aiohttp.ClientTimeout` (`influx_exporter.py:20,80`) raises `asyncio.TimeoutError`, propagating through `coordinator.py:125-126` into `_async_update_data` | Also catch `asyncio.TimeoutError` so a slow Influx host degrades to a logged warning instead of failing the whole refresh | S |
| High | No Bridge/Strategy implementation despite architecture claims | `custom_components/abstractor/` has no `bridge/` or `sensor_types/`; `raw-findings.md:30-39` | Explicitly scope these as roadmap work or implement the promised pluggable bridge/sensor-type interfaces before claiming the architecture is delivered | L |
| High | One failing subentry can make every entity unavailable | `coordinator.py:95-127` (unguarded subentry loop); `raw-findings.md:43-45` | Catch and record failures per subentry, retain successful results, and expose a per-subentry unavailable/error state | S |
| High | Non-legacy reconfigure changes `unique_id` when sources change | `sensor.py:93-102`; `config_flow.py:186-202`; `raw-findings.md:41-45`, `:62` (GH#19) | Base identity on immutable subentry identity; preserve source-swap history while retaining the legacy migration pin | M |
| High | `source_required` is emitted in the subentry flow but absent from its translation namespace | `config_flow.py:363-370,415-421`; `strings.json:52-61`; `translations/en.json:51-59` | Add `config_subentries.sensor.error.source_required` to both catalogs and test the rendered error | S |
| High | PR pytest CI is likely red without the remediation CI-unblock commit | `raw-findings.md:134-146` (`2a37a85`, py3.13 job) | Reconcile the CI fix, then run the exact workflow matrix before merge | S |
| Medium | "Spike filter" rejects all decreases and is applied to power | `filters.py:36-45,103-114`; `sensor.py:126-137`; `raw-findings.md:46` | Rename it to monotonic guard and restrict it to totalizing counters; preserve real-time power decreases | S |
| Medium | Unavailable power is conflated with zero and `fallback_zero` is non-functional for power | `filters.py:66-89,127-130` (`_handle_unavailable` hard-codes `device_type == "power"` → `0.0`, ignoring the toggle); `raw-findings.md:50` | Honor the `fallback_zero` option; represent unavailable separately from zero; prevent unavailable samples from updating `_last_valid_state` | M |
| Medium | Notify and Influx calls are awaited serially inside polling | `coordinator.py:116-126`; `raw-findings.md:47` | Dispatch bounded background work or otherwise decouple side-channel I/O from the coordinator's poll cadence | M |
| Medium | Poll interval uses HA-private coordinator seams | `coordinator.py:64-80`; `raw-findings.md:48` | Add explicit version guards and a compatibility test, or use a supported rescheduling API when available | M |
| Medium | Device registry is only an in-memory metadata stub and is not identity authority | `repository/device_registry.py:6-25`; `__init__.py:398-399`; `sensor.py:122-124`; `raw-findings.md:36,63` | Either implement documented dedup/type/location lookup semantics or reduce the documentation and remove the misleading abstraction | M |
| Medium | Config-flow coverage misses supported-subentry registration and duplicate-root abort | `config_flow.py:216-234`; `raw-findings.md:57-63` | Add direct tests for `async_get_supported_subentry_types` and `_abort_if_unique_id_configured` | S |
| Medium | Snapshot validation has six untested `vol.Invalid` paths | `snapshot.py:33-55`; `raw-findings.md:121-130` | Add invalid-format/version/shape tests and raise snapshot coverage from 76% | S |
| Medium | Error-path coverage remains thin outside config flow | `raw-findings.md:117-130` (coordinator, sensor, Influx, filters, migration) | Add focused tests for failed pipelines, non-numeric/non-finite input, exporter failures, and migration edge cases | M |
| Medium | README describes the pre-subentry flow and obsolete options | `README.md:96-136,209-229`; `raw-findings.md:93-100` | Refresh setup, options, implemented features, limitations, and panel documentation against current behavior | M |
| Medium | Architecture documentation is stale and omits device mapping | `docs/ARCHITECTURE.md:5` and drifted citations; `raw-findings.md:93-100` | Re-verify citations, update branch/runtime metadata, and document the device-mapping contract and actual implementation boundary | M |
| Medium | Project guidance presents planned Bridge/Strategy/EntityDescription features as implemented | `AGENTS.md:65` and raw architecture matrix; `raw-findings.md:99-100` | Reconcile prose with the explicit planned marker and current source tree | S |
| Medium | Influx `entity_id` tag uses the first source instead of the abstract sensor identity | `coordinator.py:125-126` pushes `source_ids[0]` as the Influx tag, losing the abstraction-layer identity for multi-source sensors | Tag with the abstract sensor/subentry id (add per-source fields only if needed) | S |
| Medium | Shared HA runtime never loaded Abstractor, so runtime behavior is unverified | `raw-findings.md:150-156` | In a separately authorized session, sync only this domain, restart HA, and re-observe entities, logs, setup, reload, and panel behavior | S |
| Medium | Dirty ReqogniLoom submodule pointer can be staged accidentally | `git status --short --branch`; `raw-findings.md:139` | Decide intentionally whether to pin `a05f6d5` or `9e0399b`, then stage only the intended parent-repo change | S |
| Medium | Committed `AGENTS.md.sync-backup-20260803-222315` stays tracked (repo hygiene) | `git status --short --branch`; `raw-findings.md:137` (introduced by commit `4e2c035`; `.gitignore` cannot untrack it) | `git rm --cached` the file in a hygiene change | S |
| Medium | Untracked `CLAUDE.md.sync-backup-*` backup is not ignored | `git status --short --branch`; `raw-findings.md:138` | Add the backup pattern to `.gitignore` and remove any accidental copies from the working tree | S |
| Medium | Health-o-mat is flooding the shared instance with unrelated errors | `raw-findings.md:155` (~343 `aiohttp.server` errors, ~90 ms cadence) | Report the undo-drink error flood to that repository owner; keep it separate from Abstractor conclusions | S |
| Low | Influx line protocol does not escape the entity tag | `influx_exporter.py:68-69`; `raw-findings.md:51` | Escape tag keys/values and field content according to Influx line-protocol rules | S |
| Low | Frontend dependency is lazily imported but absent from manifest | `manifest.json:5-7`; `frontend.py:40-49`; `raw-findings.md:73-75` | Add the required manifest dependency if supported by the target HA versions, then validate with Hassfest | S |
| Low | Panel computes device name but renders no entity name | `www/abstractor-panel.js:36-45,119-126`; `raw-findings.md:76` | Render the computed entity name alongside entity ID and value | S |
| Low | Panel sorts without guarding an undefined device name | `www/abstractor-panel.js:47-55`; `raw-findings.md:77` | Normalize the sort key to a guaranteed string before `localeCompare` | S |
| Low | Panel and sidebar text are hardcoded English | `www/abstractor-panel.js:93-102`; `frontend.py:44-49`; `raw-findings.md:78` | Add frontend localization if multilingual panel support is a product requirement | M |
| Low | Root `config.error.source_required` is now orphaned | `strings.json:10-12`; `translations/en.json:9-11`; `raw-findings.md:85-89` | Remove the dead root key after the subentry key is added, or document why it remains | S |
| Low | Several UI strings are not localizable or use an unsubstituted placeholder | `config_flow.py:383-386,449-454`; `sensor.py:103`; `strings.json:35`; `raw-findings.md:87-89` | Move titles/entity names to translation-aware descriptions and ensure placeholders are supplied | S |
| Low | `docs/SENSOR_TYPES.md` is referenced but missing | `AGENTS.md:65`, `CLAUDE.md:87`, `.meta-config/project.yaml:90-91`; `raw-findings.md:98-100` | Create the promised document or mark the reference explicitly as planned | S |
| Low | Import snapshots are validated structurally but rendered fields are not constrained | `snapshot.py:33-55`; `__init__.py:588-594`; `raw-findings.md:141-142` | Validate known sensor/config fields and HTML-escape all panel-rendered values; retain the non-recreating import contract | M |
| Low | Shared-mutable state is mutated across reloads while the poll loop may be suspended | `__init__.py:417-421` and `coordinator.py:82-93` mutate `subentry_data`/`pipelines` while `_async_update_data` may be mid-loop, so a removed sensor can still be processed in the current cycle | Snapshot the subentry set per update cycle before iterating | M |
| Low | `_registry_capabilities` lru_cache never invalidates | `config_flow.py:137-138` caches for process lifetime; stale capabilities survive HA registry changes/reloads | Invalidate on reload or bound the cache | S |
| Low | `native_value` has no return annotation | `sensor.py:139-142`; `raw-findings.md:51-53` | Annotate it as `float | None` | S |
| Low | CI lacks explicit permissions/concurrency and pins floating action refs | `raw-findings.md:143-146` (`validate.yaml`, `hacs/action@main`, `hassfest@master`) | Set read-only permissions and concurrency cancellation; pin actions to reviewed versions or SHAs | S |
| Low | Manifest prerelease and HA-floor comments need consistency review | `manifest.json:7-11`; `config_flow.py:396-401`; `raw-findings.md:80-83` | Verify Hassfest acceptance of `1.1.0-rc.1` and correct comments to cite the actual floor source | S |

## Per-area findings

### (a) Backend patterns & correctness

The core defect cluster lives here: the poll loop in `coordinator.py` is the single point of failure for the whole domain. Key findings: **no per-subentry error isolation** (High), the **unhandled `asyncio.TimeoutError`** in the Influx push (High), the **unique_id derivation** from mutable source lists (High), the **absent Bridge/Strategy/EntityDescription architecture** (High), and the **in-memory device-registry stub** that is never consulted for identity (Medium). Filtering semantics are also off: the "spike filter" is a monotonic guard applied to power (Medium) and **unavailable power hard-codes to `0.0`, ignoring the `fallback_zero` toggle**, feeding the guard state (Medium). Side-channel I/O (notify, Influx) is awaited serially inside the poll cadence (Medium), the interval reschedule pokes HA-private seams (Medium), and the Influx tag both uses the wrong identity (`source_ids[0]`, Medium) and is **unescaped line protocol** (Low). Reload safety is weak: `subentry_data`/`pipelines` are mutated while `_async_update_data` may be suspended (Low), and `native_value` lacks a return annotation (Low). See the table for the full rows.

### (b) Config flow / device mapping / migration

The subentry rework is structurally sound — legacy migration preserves unique IDs, re-points registry rows, and is idempotent/interrupt-safe (`raw-findings.md:67`) — and the ownership-model feature detection is conservative and fail-safe. Remaining gaps: the **non-legacy source-swap re-derives `unique_id`** (High, GH#19), `source_required` is raised in the subentry flow but has no translation key there (High), the **supported-subentry registration and duplicate-root abort paths are untested** despite the 100% config-flow claim (Medium), and **`_registry_capabilities` is cached for process lifetime** and never invalidated on registry changes or reloads (Low). The orphaned root `config.error.source_required` key (Low), unlocalizable titles/entity names and the unsubstituted `{device_type}` placeholder (Low), and the manifest/HA-floor comment drift (Low) all belong to this area as well.

### (c) Frontend / JS / HA compliance / translations

The panel JavaScript is XSS-safe — all dynamic values use `textContent`; the single `innerHTML` writes only a static shell — and all other translation keys are present and identical in both catalogs with CI enforcing sync. Gaps: the `frontend` dependency is lazily imported but **absent from the manifest** (Low), the computed entity name is never rendered (Low), the sort key can hit `localeCompare` with an undefined name (Low), panel and sidebar strings are hardcoded English (Low), and the `source_required`/orphaned-key/placeholder issues cross-referenced in (b) are surfaced here in the rendered UI.

### (d) Documentation

`docs/device-mapping-ui-design.md` maps 1:1 onto the implementation and `docs/REQUIREMENTS.md` correctly states bridge/sensor extensibility as requirements rather than delivered features. Everything else drifted: the **README describes the pre-subentry flow and obsolete options** (Medium), **`docs/ARCHITECTURE.md` carries a wrong branch header, drifted citations, and no device-mapping section** (Medium), **`AGENTS.md` presents planned Bridge/Strategy/EntityDescription features as implemented** (Medium), and **`docs/SENSOR_TYPES.md` is referenced but missing** (Low).

### (e) Tests & coverage

Strengths first: 136/136 tests pass at 97% coverage with a meaningful, registry-driven 100% on the config flow; GH#18 has extensive unit coverage plus a strict, self-inverting E2E sentinel (deliberate xfail, not a masked failure). Gaps: **snapshot.py sits at 76% with six untested `vol.Invalid` paths** (Medium), **config-flow coverage misses the supported-subentry and duplicate-abort branches** (Medium), and **error paths outside the config flow are thin** — coordinator, sensor, Influx exporter, filters, migration (Medium). `test_migration.py` has only two tests, the absent `bridge/`/`sensor_types/` packages have zero test surface, and frontend JS is untestable by pytest (Python glue is 100%).

### (f) CI/CD

`validate.yaml` (HACS, Hassfest, translations-sync, pytest on py3.13) and `e2e.yaml` (docker-compose, artifact upload, `down -v` teardown on `if: always()`) are present; the latest E2E run succeeded (4m15s). Risks: **the pytest job is likely red on PR #30 without the remediation CI-unblock commit** (High), workflows **lack `permissions:`/`concurrency:`** and pin **floating action refs** (`hacs/action@main`, `hassfest@master`) (Low).

### (g) Repository hygiene & security

Security verdict is clean: no secrets ever tracked, `.ha-state` history is empty, tokens are masked and never logged or URL-embedded. The blocking item is the **orphaned remediation branch** (Critical). Hygiene findings: the **committed `AGENTS.md.sync-backup-20260803-222315`** (Medium, `git rm --cached`), the **untracked, non-ignored `CLAUDE.md.sync-backup-*`** (Medium), the **dirty ReqogniLoom submodule pointer** (Medium), and the **unconstrained/unescaped import-snapshot fields** (Low, stored-XSS/entity-spoof surface). No real TODO/FIXME markers exist.

### (h) Runtime

Abstractor was **not loaded** on the shared HA 2026.9.1 instance, so no runtime claim about this branch is verified — re-rated to Medium as a test-environment/workflow limitation, not a code defect. The instance's unrelated **health_o_mat error flood** (~343 `aiohttp.server` errors at ~90 ms cadence, undo-drink path) should be reported to that repository's owner and kept separate from Abstractor conclusions (Medium). Full details in the Runtime observations section.

## Coverage

The unit suite reports **136/136 tests passed**, **97% overall coverage** (869 statements, 27 missed), and **100% config-flow coverage**.

| Module | Stmts | Miss | Cover |
|---|---:|---:|---:|
| `config_flow.py` | 301 | 0 | **100%** |
| `const.py` | 44 | 0 | 100% |
| `diagnostics.py` | 14 | 0 | 100% |
| `frontend.py` | 42 | 0 | 100% |
| `__init__.py` | 179 | 1 | 99% (line 440) |
| `coordinator.py` | 78 | 2 | 97% (104,162) |
| `sensor.py` | 55 | 4 | 93% (134-137) |
| `influx_exporter.py` | 38 | 3 | 92% (91-93) |
| `repository/device_registry.py` | 10 | 1 | 90% (25) |
| `filters.py` | 83 | 10 | 88% (26-29,76,109-111,123-124) |
| `snapshot.py` | 25 | 6 | 76% (41,45,47,49,52,54) |

Notable gaps: `snapshot.py` is only 76%; the planned `bridge/` and `sensor_types/` packages are absent and therefore untestable; error paths remain thin in `__init__.py`, coordinator, sensor, Influx exporter, filters, and migration. Frontend JavaScript is not covered by pytest. The single strict E2E xfail is deliberate and tied to GH#18, not a masked failure.

## Runtime observations

The shared HA instance was **HA 2026.9.1**, running in Europe/Berlin (metric, de/DE), but Abstractor was **not loaded**: zero Abstractor entities (79 total, all health_o_mat/core), no `abstractor` component in `/api/config`, no `custom_components/abstractor/` on disk, and no Abstractor log lines. The branch was never synced, so runtime behavior, reloads, entity registration, and the panel remain unverified; this is an audit limitation, not evidence of a runtime defect. A separate authorized sync-and-observe session is required.

Side observation: the shared instance had an unrelated health_o_mat error flood — approximately 343 `aiohttp.server` errors at roughly 90 ms cadence from `HomeAssistantError("Keine Getränke zum Entfernen")` in the undo-drink path. Report that to the health_o_mat owner and do not attribute it to Abstractor.

## Phase-2 readiness

Data sources available now: `coordinator.data` per-subentry results, the snapshot store, config entries/subentries through `hass`, HA device/entity registries, and filter configuration. The existing panel already receives the `hass` object.

Missing/blocking data: (1) live filter traces showing accept/reject decisions and reasons, (2) bounded per-update pipeline history or an event/debug channel, and (3) a read-only WS/REST API — diagnostics is static and the existing notify side-channel is inside the poll path.

Top three pre-work items:

1. Add a bounded coordinator/filter debug ring buffer with structured raw values, filter decisions/reasons, and final values.
2. Move notify and Influx side-channel work out of the polling critical path so timing and history are trustworthy (also removes the poll-crash surface of the TimeoutError finding).
3. Expose the buffer through a read-only WS/HTTP endpoint and render all returned strings safely; this also closes the import/panel escaping concern.

## Proposed follow-up issues

### [Harden the Influx push and poll loop against timeouts and side-channel failures]

Background: `influx_exporter.py:74-93` catches `aiohttp.ClientError` but not the `asyncio.TimeoutError` raised by the 10 s client timeout, so a slow Influx host propagates an unhandled exception into `_async_update_data` and fails every entity's refresh.
Finding/impact: one slow Influx write can knock the whole domain offline instead of degrading to a logged warning.
Suggested fix: catch `asyncio.TimeoutError` alongside `aiohttp.ClientError`, and (longer term) move the Influx/notify side-channel awaits out of the poll loop into bounded background work.

### [Reconcile remediation branch into device-mapping PR #30]

Background: `fix/system-audit-remediation-2026-09-04` is not in main or PR #30 and contains the security, stable identity (GH#19), snapshot, diagnostics, and CI fixes.
Finding/impact: merging PR #30 alone would ship the UI without those protections and may leave pytest CI red.
Suggested fix: rebase or merge the remediation branch into PR #30/main, resolve conflicts, rerun unit/CI validation, and review the combined diff.

### [Preserve unique_id across non-legacy source reconfigure]

Background: sensor identity is derived from source entity IDs and device type (`sensor.py:93-102`).
Finding/impact: changing hardware sources during reconfigure creates a new entity identity and can orphan registry/history data (GH#19).
Suggested fix: derive non-legacy IDs from immutable subentry identity, retain the legacy migration pin, and add a source-swap regression test.

### [Isolate coordinator failures per subentry]

Background: `_async_update_data` processes all subentries in one unguarded loop.
Finding/impact: one pipeline, notify, or export exception can fail the refresh for every entity.
Suggested fix: guard each subentry, retain successful values, record the failed subentry and reason, and test mixed success/failure polling.

### [Add source_required to the subentry translation namespace]

Background: both subentry flow steps emit `errors["base"] = "source_required"`.
Finding/impact: the key exists only under top-level `config.error`, so the user-facing subentry error can be blank or untranslated.
Suggested fix: add the key under `config_subentries.sensor.error` in `strings.json` and `translations/en.json`, then test translation synchronization and display.

### [Refresh README and ARCHITECTURE documentation]

Background: current docs describe the old root-bundling flow, obsolete options, and stale line references.
Finding/impact: users and maintainers receive incorrect setup and architecture guidance, while the device-mapping contract is missing.
Suggested fix: update setup/options/limitations, document the panel and subentry model, correct citations, and distinguish implemented patterns from roadmap items.

### [Untrack sync-backups and resolve the dirty ReqogniLoom submodule]

Background: a tracked `AGENTS.md.sync-backup-20260803-222315`, an untracked `CLAUDE.md.sync-backup-*`, and a dirty external submodule are present.
Finding/impact: generated backups can recur in releases and the submodule pointer can be staged accidentally.
Suggested fix: `git rm --cached` the tracked backup, ignore the backup pattern, and intentionally commit or revert the submodule pointer in a separate hygiene change.

### [Escape and constrain imported snapshot values]

Background: import validates the portable snapshot shape and stores it, while panel values originate from HA registry/state data.
Finding/impact: rendered titles/device names and related fields are not constrained by known integration values; future panel rendering could expose spoofing or stored-XSS risk.
Suggested fix: validate known sensor/config fields on import and HTML-escape/render all dynamic panel values with `textContent`; add invalid-field tests.

## Appendix — methods & limitations

Method: fully **read-only** audit of branch `feat/device-mapping-ui` (PR #30) — no code/config edits, no commits except this report. Six parallel research workers (backend, config flow/mapping, frontend/translations, docs, tests, repo/CI/security/runtime) produced the consolidated evidence in `raw-findings.md`; a senior-developer synthesis pass merged it into 33 findings, and a code-review pass added 5 verified findings and adjusted severities (this report). Coverage numbers come from a local `pytest --cov` run (artifacts only). The shared HA test instance was observed read-only.

Limitations: Abstractor was **not loaded** in the shared instance, so the runtime section contains no Abstractor runtime data; E2E tests were not run (they need a live HA plus browser) — only the workflow health was reported; the `/api/config_entries` endpoint returned **404** and was not available for inspection; `bin/logs` output was **sampled** (~400 lines), so the log analysis is a window, not a full trace.
