# System Audit — AbstrHActor (`custom_components/abstractor`)

**Audit date:** 2026-09-04
**Supersedes:** `docs/SYSTEM_AUDIT.md` (2026-08-03) and `docs/find.md` (2026-08-03) — both are now stale; keep them only as historical record. Every finding below was independently re-verified against the current tree (manifest `1.1.0-rc.1`, branch `chore/upgrade-agent-meta-beta`, HEAD `bf1b5e6`), not copied from the old reports.
**Method:** Five parallel read-only tracks, each with full-file reads, `git`/`gh` history mining, and (for the CI root cause) empirical PyPI wheel bisection — not static guessing. Raw per-track reports are archived in the session scratchpad; this document consolidates and cross-references them. No project files were modified during the audit itself.

---

## 1. Executive summary

Since the 2026-08-03 audit, AbstrHActor grew substantially: it shipped v1.1.0-rc.1, added a singleton-root/subentry ("Device Bundling") architecture, a browser-facing frontend panel, a live InfluxDB exporter, and grew its test suite 7.6x (13 → 99 tests, 7 → 12 files). Some old findings are genuinely fixed. But the audit surfaced a new critical fact and two new high-severity regressions introduced by that same growth:

> **CI-1/2/3 (Critical):** **The test suite has never once passed on `main`.** A dependency-pin bug (`requirements.txt: homeassistant>=2025.1`, one minor below the code's actual 2025.3.0 floor) combined with CI's Python 3.12 pin makes it structurally impossible for pip to install any Home Assistant version that has the `ConfigSubentry` class the code needs. Every one of the 12 test files fails at import/collection. This has been true for **every run since the Pytest job was added on 2026-08-16 — 19+ consecutive daily runs plus every push, 100% failure, zero exceptions.** The 99-test suite is a real, substantial investment that has never executed successfully in CI.

> **ARCH-1 (High) — REQ-CORE-001 regression, tracked as GH#19:** The core "swap hardware, keep your dashboards" promise still breaks for any Abstract sensor created *after* the Device Bundling migration. The mechanism to pin a stable identity (`CONF_LEGACY_UNIQUE_ID`) exists and correctly protects migrated pre-1.1 sensors, but for a brand-new sensor it is just an easy-to-miss optional form field — nothing auto-generates it. The first hardware swap via reconfigure silently mints a new `unique_id`/`entity_id` and orphans the old entity's recorder history.

> **ARCH-2 (High, new regression):** `diagnostics.py` filters `coordinator.pipelines` by `entry.entry_id`, but pipelines are keyed by `subentry_id` under the new architecture. Diagnostics exports come back with an **empty** `pipeline_config` for almost every sensor in a typical multi-sensor install — silently, right when a user needs it most for support.

> **SEC-1 (High, risk-profile change):** The old audit's headline security claim — "no network I/O in shipped code" — is **no longer true** and must be formally retracted. `influx_exporter.py` now performs real outbound HTTP POSTs with a bearer token to a user-configured host, with no scheme/SSRF-awareness validation on that host field.

Two lower-drama but structurally important findings round out the picture: **the DoD's "tests must be green" requirement is currently unenforceable** — `main` has no GitHub branch protection, so even if CI were fixed today nothing would mechanically stop a red-test merge — and **CLAUDE.md/AGENTS.md now internally contradict themselves**: their file-tree section was correctly fixed to mark `bridge/`/`sensor_types/` as not-yet-built, but the prose 30 lines below still describes those same nonexistent things (a Bridge Pattern, an `AbstractSensor` base class, EntityDescription dataclasses, serial/MAC discovery) as if implemented today.

**Verdict: not release-ready as `1.1.0` (stable).** The rc.1 tag is appropriate. Before cutting `1.1.0`: fix CI (unblocks all other verification), close GH#19 properly, fix the diagnostics regression, and correct the security-profile documentation.

---

## 2. Scope and method

Five parallel tracks, each independently re-verifying claims rather than trusting the stale 2026-08-03 baseline:

| Track | Scope |
|---|---|
| **Architecture & code quality** | Every `.py` file under `custom_components/abstractor/`, convention conformance vs. CLAUDE.md |
| **Tests & CI health** | `.github/workflows/`, `tests/`, `tests_e2e/`, dependency pins, full CI run-history reconstruction |
| **Docs, HACS compliance, repo hygiene** | HACS manifest consistency, doc-vs-code drift, requirements traceability, GitHub issue hygiene, git/gitignore hygiene |
| **Security & dependencies** | New frontend/network attack surface, input validation, secrets handling, supply chain |
| **Agent-meta / Claude infra** | Fallout from today's agent-meta v0.101.0-beta.5 upgrade and PR #28 merge — role removal, sync drift, DoD-gate reality, guard-hook accuracy |

No files were modified during the audit. `pytest --collect-only` was attempted locally and confirmed to fail on Windows (`ModuleNotFoundError: No module named 'fcntl'`, the pre-existing, non-regression HA-test-plugin/Windows incompatibility documented as F-10 in the old audit) — GitHub Actions logs (Ubuntu runners) were used instead, which is where the CI root cause was actually confirmed.

---

## 3. Findings index

Severity: **Critical** (ships broken/false, blocks release) · **High** (real defect or materially misleading) · **Medium** (drift, fix soon) · **Low** (polish). Status: **NEW** (introduced since 2026-08-03) · **REGRESSION** (a previously-working thing broke) · **OPEN** (known, still unfixed) · **FIXED** · **SUPERSEDED**.

### 3.1 Tests & CI

| ID | Finding | Severity | Status |
|---|---|---|---|
| CI-1 | `requirements.txt:3` (`homeassistant>=2025.1`) is one minor below the code's real floor (2025.3.0, per `hacs.json`/`Dockerfile.test`) | **Critical** | OPEN |
| CI-2 | CI's Python 3.12 pin (`validate.yaml:57`) makes it structurally impossible to resolve any HA ≥2025.2.0 (HA requires Python ≥3.13 from that release on) | **Critical** | OPEN |
| CI-3 | Combined effect: 100% of the Pytest suite (12 files / 99 tests) has failed at collection on every run since the job was introduced (2026-08-16) — **zero passing CI test evidence has ever existed on `main`** | **Critical** | OPEN |
| CI-4 | Two parallel test-runner configs (`Dockerfile.test` vs. CI `requirements.txt`) drifted — only Docker was updated when the subentry work landed | High | REGRESSION |
| CI-5 | No pip caching in CI (`actions/setup-python@v5` has no `cache: pip`) | Low | OPEN |
| CI-6 | No matrix/canary testing across HA versions, despite HA's demonstrated ~quarterly Python-floor bumps (3.12→3.13 at 2025.2.0, 3.13→3.14 at 2026.6.0) | Medium | OPEN |
| CI-7 | Floating action refs (`hacs/action@main`, `home-assistant/actions/hassfest@master`) — supply-chain reproducibility concern | Low | OPEN |
| CI-8 | `docs/E2E_TESTING.md` coverage table missing 2 newer E2E test files (`test_device_bundling_e2e.py`, `test_translations_e2e.py`) | Low | OPEN |
| CI-9 | Native `pytest --collect-only` fails on Windows (`fcntl`) | Info | OPEN (pre-existing, not a regression — old F-10) |

**Root cause detail (CI-1/2/3):** `ConfigSubentry` was introduced in Home Assistant **2025.3.0** (confirmed empirically by downloading and grepping PyPI wheels: absent in 2025.1.4/2025.2.0, present from 2025.3.0 on). `__init__.py:12` imports it — added in commit `d914b57` (Device Bundling foundation), still load-bearing today. `hacs.json` and `Dockerfile.test` already correctly declare `2025.3.0` as the floor. `requirements.txt` was never updated to match, and — separately — HA's `requires_python` jumped to `>=3.13.0` starting at exactly 2025.2.0, while `validate.yaml` pins the Pytest job to Python 3.12. So pip can *only* ever resolve `homeassistant==2025.1.4` in CI (confirmed directly in the failing run's install log), which predates `ConfigSubentry` entirely. **This is a lower-bound-too-low problem compounded by a Python-version ceiling, not an upstream removal** — nothing was deleted by a newer HA release.

