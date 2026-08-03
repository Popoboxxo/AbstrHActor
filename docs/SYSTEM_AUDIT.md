# System Audit — AbstrHActor (`custom_components/abstractor`)

**Audit date:** 2026-08-03
**Auditor:** Documentation Agent (documentation-only task; no source, test, generated-file, submodule, or git-state changes were made; nothing was committed)
**Audited state:** Git working tree at commit `368f4a0` ("Initial test") **plus uncommitted working-tree changes** (see observation O-01). All statements below refer to the working-tree state as inspected, unless noted.

---

## 1. Executive Summary

AbstrHActor is a Home Assistant custom integration whose stated value proposition (README, `docs/REQUIREMENTS.md`) is **hardware/source replacement without touching automations, dashboards, or utility meters** — i.e., a stable abstract entity identity across source swaps. The audit confirms that the *implemented* runtime path is clean and small:

**config/options flow → one shared `DataUpdateCoordinator` → one filter pipeline per config entry → one `AbstractorSensor` (CoordinatorEntity) per entry.**

That core path is real, readable, and uses current HA APIs (`ConfigFlow` with unique IDs, `OptionsFlow`, `DataUpdateCoordinator`, `CoordinatorEntity`, `EntityDescription`-style declarative attrs, `Store`-based persistence, native diagnostics). However, the audit found **one critical, requirement-violating defect**, several **high/medium gaps in test coverage, CI, and dead code**, and a **large drift between the target architecture documentation and the actual implementation**.

The single most important finding:

> **F-01 (Critical):** Replacing source entities via the Options Flow changes the abstract sensor's entity `unique_id` (and therefore its `entity_id`). This directly violates MUST-requirement **REQ-CORE-001** (`docs/REQUIREMENTS.md:9`), contradicts the README's headline promise (`README.md:105–108`), and contradicts the coverage claim FA-03 (`docs/REQUIREMENTS_COVERAGE.md:9`). The integration's core "swap hardware, keep your logic" promise is broken by the code as written.

Secondary headline findings:

- **F-02 (High):** No CI at all. The `.github/workflows` directory promised in `AGENTS.md:63` (HACS Action + Hassfest validation) does not exist; there is no automated validation of the repository.
- **F-03 (High):** The sensor platform (`sensor.py`) has **0 % test coverage** and `__init__.py` lifecycle (`async_setup_entry`/`async_unload_entry`) is largely uncovered — no dedicated sensor tests and no `__init__` lifecycle tests exist.
- **F-04 (Medium):** The config-flow test is essentially happy-path only (single source, no error/abort/options-flow cases).
- **F-05 … F-09 (Medium):** Silent `device_type` defaulting to `power`; hardcoded debug-notification targets; `DeviceRegistry` instantiated but never wired; `InfluxExporter` is a no-I/O stub that is never instantiated; spike-filter state is in-memory only (lost on restart *and* on every options reload).
- **F-10 (Medium):** Native pytest **cannot run on Windows**: the HA pytest plugin imports the Unix-only `fcntl` module. Reproduced on this machine (exact chain in §4.10). A Docker-based workaround exists and is documented.
- **F-11 (Low) / F-12 (Low):** Target docs (`AGENTS.md`) list a bridge/backend layer, five sensor types, brand assets, three doc files, and workflow tests that do not exist in the implementation; diagnostics implement the config-entry variant but not the device-level variant named in REQ-NFA-006.

**Verdict:** Not release-ready. The release-readiness gate in §13 fails on F-01 (blocking), F-02, and F-03.

---

## 2. Scope and Method

### 2.1 Scope

- **In scope:** everything under `custom_components/abstractor/` (implementation), `tests/` (test suite), root delivery metadata (`hacs.json`, `manifest.json`, `strings.json`, `icons.json`, `services.yaml`), delivery/infra files (`Dockerfile.test`, `docker-compose.test.yml`, `scripts/`), and specification/documentation (`README.md`, `info.md`, `docs/REQUIREMENTS.md`, `docs/REQUIREMENTS_COVERAGE.md`, `AGENTS.md` architecture section).
- **Out of scope (read-only / context only):** git submodules (`.agent-meta/`, `external/ReqogniLoom/`), knowledge-engine directories, `graphify-out/` artifacts, `docs/find.md`, `LASTENHEFT_ABSTRAKTIONS_INTEGRATION.md` (referenced but not audited for content), and the `compose/`, `docker/`, `run/`, `test/` (empty) directories.
- **No files were modified** during this audit.

### 2.2 Method

1. **Inventory:** recursive listing of the component, tests, docs, and root; `git ls-files` for tracked-vs-untracked truth.
2. **Static reading:** every Python file in `custom_components/abstractor/` and `tests/` was read in full (not skimmed); all JSON/YAML delivery files were read in full.
3. **Cross-check of every claim against primary evidence:** every finding below cites exact file paths and line numbers that were verified by reading the file at audit time.
4. **Runtime probe (read-only):** native `pytest --collect-only` was executed against the system Python 3.14 environment to reproduce the Windows `fcntl` failure (F-10). No test code was executed to completion; **no claim of passing tests is made anywhere in this document.**
5. **Git state:** `git status --short` and `git log --oneline -5` were read (read-only) for the worktree-context observation (O-01).

### 2.3 Validation limitations

- The test suite was **not** executed (Linux/Docker container was not run; native execution is impossible on Windows, see F-10). All statements about coverage rest on the *stale generated artifact* `test-results/coverage.xml` (see O-03) and on static analysis of the test files.
- Static analysis only — no runtime behavior of Home Assistant was observed; findings about runtime behavior are inferences from code, clearly labeled as such where relevant.
- The submodule `external/ReqogniLoom` is newly added (`A` in `git status`) and was excluded from inspection.

---

## 3. Architecture versus Implementation

### 3.1 Documented target architecture (as written)

`AGENTS.md` (lines ~26–64) specifies a target architecture containing, among others:

| Target item | Promised in | Actual state |
|---|---|---|
| `bridge/serial_bridge.py`, `bridge/mqtt_bridge.py`, `bridge/http_bridge.py` | `AGENTS.md:38–40` | **Absent.** `custom_components/abstractor/bridge/` is an empty directory. |
| `sensor_types/temperature.py`, `humidity.py`, `pressure.py`, `power.py`, `water.py` | `AGENTS.md:43–47` | **Absent.** `custom_components/abstractor/sensor_types/` is empty. Only `power`, `energy`, `water` exist as strings (`const.py:19–27`). |
| `brand/icon.png`, `brand/logo.png` | `AGENTS.md` tree | **Absent.** `custom_components/abstractor/brand/` is empty. |
| `tests/test_bridge.py`, `tests/test_device.py` | `AGENTS.md:55–56` | **Absent.** |
| `docs/ARCHITECTURE.md`, `docs/SENSOR_TYPES.md` | `AGENTS.md:59–60` | **Absent.** `docs/` contains only `REQUIREMENTS.md`, `REQUIREMENTS_COVERAGE.md`, `find.md`. |
| `.github/workflows/validate.yaml` (HACS Action + Hassfest) | `AGENTS.md:63` | **Absent.** No `.github/` directory exists at all. |
| `docs/CODEBASE_OVERVIEW.md` (referenced in `AGENTS.md:217` for session handoff) | `AGENTS.md:217` | **Absent.** |

Verified by: root and `docs/` directory listings, `git ls-files` (no files tracked under `bridge/`, `sensor_types/`, `brand/`, `.github/`, `docs/ARCHITECTURE.md`, etc.), and grep for the promised module names (matches only inside `AGENTS.md` itself).

### 3.2 Actual implemented architecture

The implemented integration is a **deliberately simpler design** than the target document, consisting of 8 Python modules plus metadata:

```
Config Flow / Options Flow (config_flow.py)
        │  creates/edits ConfigEntry (data: device_type, source_entity_id(s))
        ▼
async_setup_entry (__init__.py)
        │  creates shared AbstractorDataUpdateCoordinator (coordinator.py)
        │  creates DeviceRegistry instance (never used afterwards — F-07)
        │  coordinator.add_entry(entry) → per-entry AbstractorFilterPipeline (filters.py)
        ▼
AbstractorDataUpdateCoordinator._async_update_data  (every 30 s, one poll for ALL entries)
        │  reads raw states of source entities from hass.states
        │  per entry: pipeline.process_sources(...) → value (or None)
        │  per entry: optional dedup debug notify (hardcoded targets — F-06)
        ▼
AbstractorSensor (sensor.py, CoordinatorEntity + SensorEntity)
        │  native_value ← coordinator.data[entry_id]
        │  unique_id derived FROM SOURCE ENTITY IDS (F-01)
```

Side modules: `snapshot.py` (versioned export/import helpers), `diagnostics.py` (config-entry diagnostics), `influx_exporter.py` (no-I/O stub, never instantiated — F-08), `repository/device_registry.py` (instantiated, never used — F-07).

**Assessment:** The implemented path is internally coherent, HA-convention-compliant (single shared poller, `has_entity_name`, `CoordinatorEntity`, unique IDs, Store persistence), and honestly documented in `README.md` ("Architecture" section, `README.md:40–80`). The gap is between `AGENTS.md` (aspirational, describes a much larger Bridge+Strategy system) and reality — not between `README.md` and reality (except F-01/F-08 claims, see §11).

---

## 4. Detailed Findings