**Blast radius:** the Pytest job was added 2026-08-16 (`a4bce6f`). Its very first run already failed this way. Every run since — 19+ consecutive daily scheduled runs plus every push — has failed identically. The 99-test suite (7.6x growth from the old audit's ~13 tests) has never executed successfully in CI. Only HACS validation, Hassfest validation, and translations-sync are green; those never exercised the Python code at all.

### 3.2 Architecture & code quality

| ID | Finding | Severity | Status |
|---|---|---|---|
| ARCH-1 | Entity identity (REQ-CORE-001) still breaks on hardware swap for sensors created *after* the bundling migration — GH#19 | **High** | REGRESSION (moved from Options Flow to Subentry Reconfigure Flow) |
| ARCH-2 | `diagnostics.py` pipeline_config filtered by `entry.entry_id`, but pipelines are keyed by `subentry_id` — empty for almost every sensor | **High** | NEW regression |
| ARCH-3 | Adding/editing/removing any *one* subentry tears down the *entire* shared coordinator (full teardown + rebuild), discarding every sensor's cached data and spike-filter guard, not just the edited one | Medium-High | NEW (architectural consequence of the singleton-root design) |
| ARCH-4 | Spike-filter / monotonic-guard state (`_last_valid_state`) is still purely in-memory — old F-09 — now amplified by ARCH-3 | Medium | OPEN, amplified |
| ARCH-5 | `device_type` missing/invalid still silently defaults inconsistently (`"power"` in `coordinator.py`, `""` in `sensor.py`), no warning logged | Medium | OPEN (old F-05/M-06) |
| ARCH-6 | Debug-notification target entity/service names still hardcoded, not configurable despite a real Options Flow now existing | Medium | OPEN (old F-06) |
| ARCH-7 | `DeviceRegistry` write side now wired (`sensor.py:124`), but `get_device` still has zero call sites — net-dead, write-only state | Low-Medium | CHANGED, still dead |
| ARCH-8 | `SENSOR_TYPES` still a bare mutable `list`, not `Final`/tuple, unlike every other `const.py` constant | Low | OPEN (old M-04) |
| ARCH-9 | Sensor typing is still an if/elif chain, not the EntityDescription-declarative pattern CLAUDE.md's own conventions mandate | Low | OPEN, now a documented-convention violation |
| ARCH-10 | `async_get_device_diagnostics` (REQ-NFA-006) still not implemented, only the config-entry variant | Low | OPEN (old F-12) |
| ARCH-11 | `__init__.py` has grown to 594 lines mixing entry lifecycle with ~300 lines of one-time legacy-entry migration/reconciliation logic | Low-Medium | NEW |
| ARCH-12 | `AbstractorFilterPipeline.process_sources` toggles `self.config["spike_filter"]` off/on as a control-flow trick | Low | NEW |

**Fixed/superseded since 2026-08-03:** InfluxExporter is no longer a stub (old F-08 — now real I/O, see SEC-1 for the resulting risk-profile change); the old H-01 unique_id format mismatch between `config_flow.py`/`sensor.py` is superseded (config-entry no longer derives any per-sensor id — it's a fixed `ROOT_UNIQUE_ID`); brand icon now present (old M-09). `www/abstractor-panel.js` was checked for injection risk and found clean (verified independently by the security track too, see §3.4).

### 3.3 Docs, HACS compliance, repo/git hygiene

| ID | Finding | Severity | Status |
|---|---|---|---|
| DOC-1 | `CLAUDE.md`/`AGENTS.md` "Besondere Patterns" narrative describes a Bridge Pattern, `AbstractSensor` base class, EntityDescription dataclasses, and USB/DHCP/MQTT config-flow discovery — **none of which exist**. Both files' own "Architektur" tree, 30 lines above, correctly marks `bridge/`/`sensor_types/` as not-yet-built — an internal self-contradiction within the same file | **High** | OPEN |
| DOC-2 | `docs/SENSOR_TYPES.md`, referenced by both CLAUDE.md and AGENTS.md's file trees, does not exist | Medium | OPEN |
| DOC-3 | CLAUDE.md's Tech-Stack section lists `pyserial`/`paho-mqtt` as key dependencies — zero imports anywhere in the code, not in `requirements.txt`/`manifest.json` | **High** | OPEN |
| DOC-4 | `README.md` claims InfluxDB export is "scaffolded only... not yet wired" — **false**, live since 1.1.0-rc.1 per CHANGELOG and `docs/ARCHITECTURE.md` | Medium/High | REGRESSION (doc didn't track a shipped feature) |
| DOC-5 | `README.md` claims device manufacturer/model customization "not implemented yet" — false, shipped via OptionsFlow in 1.1.0-rc.1 | Low | OPEN |
| DOC-6 | No REQ-ID for Device Bundling; `docs/REQUIREMENTS.md` (`REQ-*`) and `docs/REQUIREMENTS_COVERAGE.md` (`FA-*`/`NFA-*`, different source doc) use disjoint, non-cross-referenced ID schemes; neither mentions GH#18/#19 | Medium | OPEN |
| DOC-7 | `CHANGELOG.md` 1.1.0-rc.1 lists "Subentry-based device bundling" under Added with no caveat that the bundling UI itself was withdrawn (GH#18) | Medium | OPEN |
| DOC-8 | `requirements.txt` HA floor stale vs. `hacs.json`'s `2025.3.0` (same root cause as CI-1) | Medium | OPEN |
| DOC-9 | Untracked ReqogniLoom self-model artifacts sitting in the repo root (`audit_report.json`, `reqogniloom_reqs.json`, `scratch_audit.py`, `scratch_decompose.py`, `test_mcp.py`, `task.md`) — not this project's content | **High** | OPEN (hygiene) |
| DOC-10 | `CLAUDE.md.sync-backup-*` not gitignored, unlike the equivalent `AGENTS.md.sync-backup-*` pattern | Medium | OPEN |
| DOC-11 | `docs/state.md` is genuine, valuable project content (Device Bundling PR outcome) but sits untracked inside a tracked `docs/` directory | Medium | OPEN |
| DOC-12 | GitHub issue #14 (E2E CI flakiness) stale — zero activity in ~4 weeks despite heavy CI/E2E churn since | Low | OPEN |
| DOC-13 | `strings.json`/`translations/en.json` differ only by the top-level `title` key | Low | Likely fine (standard HA i18n convention) |

**Confirmed healthy:** `brand/icon.png` now present (old finding resolved); no undeclared runtime dependencies (`aiohttp`/`voluptuous` are HA-bundled); no tracked `.pyc`/`__pycache__`; `.gitignore` covers the main risk areas; `docs/ARCHITECTURE.md` is fully accurate and code-verified; GH#18 and GH#19 both accurately describe live, unresolved issues; Hassfest/HACS/Translations-sync CI jobs are 100% green on every recent run — **the red workflow badge is misleading if read as "HACS compliance is broken"; it is not, only Pytest is red.**

### 3.4 Security & dependencies

| ID | Finding | Severity | Status |
|---|---|---|---|
| SEC-1 | `influx_exporter.py` performs real outbound HTTP POSTs with a bearer token — the old audit's "no network I/O" conclusion is **false** for the current tree and must be retracted; `CONF_INFLUX_HOST` has no scheme/SSRF-awareness validation | **High** | REGRESSION (risk-profile change, not a code defect — the feature works as designed) |
| SEC-2 | `snapshot.py`'s import validation checks shape only, not content of `entry.data`/`entry.options`/`values` — currently narrow blast radius (write-only to Store, never read back), but dangerous the moment `stored_snapshot` is ever consumed to reconstruct entries | Medium | OPEN (old finding, unchanged despite Device Bundling landing) |
| SEC-3 | `requirements.txt`'s `homeassistant>=2025.1` unbounded pin (same as CI-1) | Medium | OPEN |
| SEC-4 | `requirements_test.txt`: `pytest-homeassistant-custom-component` has zero version pin at all | Low | OPEN |
| SEC-5 | `Dockerfile.test`: `ruff`, `mypy`, and 3 pytest packages installed unpinned, contradicting the file's own "reproducible container" stated goal | Low | OPEN |
| SEC-6 | CLAUDE.md's `pyserial`/`paho-mqtt` claim (same as DOC-3) — confirmed, from a supply-chain angle, that no phantom dependency is actually installed; the risk is purely a stale-documentation hazard | Low | OPEN |

**Confirmed clean (re-verified fresh, not copied):** no hardcoded secrets anywhere; no `eval`/`exec`/`subprocess`/`pickle`/`os.system`; the new frontend panel (`www/abstractor-panel.js`) uses `textContent` for every HA-derived value and only a static template literal via `innerHTML` — verified line-by-line, not by trusting the code's own comment; static file serving has no path-traversal surface (fixed constants only); `export_data_service`/`import_data_service` cannot inject arbitrary config entries or write outside the integration's own `Store`; Influx token is correctly masked in the UI (`PASSWORD` selector) and redacted in diagnostics.

### 3.5 Agent-meta / Claude infra

| ID | Finding | Severity | Status |
|---|---|---|---|
| INFRA-1 | `frontend-component-engineer` (removed today from `roles:`) still referenced in the `feature-lifecycle` pipeline's `implement`-stage allowed-agents list, across all 3 provider mirrors — sync.py warns about it but doesn't auto-clean pipeline-detail files | **High** | NEW (today's merge fallout) |
| INFRA-2 | `AGENTS.md`'s manual section is structurally corrupted from today's merge: duplicated `## Eigene Notizen` header (lines ~533 and ~599) with leaked marker-explanation text spliced into the managed-begin marker itself | Medium | NEW (today's merge fallout) |
| INFRA-3 | `sync.py --dry-run --check` currently exits 1 — 25 pending writes, all for 4 ReqogniLoom external agent templates that are stale relative to the current `external/ReqogniLoom` submodule content (`9e0399b3`) | **High** | OPEN (pre-existing, discovered during audit) |
| INFRA-4 | `requirements-architect` ReqogniLoom skill entry is missing/broken (template file doesn't exist upstream) | Medium | OPEN |
| INFRA-5 | The DoD's "tests must be green" requirement is enforced only by the `validator` agent's judgment — `main` has **no GitHub branch protection at all** (`404` on the protection API); combined with CI-3, the gate is currently unenforceable by any mechanism | Medium | OPEN |
| INFRA-6 | `AGENTS.md`'s manual "Known agent-meta health items" note (dated 2026-08-02) is doubly stale: its `claude-expert` premise is moot (role fully removed, not just missing a file) and it still claims the submodule is pinned to v0.91.3 (10 releases behind current v0.101.0-beta.5) | Low | OPEN |
| INFRA-7 | `a2a-delegation-gates.md` attributes sentinel-parsing logic to `orchestrator-guard.sh`; since the #630 wrapper/impl split it actually lives in `orchestrator-guard-impl.sh` | Low | OPEN (doc-precision nit) |
| INFRA-8 | Leftover unused `mcpServers` keys in `.claude/settings.json` and `.claude/settings.local.json` | Low | OPEN |

**Confirmed healthy:** `.agent-meta` submodule is clean, detached HEAD exactly at tag `v0.101.0-beta.5`, matching the parent repo's recorded pointer; both removed roles' per-role agent files were correctly deleted (no orphans); `pending-tasks.md` correctly absent; `branch-guard.md`/`a2a-delegation-gates.md`'s substantive claims (tokenizer gaps, convention- vs. security-boundary framing, self-declared-sentinel limitation) all verified accurate against the actual hook code; the DoD config chain itself (`project.yaml` → `CLAUDE.md` → `dod-criteria.md`) is internally consistent and correctly says tests are required — the gap is enforcement, not configuration.

---

## 4. Cross-cutting observations

1. **The session's own initial context was stale mid-audit.** Two independent tracks noted that the CLAUDE.md/branch-guard.md content injected into this session at start-up was an older cached copy (predating today's agent-meta merge) — the live on-disk files had already moved on. Anyone (human or agent) relying on injected session context rather than re-reading files works from stale config. This is worth a general process note, not a code fix.
2. **Working tree state shifted mid-audit.** The `external/ReqogniLoom` submodule and `CLAUDE.md` both appeared "modified"/stale in one track's initial snapshot but were clean/accurate on re-check, most likely because a concurrent agent in this same 5-track audit (or the earlier PR #28 merge work) touched them between snapshots. Not a defect — flagged for awareness only.
3. **Two parallel dependency-pinning stories tell different truths.** `Dockerfile.test` (pinned correctly to `2025.3.0`) is why `docs/state.md`'s "69/69 unit tests green" claim is plausible and *not* contradicted by CI-1/2/3 — that claim was verified through the correctly-pinned Docker path, never through the CI path, which is pinned differently and has always been broken.
4. **CLAUDE.md/AGENTS.md's file-tree accuracy fix and their prose fix are two different pieces of work that only one of them received.** Whatever process corrected the "Architektur" ASCII tree (most likely today's PR #28 merge) did not touch "Besondere Patterns" 30 lines below — worth remembering next time either file is regenerated: check both sections, not just the tree.

---

## 5. What to do next

See the accompanying implementation plan: **`docs/superpowers/plans/2026-09-04-system-audit-remediation.md`**, which sequences all of the above into concrete, TDD-sized tasks (P0 fixes that unblock everything else, then P1 correctness/security/docs, then a P2 hardening backlog).