Severity scale used: **Critical** (violates a MUST requirement or breaks the product's core promise), **High** (blocks release quality/validation), **Medium** (correctness/robustness risk or significant maintainability gap), **Low** (documentation drift / polish). Every finding is tagged **CONFIRMED** (directly verified in code/artifacts during this audit) or **OBSERVATION** (inferred, contextual, or a risk assessment).

### 4.1 F-01 — Source replacement breaks entity identity (unique_id/entity_id) — **Critical — CONFIRMED**

**What:** The abstract sensor entity's `unique_id` is derived from the **source entity IDs**, not from a stable per-configuration identity.

**Evidence:**
- `custom_components/abstractor/sensor.py:64–70`
  ```python
  if len(source_entity_ids) == 1:
      # Keep the first MVP's ID stable for existing single-source entries.
      self._attr_unique_id = f"abstractor_{source_entity_ids[0]}_{device_type}"
  else:
      self._attr_unique_id = (
          f"abstractor_{device_type}_{'_'.join(sorted(source_entity_ids))}"
      )
  ```
- The source list is recomputed on every setup from `{**entry.data, **entry.options}` (`sensor.py:36–40`).
- The Options Flow writes new sources into `entry.options` (`config_flow.py:99–133`, entry created at `config_flow.py:103–104`).
- An options change triggers a full entry reload: `__init__.py:98–100` (`_async_options_updated` → `async_reload`), which re-runs `async_setup_entry` → re-runs the sensor platform setup with the *new* sources → new `unique_id`.

**Requirement/docs contradictions (all verified):**
- `docs/REQUIREMENTS.md:9` — REQ-CORE-001 (MUST): "…kann der abstrahierte Sensor auf ein neues Quell-Gerät umkonfiguriert werden, **ohne dass sich die `entity_id` oder `unique_id` des abstrahierten Sensors für den Nutzer ändert**."
- `README.md:105–108` — "replace the source entities, and save. **The abstract sensor's `entity_id` and `unique_id` stay stable** — dashboards, automations, and utility meters keep working."
- `docs/REQUIREMENTS_COVERAGE.md:9` — FA-03: "Sources can be changed through Options Flow and reloaded **safely**."

**Why it matters:** In Home Assistant, the entity registry derives `entity_id` from `unique_id`. When the `unique_id` changes, HA registers a **new** entity (new `entity_id`); the old entity is orphaned and goes `unavailable`. Every automation, dashboard card, and utility-meter input referencing the old `entity_id` stops working — precisely the outcome the integration exists to prevent. Note also that the config-entry-level `unique_id` (`config_flow.py:50–53`) *does* stay stable (it is stored at creation and never updated), which masks the problem at the entry level while the *entity-level* identity still breaks.

### 4.2 F-02 — No CI / no `.github/workflows` — **High — CONFIRMED**

**What:** The repository contains no GitHub Actions workflows at all.

**Evidence:**
- Root directory listing shows no `.github/` directory; glob `**/.github/**` returns no files; `git ls-files` shows nothing under `.github/`.
- `AGENTS.md:63` promises `.github/workflows/validate.yaml` ("HACS Action + Hassfest validation on push/PR").
- `README.md` and `info.md` never claim CI, so the mismatch is purely against `AGENTS.md` — but the *absence* of any automated validation stands independently.

**Why it matters:** For a HACS-delivered integration, Hassfest (manifest/HACS validation) and the HACS Action are the standard quality gates. Their absence means nothing automatically verifies `manifest.json`, `hacs.json`, `strings.json`/`icons.json` consistency, or Python style on push/PR. Every quality signal in this repository today comes from manual/local runs.

### 4.3 F-03 — No sensor-platform tests and no `__init__` lifecycle tests — **High — CONFIRMED**

**What:** The entity layer and the integration lifecycle are effectively untested.

**Evidence:**
- `tests/` contains exactly: `conftest.py`, `test_config_flow.py`, `test_coordinator.py`, `test_diagnostics.py`, `test_filters.py`, `test_services.py`, `test_snapshot.py` (directory listing; `git ls-files` agrees).
- **No `test_sensor.py`** and **no test file covering `__init__.py`** (`async_setup_entry`, `async_unload_entry`, `async_migrate_entry`, `_async_options_updated`, service registration).
- The last generated coverage artifact (`test-results/coverage.xml:2`, generated 2026-08-02 in a Linux container at `/workspace`) reports per-file line rates: `sensor.py` **0.0**, `influx_exporter.py` **0.0**, `__init__.py` **0.4865**, `coordinator.py` **0.4182**, overall **0.5623**. (Artifact only — see O-03; no claim that the suite currently passes is made.)
- Static confirmation of the same: `__init__.py` line range 31–73 (`async_setup_entry` body) is listed as hit=0 in the artifact, consistent with the absence of lifecycle tests.

**Why it matters:** The sensor platform is the user-facing surface (device_class, unit, state_class, unique_id stability — the F-01 defect lives here) and the lifecycle is the HA-integration contract. Both are currently covered only by static reading.

### 4.4 F-04 — Config-flow test is essentially happy path — **Medium — CONFIRMED**

**What:** `tests/test_config_flow.py` contains exactly one test, `test_form` (`test_config_flow.py:14–41`), covering the single-source success path with `device_type=power` and a mocked `async_setup_entry`.

**Untested branches (all real, reachable code):**
- The `source_required` error path (`config_flow.py:40–45`).
- Multi-source normalization and `CONF_SOURCE_ENTITY_IDS` cleanup (`config_flow.py:46–49`).
- `_abort_if_unique_id_configured()` duplicate-entry abort (`config_flow.py:55`).
- The **entire Options Flow** (`config_flow.py:92–133`) — none of `async_step_init`, schema defaults, or the create-entry branch is exercised.
- `async_migrate_entry` (`__init__.py:93–96`).

**Why it matters:** The AGENTS.md project conventions mandate "100 % test coverage for config flow". Measured against the *current* test, coverage of the flow module is partial (the artifact shows `config_flow.py` at 0.825 line rate) and the most security/UX-relevant branches (abort, validation errors, options) are untested.

### 4.5 F-05 — Coordinator silently defaults missing `device_type` to `power` — **Medium — CONFIRMED**

**What:** The coordinator injects a fallback `device_type` into the per-entry pipeline config, silently.

**Evidence:** `coordinator.py:36–38`
```python
config = {**entry.data, **entry.options}
config["device_type"] = config.get("device_type", "power")
self.pipelines[entry.entry_id] = AbstractorFilterPipeline(config)
```

**Why it matters / inconsistencies:**
- The same missing key is handled differently elsewhere: `sensor.py:35` uses `entry.data.get(CONF_DEVICE_TYPE, "")` → empty string → no `device_class`/`unit_of_measurement` and `name = ""`; `filters.py:83` treats missing `device_type` as fail-soft-like-`power`.
- A misconfigured/legacy entry therefore silently behaves like a power sensor in the pipeline (fail-soft to 0) while its entity presents no device metadata — divergent, invisible behavior. The config flow makes `device_type` required, so this only triggers on corrupted/legacy entries — but it should fail loudly or be consistent, not silently assume `power`.

### 4.6 F-06 — Debug notification targets are hardcoded — **Medium — CONFIRMED**

**What:** The debug-notification path is coupled to two hardcoded HA entity/service names that are not part of this integration.

**Evidence:** `coordinator.py:73–90` (`_async_notify_debug`):
- `coordinator.py:80` — `self.hass.states.is_state("input_boolean.automation_debugger", "on")`
- `coordinator.py:82` — `self.hass.services.has_service("notify", "adminnotificationgroup")`
- `coordinator.py:84–89` — `async_call("notify", "adminnotificationgroup", …)`

**Why it matters:** The notification only fires if the user happens to have a toggle named `input_boolean.automation_debugger` and a notify group named `adminnotificationgroup`. The names are neither configurable nor owned by the integration. `docs/REQUIREMENTS_COVERAGE.md:13` (FA-13) documents this coupling, so it is a *known, documented* design choice — but it remains a hardcoded cross-integration dependency and will silently no-op on installs lacking those entities.

### 4.7 F-07 — `DeviceRegistry` is instantiated but never wired — **Medium — CONFIRMED**

**What:** A repository-pattern registry class exists and is created, but nothing ever calls it.

**Evidence:**
- Defined: `repository/device_registry.py:6–22` (`register_device`, `get_device`).
- Instantiated: `__init__.py:44–45` (`domain_data["registry"] = DeviceRegistry()`); removed at `__init__.py:86`.
- Grep for `registry` across the component: only `__init__.py:20,44,45,86`, `snapshot.py:14,38` (docstrings) match. `register_device`/`get_device` have **zero call sites**; `coordinator.py` and `sensor.py` never touch it.

**Nuance:** The README feature "Device registry integration — each abstract sensor appears as a logical device in the HA device registry" (`README.md:37–38`) is *actually satisfied* — but by `DeviceInfo(...)` in `sensor.py:72–77`, not by the `DeviceRegistry` class. The class is dead weight: 22 lines that create the impression of a repository layer while the real integration relies on HA's own registry. Decide: delete it or wire it (e.g., to persist source→device mappings for the F-01 fix).

### 4.8 F-08 — `InfluxExporter` has no I/O and is never instantiated — **Medium — CONFIRMED**

**What:** The telemetry push path (REQ-DATA-002, SOLL) is a log-only stub that is never activated.

**Evidence:**
- `influx_exporter.py:15–16` — `async_push` only logs: `_LOGGER.debug("Pushing %s=%s to InfluxDB", entity_id, value)`. No network code, no client, no retry.
- `coordinator.py:30` — `self.influx_exporter = None`; the only call site is guarded by `if self.influx_exporter and val is not None:` (`coordinator.py:69–70`), which can never be true as written.
- `InfluxExporter.__init__` (`influx_exporter.py:8–13`) has no caller anywhere (grep: only the class definition and the `None` assignment).

**Mitigating context:** This is *honestly documented*: `README.md:224–226` ("InfluxDB push is scaffolded only … not yet wired"), and `REQUIREMENTS_COVERAGE.md:39–41` lists it as out of scope for the MVP. Severity is therefore Medium, not High: dead code plus an unmet SOLL requirement, but no false claim in the user-facing docs.

### 4.9 F-09 — Spike-filter state is in-memory only — **Medium — CONFIRMED**

**What:** The monotonic guard's last-valid value lives only in a process-memory instance attribute.

**Evidence:**
- `filters.py:14` — `self._last_valid_state: float | None = None`, mutated at `filters.py:44` and `filters.py:79`; the guard compares against it at `filters.py:39–42` and `filters.py:69–77`.
- **Lost on restart:** the attribute starts `None` on every HA start.
- **Lost on reload:** `coordinator.add_entry` rebuilds the pipeline object on *every* `async_setup_entry` (`coordinator.py:38`), and the options flow reloads the entry (`__init__.py:98–100`). So every options save resets the guard, and the first poll after a restart sees `_last_valid_state is None` — a genuine counter drop (e.g., after a device reset during downtime) passes the guard once.

**Why it matters:** For `total_increasing` energy/water sensors, one unguarded low reading after restart/reload can corrupt a long-term utility-meter total — the exact scenario REQ-COMP-001 (`REQUIREMENTS.md:19`) exists to prevent. Not listed in the README "Known limitations" section (`README.md:206–226`). (Fixing identity per F-01 — e.g., persisting a stable per-entry value — would also be the natural place to persist the last-valid state.)

### 4.10 F-10 — Native pytest cannot run on Windows (HA plugin imports `fcntl`) — **Medium — CONFIRMED (reproduced)**

**What:** The documented host-level test entrypoint fails at import/collection time on Windows because the HA pytest plugin chain imports the Unix-only `fcntl` module.

**Reproduction (this machine, read-only, `collect-only`):**
```
C:\Users\duchr\AppData\Local\Programs\Python\Python314\python.exe -m pytest tests/test_filters.py --collect-only -q
```
Result:
```
pytest_homeassistant_custom_component\plugins.py:58
pytest_homeassistant_custom_component\patch_time.py:99
    from homeassistant import runner
homeassistant\runner.py:9
    import fcntl
ModuleNotFoundError: No module named 'fcntl'
```
Environment at reproduction time: Python 3.14, pytest 9.1.1, pytest-homeassistant-custom-component 0.13.351, homeassistant 2026.8.0b3 (site-packages). Note the HA version there is a **beta** (see O-04).

**Mitigating context:** The repository ships a documented, Dockerized test stack that sidesteps this (`Dockerfile.test`, `docker-compose.test.yml`, `scripts/run_tests.sh`, `scripts/run_tests.ps1`, `scripts/entrypoint.sh`; README `README.md:147–204`), and `test-results/coverage.xml` shows a successful containerized run from 2026-08-02. So the failure mode is "host-native Windows testing is impossible," not "testing is impossible." Still, it blocks the default developer workflow on Windows and is worth a documented note in the README (currently only the Docker path is described).

### 4.11 F-11 — Target documentation lists many modules absent from the implementation — **Low — CONFIRMED**

**What:** `AGENTS.md` describes an architecture with a bridge layer, five sensor types, brand assets, workflow tests, and three documentation files that do not exist. See the table in §3.1 for the full inventory and evidence.

**Why it matters:** As a roadmap, `AGENTS.md` is fine; as an *accurate* description of the repository it is misleading — exactly the class of drift `docs/CODEBASE_OVERVIEW.md` (itself absent) is meant to prevent. The README, by contrast, is accurate about what exists (except F-01/F-08 nuances discussed in §11).

### 4.12 F-12 — Diagnostics implement only the config-entry API, not the device-level API named in the requirement — **Low — CONFIRMED**

**What:** REQ-NFA-006 (`docs/REQUIREMENTS.md:44`) names `async_get_device_diagnostics`; the implementation provides only `async_get_config_entry_diagnostics`.

**Evidence:** `diagnostics.py:13–27` implements `async_get_config_entry_diagnostics` only. The requirement text (`REQUIREMENTS.md:44`): "Die Integration MUSS die native HA Diagnostics-API (`async_get_device_diagnostics`) implementieren."

**Nuance:** Config-entry diagnostics is a valid HA diagnostics API and is what most single-config-entry integrations ship; the requirement's letter names the device variant. Behaviorally the data exposed (`diagnostics.py:19–26`: entry dict, coordinator data, pipeline config) would serve both.

### 4.13 O-01 — Dirty worktree (audit-context observation) — **OBSERVATION**

`git status --short` at audit time shows substantial uncommitted state, including:
- **Modified tracked files in scope:** `README.md` (+221 lines), `custom_components/abstractor/config_flow.py`, `custom_components/abstractor/sensor.py`, `custom_components/abstractor/strings.json`, `tests/test_services.py`.
- **Untracked (not yet committed) delivery files:** `Dockerfile.test`, `docker-compose.test.yml`, `requirements.txt`, `requirements_test.txt`, `scripts/` (incl. `run_tests.ps1`, `run_tests.sh`, `entrypoint.sh`), `docs/find.md`.
- **Modified out of scope (context):** `.agent-meta` (submodule), `.meta-config/*`, `AGENTS.md`, `CLAUDE.md`, `graphify-out/*`, `info.md`; **newly added submodule** `external/ReqogniLoom`.
- Last commits: `368f4a0 Initial test`, `f49359a initial Import`, `7671959 check initial add`.

This is treated as **audit context only** — the audit describes the working tree as inspected. It is not itself a product defect (uncommitted work is a normal pre-release state), but it means: (a) the audited implementation differs from the last commit in `config_flow.py`/`sensor.py`/`strings.json`/`test_services.py`, and (b) a release would have to decide what belongs in the artifact.

### 4.14 O-02 — Entry-level vs. entity-level unique-ID formats diverge; options never update the entry unique ID — **OBSERVATION**

- Config-flow entry unique ID: `abstractor_{device_type}_{'_'.join(sorted(sources))}` (`config_flow.py:50–53`).
- Single-source entity unique ID: `abstractor_{source}_{device_type}` — different order (`sensor.py:66`).
- The entry `unique_id` is set once at creation and never touched by the options flow, so after source changes the entry ID describes stale sources. Consequence (example): user creates entry with sources `[A, B]` (ID `abstractor_power_A_B`), later changes options to `[C]`, then later tries to create a new entry with `[A, B]` → `_abort_if_unique_id_configured()` aborts because the stale ID still occupies the namespace. A latent UX trap, plus the entity-level break of F-01.

### 4.15 O-03 — `test-results/coverage.xml` is a stale, container-generated artifact — **OBSERVATION**

`test-results/coverage.xml` (generated 2026-08-02, coverage.py 7.6.8, source root `/workspace/custom_components/abstractor` — i.e., produced inside the Docker image, not on this host) reports: lines-valid 345, lines-covered 194, line-rate **0.5623**; per-file: `sensor.py` 0.0, `influx_exporter.py` 0.0, `__init__.py` 0.4865, `coordinator.py` 0.4182, `config_flow.py` 0.825, `filters.py` 0.8667, `snapshot.py` 0.76, `repository/device_registry.py` 0.6, `const.py`/`diagnostics.py` 1.0. It is used here only as corroborating evidence for F-03/F-04/F-08 and is **not** treated as proof that the suite currently passes.

### 4.16 O-04 — Host environment's HA is a beta; test env must use the pinned Docker image — **OBSERVATION**

The global Python 3.14 site-packages contains `homeassistant 2026.8.0b3` (beta) — that is the environment in which F-10 was reproduced. The reproducible path is the Docker image pinning `homeassistant==2025.1.4` (`Dockerfile.test:25`) with an overridable build arg. Testing against a beta host install is a compatibility hazard; use the container.

### 4.17 O-05 — Empty scaffolding directories — **OBSERVATION**

`custom_components/abstractor/bridge/`, `sensor_types/`, and `brand/` exist as **empty** directories on disk and are untracked by git (git does not track empty directories). They are forward-looking scaffolding matching the `AGENTS.md` roadmap (§3.1) but contribute nothing to the current artifact; HACS packaging will simply ignore them.

### 4.18 O-06 — Other SOLL-level requirements intentionally not implemented — **OBSERVATION**

- REQ-SENS-003 Riemann energy integration (`REQUIREMENTS.md:35`) — not implemented; not claimed.
- REQ-UTIL-001 built-in utility meter (`REQUIREMENTS.md:27`) — not implemented; documented as delegated to HA (`README.md:213–216`).
- REQ-COMP-004 conditional cross-entity fallback (`REQUIREMENTS.md:22`) — not implemented; documented (`README.md:221–223`).
- REQ-DATA-002 InfluxDB — scaffolded only (F-08).
These are SOLL ("should") items, so their absence is not a defect; listed for completeness.

### 4.19 O-07 — `async_migrate_entry` is a no-op acceptance — **OBSERVATION**

`__init__.py:93–96` returns `config_entry.version <= 1` without transforming data. Acceptable while the schema is at VERSION 1, but it is a standing trap for future schema changes (REQ-NFA-004, `REQUIREMENTS.md:42`, demands automatic migration scripts for breaking changes).

---

## 5. Impact Analysis

| Area | Impact |
|---|---|
| **Core value proposition** | F-01: a source swap silently creates a new entity and orphans the old one. Automations, dashboard cards, and utility-meter inputs pointing at the old `entity_id` go stale/unavailable — the exact failure the integration promises to prevent. Highest user-facing impact; likely to surface as support issues immediately after first "swap a device" usage. |
| **Data integrity (energy/water)** | F-09: after every restart and every options reload, the monotonic guard forgets the last valid reading, so a single low/counter-reset sample passes the guard and can corrupt `total_increasing` totals consumed by utility meters. F-05 can additionally cause silent fail-soft-to-0 behavior for misconfigured entries. |
| **Release / quality gates** | F-02: no automated validation exists; HACS/Hassfest checks never run automatically. F-03/F-04: the untested entity layer is where F-01 lives; the config-flow error/abort branches are untested despite a stated 100 % coverage convention. |
| **Maintainability / dead code** | F-07/F-08: ~40 lines of unwired code (`DeviceRegistry`, `InfluxExporter`) plus the empty scaffolding dirs (O-05) inflate the perceived system while doing nothing; F-08's guard (`coordinator.py:69`) is permanently false. |
| **Developer experience** | F-10: native test execution is impossible on Windows (reproduced); all testing is Docker-mediated (which works, but is the only path). |
| **Documentation trust** | F-11/F-12/O-02: `AGENTS.md` describes a system that does not exist; `REQUIREMENTS_COVERAGE.md` FA-03 claims source changes are "safe" (contradicted by F-01); the README over-promises identity stability. |

---

## 6. Recommendations (per finding)

- **F-01 (blocker):** Decouple the entity `unique_id` from the source list. Use a stable, user-invisible identity generated once per config entry (e.g., a stored UUID or the entry's own ID derived at creation), and keep the *sources* purely as data. Recommended shape: `self._attr_unique_id = f"{DOMAIN}_{entry_id}"` or a persisted `stable_id` in `entry.data`, with a migration path for existing entries (REQ-CORE-003/REQ-NFA-004, `REQUIREMENTS.md:11,42`). Then update README's claim only after the code actually honors it.
- **F-02:** Add `.github/workflows/validate.yaml` running the official HACS Action and Hassfest (`home-assistant/actions/hassfest` + `hacs/action`) on push/PR — matching `AGENTS.md:63`.
- **F-03:** Add `tests/test_sensor.py` (unique-id stability across source changes, device_class/unit/state_class per type, `native_value` propagation, availability via coordinator) and `tests/test_init.py` (setup/unload with multiple entries, service registration/deregistration, options-reload listener, snapshot persistence).
- **F-04:** Extend `tests/test_config_flow.py`: `source_required` error, multi-source normalization, duplicate unique-ID abort, options-flow step (schema defaults, save branch), migration.
- **F-05:** Stop silently defaulting `device_type` to `power`. Either reject entries without a valid `device_type` (coordinator raises/logs error) or make the default explicit and identical in `coordinator.py`, `sensor.py`, and `filters.py`.
- **F-06:** Move the two hardcoded names into options (configurable debug-toggle entity and notify target), or drop the notify hook; at minimum, document the dependency in README Known limitations (it is currently only in `REQUIREMENTS_COVERAGE.md`).
- **F-07:** Either wire `DeviceRegistry` to something real (persist per-entry device metadata used by the F-01 fix) or remove it and its instantiation.
- **F-08:** Either implement actual InfluxDB line-protocol push behind the existing option guard, or remove the class and the dead `coordinator.py:69–70` branch; keep the README limitation accurate in either case.
- **F-09:** Persist `_last_valid_state` in HA storage per entry (e.g., in the same `Store` used by `__init__.py:35`) and reload it when the pipeline is (re)built; document the residual gap in README.
- **F-10:** Document in README that host-native pytest does not work on Windows (with the `fcntl` chain) and that the Docker path is the supported one; optionally add an `os.name == "nt"` skip/early-exit note. Consider a `pyproject.toml`/`conftest` guard that prints a clear message instead of a raw traceback.
- **F-11:** Reconcile `AGENTS.md` with reality (either as roadmap with explicit "planned" markers or updated to the implemented architecture) once the implementation stabilizes; create the missing `docs/CODEBASE_OVERVIEW.md`/`ARCHITECTURE.md` or drop their references.
- **F-12:** Implement `async_get_device_diagnostics` delegating to the existing entry diagnostics, or amend the requirement to the config-entry API.

---

## 7. Security

No exploitable issues were found in a static review; the integration has a small attack surface:

- **No network I/O** in the shipped code path (`manifest.json:10` `"requirements": []`; no sockets, no HTTP clients). The only network-oriented class, `InfluxExporter`, is a stub with no I/O (F-08) — no credential handling exists anywhere, which is currently safe *because* it is inert, but any future implementation must treat host/token/org/bucket as secrets (`influx_exporter.py:8` constructor params exist already).
- **Service schema is validated:** `IMPORT_SERVICE_SCHEMA` (`__init__.py:27–29`) runs `validate_snapshot` on the import payload; `validate_snapshot` (`snapshot.py:33–55`) enforces the format/version/shape. Import writes to HA `.storage/` only (no entry recreation), so it cannot be used to inject config entries.
- **No shell execution, no `eval`, no dynamic imports** anywhere in the component.
- **Exposure of raw states:** sources are read via `hass.states` (`coordinator.py:58–61`); arbitrary source entity IDs are accepted (entity-selector UI-bound, but the service/import path doesn't create entries, limiting abuse).
- **Debug notification** can only *send* messages to a user-defined notify group when a user-defined toggle is on (F-06) — a minor spam/abuse surface, bounded by the toggle and dedup (`coordinator.py:78–79`).

**Security caveat (audit limitation):** no dependency/SCA scan was run; `requirements.txt`/`requirements_test.txt` pin no versions for the test deps (only `homeassistant>=2025.1`), and the Docker image pins only HA (`Dockerfile.test:25`) while installing `pytest-homeassistant-custom-component`, `ruff`, `mypy` unpinned (`Dockerfile.test:54–60`) — supply-chain hygiene for dev deps is weak, though not shipped to users.

---

## 8. Reliability and Data Integrity

- **F-09 (in-memory spike state)** is the main data-integrity risk: guard resets on restart and on every options reload; one bad sample post-reset can corrupt `total_increasing` totals (REQ-COMP-001, `REQUIREMENTS.md:19`).
- **F-05 (silent `power` default)** can silently change fail-soft/fail-closed semantics for corrupted entries: pipeline treats a missing `device_type` as fail-soft (`filters.py:83`), while the sensor entity shows no unit/device_class (`sensor.py:35`).
- **Notification inside the poll loop:** `_async_update_data` awaits `_async_notify_debug` for every entry on every cycle (`coordinator.py:67`). A raise inside `async_call` would fail the entire poll and mark **all** entries unavailable (the service-exists guard at `coordinator.py:82` mitigates the most likely cause). Low probability, high blast radius; consider wrapping in try/except.
- **Snapshot durability:** `_save_snapshot` is called at setup and on last-entry unload (`__init__.py:71,87`), and the values in it are the coordinator's last poll — best effort, not a WAL; acceptable for a support snapshot, but it is *not* a backup of recorder history (correctly stated in README `README.md:14–18,217–220`).
- **Error handling in the pipeline** is solid where it matters: NaN/inf/`unavailable`/`unknown`/`none` are bounded (`filters.py:20–34`), non-numeric values produce `None` rather than raising, and fail-closed behavior protects utility meters (REQ-COMP-002/003, `REQUIREMENTS.md:20–21`).
- **Coordinator data dict** only contains keys for entries that produced values (None results are still stored as `None` at `coordinator.py:66` — `native_value` then returns `None`, which SensorEntity renders as `unknown`; consistent).

---

## 9. Testing

**Facts (verified, no claims of passing runs):**

- Test inventory: 7 test modules, ~13 test functions total, covering: filters (7 tests incl. spike/NaN/fail-soft/fail-closed/invert/event), snapshot validation (2), services (2), diagnostics (1), coordinator debug-notify (1), config flow (1). Sources: `tests/*.py` as read; counts are from reading the files.
- **Not covered:** `sensor.py` (F-03, artifact 0 %), `__init__.py` lifecycle (F-03, artifact 48.65 %), `influx_exporter.py` (F-08, artifact 0 %), config-flow error/abort/options branches (F-04), `coordinator._async_update_data` core polling loop (artifact 41.82 % overall coordinator), `repository/device_registry.py` (no test file; artifact 0.6 via incidental import only).
- **Executability:** native pytest fails on Windows (F-10, reproduced). The Docker path (`docker-compose.test.yml:38`) is the supported runner; the last generated `coverage.xml` indicates a successful containerized run on 2026-08-02 (O-03), which is consistent with the Docker stack being functional — but the suite's current pass/fail status was **not** re-verified in this audit.
- The stated convention of "100 % test coverage for config flow" (AGENTS.md conventions) is not met (F-04).

---

## 10. CI / Operations

- **No CI:** no `.github/` at all (F-02). No HACS Action, no Hassfest, no lint/test job runs on push/PR.
- **Local ops tooling exists and is coherent:** `Dockerfile.test` (pins HA 2025.1.4, installs pytest/ruff/mypy; `Dockerfile.test:25,54–60`), `docker-compose.test.yml` (pytest service + lint profile; `docker-compose.test.yml:27–53`), `scripts/entrypoint.sh` (dispatch pytest/lint/shell; `entrypoint.sh:19–48`), `scripts/run_tests.sh`/`run_tests.ps1` (Linux/macOS and Windows wrappers; verified present). README documents usage accurately (`README.md:147–204`).
- **Packaging metadata:** `hacs.json` (min HA 2025.1.0, `render_readme: true`) and `manifest.json` (version 1.0.0, `iot_class: local_polling`, empty `requirements`) are structurally consistent with each other and with the actual (dependency-free) code. No `brand/icon.png` exists (O-05), which HACS treats as optional but which `AGENTS.md` promised.
- **Operational gap:** no `.gitignore` verification done here for `test-results/`, `.pytest_cache/`, `.mypy_cache/`; the generated `test-results/coverage.xml` is present in the tree (tracked status not checked) — flag for the release: decide whether build artifacts are committed.
- **Release process:** no changelog, no release workflow, no semantic-version automation exists beyond the static `manifest.json` version.

---

## 11. Documentation / Specification Consistency

| Doc | Claim | Verdict vs. implementation |
|---|---|---|
| `README.md:105–108` | Source replacement keeps `entity_id`/`unique_id` stable | **FALSE (F-01)** — code derives unique_id from sources. |
| `README.md:37–38` | "Device registry integration" via logical devices | **True via `DeviceInfo`** (`sensor.py:72–77`); the `DeviceRegistry` class is unrelated dead code (F-07). |
| `README.md:224–226` | InfluxDB push "scaffolded only" | **True (F-08)** — honest. |
| `README.md:100–101` | Config flow creates "stable unique ID based on device type and source entities" | **True for the entry-level ID**; misleadingly conflatable with entity identity (F-01/O-02). |
| `docs/REQUIREMENTS_COVERAGE.md:9` FA-03 | "Sources can be changed through Options Flow and reloaded safely" | **Misleading (F-01)** — reload is safe, identity is not. |
| `docs/REQUIREMENTS_COVERAGE.md:13` FA-13 | Debug notify via hardcoded names | **True (F-06)** — documented as designed. |
| `docs/REQUIREMENTS.md:9` REQ-CORE-001 | MUST keep entity_id/unique_id on source swap | **Violated (F-01).** |
| `AGENTS.md:38–63` | Bridge layer, 5 sensor types, brand, workflows, 2 doc files | **Absent in implementation (F-11)** — roadmap text presented as structure. |
| `AGENTS.md:217` | `docs/CODEBASE_OVERVIEW.md` session handoff | **Absent file.** |
| `REQUIREMENTS.md:44` REQ-NFA-006 | `async_get_device_diagnostics` | **Partial (F-12)** — only config-entry variant. |
| `info.md:31–32` | "stable unique IDs and an options flow" | Same F-01 nuance as README. |

Overall: the **README is accurate about what exists** (data flow, services, Docker stack, limitations) but over-promises on the one claim that matters most (identity stability). The **requirements/coverage docs** over-state FA-03. **AGENTS.md** describes a target architecture, not the current one.

---

## 12. Prioritized Remediation Roadmap

**P0 — blocking (before any release):**
1. **F-01** — stable entity unique_id decoupled from sources (+ migration for existing entries).
2. **F-02** — add `.github/workflows/validate.yaml` (HACS Action + Hassfest).

**P1 — release quality (same milestone as P0, or immediately after):**
3. **F-03** — `tests/test_sensor.py` (incl. a regression test asserting unique_id stability across an options-driven source change) and `tests/test_init.py` lifecycle tests.
4. **F-04** — config-flow error/abort/options-flow tests (target the stated 100 % convention).
5. **F-09** — persist spike-filter last-valid state in HA storage; restore on pipeline (re)build.

**P2 — hardening (next iteration):**
6. **F-05** — remove silent `power` default; make device-type handling consistent across `coordinator.py`/`sensor.py`/`filters.py`.
7. **F-07** — wire or delete `DeviceRegistry`.
8. **F-08** — implement InfluxDB push behind the guard or delete the stub + dead branch.
9. **F-06** — make debug-notify targets configurable (or drop the hook and document).

**P3 — docs/hygiene:**
10. **F-10** — README note + friendly Windows guard for native pytest.
11. **F-11** — reconcile `AGENTS.md` with the implemented architecture; create `docs/CODEBASE_OVERVIEW.md`/`ARCHITECTURE.md` or remove references.
12. **F-12/O-02/O-07** — device diagnostics variant; options/entry-ID handling; real migration logic before any future schema bump; pin dev-dependency versions in `Dockerfile.test`/`requirements_test.txt`.

---

## 13. Release Readiness Gate

**Verdict: NOT READY.**

| Gate | Status | Criterion |
|---|---|---|
| Core promise verified by test | ❌ **FAIL** | A test asserting entity identity survives a source change exists nowhere; the code violates REQ-CORE-001 (F-01). |
| CI validation (HACS + Hassfest) | ❌ **FAIL** | No `.github/workflows` (F-02). |
| Sensor + lifecycle test coverage | ❌ **FAIL** | `sensor.py` 0 %, lifecycle largely uncovered (F-03). |
| Config-flow coverage | ⚠️ **PARTIAL** | Happy path only (F-04). |
| Test suite executable in documented env | ⚠️ **PARTIAL** | Containerized path exists and shows prior success (O-03); host-native Windows execution impossible (F-10). |
| Manifest/HACS metadata | ✅ **PASS** | `hacs.json`/`manifest.json` consistent; dependency-free. |
| Requirements traceability | ⚠️ **PARTIAL** | MUST requirements met except REQ-CORE-001; SOLL items documented as out of scope. |
| Docs truthfulness | ⚠️ **PARTIAL** | README accurate except identity claim; coverage doc over-states FA-03. |

**To reach "ready":** ship P0 items 1–2 and P1 items 3–5, re-run the suite in the container, and re-audit the identity claim end-to-end (options change → reload → same entity_id, recorder/utility-meter continuity).

---

## 14. Appendix

### A. Inspected files (all read in full unless noted)

**Implementation — `custom_components/abstractor/`:**
- `__init__.py` (130 lines) — setup/unload/migrate, services, storage, options listener
- `config_flow.py` (133) — config flow + options flow
- `const.py` (27) — constants, 3 sensor types
- `coordinator.py` (90) — shared DataUpdateCoordinator, pipelines, debug notify
- `sensor.py` (95) — AbstractorSensor (CoordinatorEntity)
- `filters.py` (85) — AbstractorFilterPipeline
- `snapshot.py` (55) — build/validate snapshot
- `diagnostics.py` (27) — config-entry diagnostics
- `influx_exporter.py` (17) — stub class
- `repository/device_registry.py` (22) — unused class
- `manifest.json`, `strings.json`, `icons.json`, `services.yaml` — metadata

**Tests — `tests/`:** `conftest.py`, `test_config_flow.py`, `test_coordinator.py`, `test_diagnostics.py`, `test_filters.py`, `test_services.py`, `test_snapshot.py`

**Docs/spec:** `README.md` (236), `info.md` (44), `docs/REQUIREMENTS.md` (49), `docs/REQUIREMENTS_COVERAGE.md` (42), `AGENTS.md` (architecture section; read via grep + provided content), `docs/find.md` (existence only)

**Infra:** `hacs.json`, `Dockerfile.test` (84), `docker-compose.test.yml` (53), `scripts/entrypoint.sh` (48), `scripts/run_tests.sh`/`run_tests.ps1` (126), `requirements.txt`, `requirements_test.txt`

**Artifacts/context:** `test-results/coverage.xml` (summary + class list; 413 lines total, read partially), `git status --short`, `git log --oneline -5`

**Empty dirs (untracked):** `custom_components/abstractor/bridge/`, `sensor_types/`, `brand/`; root `compose/`, `docker/`, `test/`

### B. Validation limitations

1. **No test execution:** native pytest cannot collect on Windows (F-10, reproduced); the container was not run. All coverage statements are from the stale `coverage.xml` artifact (O-03) and static analysis.
2. **Static-only runtime claims:** behavior claims (F-01 entity re-registration, F-09 reset-on-reload, F-06 no-op when entities absent) follow from HA semantics + code reading, not live observation.
3. **Working-tree state:** audited state includes uncommitted changes (O-01); the audited code differs from `git HEAD` in `config_flow.py`, `sensor.py`, `strings.json`, `test_services.py`.
4. **Submodules excluded:** `.agent-meta/` (modified submodule) and `external/ReqogniLoom` (newly added) were not inspected; their state is noted as context only.
5. **Host environment drift:** the global Python 3.14 env runs HA **2026.8.0b3 (beta)**, which does not match the Docker pin (2025.1.4) — F-10 reproduction used that beta env (O-04).
6. **No SCA/dependency scan, no lint/mypy run** was performed during this audit (documentation-only scope; tools not invoked on the component).
