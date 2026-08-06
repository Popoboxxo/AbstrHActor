STATUS: COMPLETE
RESULT: 28 findings identified (0 critical, 5 high, 9 medium, 10 low, 4 informational)
SYSTEM AUDIT: AbstrHActor v1.0.0
Repository: https://github.com/Popoboxxo/AbstrHActor
Branch: chore/system-review-agent-meta-update (dirty – 28 modified files, multiple untracked)
Last commit: 368f4a0 Initial test
Audit date: 2026-08-03
Scope: Read-only — no modifications, commits, or file writes performed.
Code metrics: 759 lines production Python / 225 lines test Python / 12 config files
Architecture delta: AGENTS.md spec vs. actual implementation shows ~70% of specified modules not yet built (bridges, sensor_type modules, binary_sensor, switch, brand assets, GitHub Actions).
1. ARCHITECTURE ANALYSIS
1.1 Architecture Specification vs. Implementation Gap
The AGENTS.md describes a rich multi-layer architecture: Bridge Pattern (serial/MQTT/HTTP), Strategy Pattern (per-type sensor modules: temperature.py, humidity.py, pressure.py, power.py, water.py), Repository Pattern (DeviceRegistry), binary_sensor.py, switch.py, and a brand/ icon directory. The actual implementation is substantially simpler, consisting of:
Spec Module	Implemented?	Notes
bridge/serial_bridge.py	❌	Not present
bridge/mqtt_bridge.py	❌	Not present
bridge/http_bridge.py	❌	Not present
sensor_types/temperature.py	❌	Not present
sensor_types/humidity.py	❌	Not present
sensor_types/pressure.py	❌	Not present
sensor_types/power.py	❌	Logic inlined in filters.py
sensor_types/water.py	❌	Logic inlined in filters.py
device.py	❌	Not present
binary_sensor.py	❌	Not present
switch.py	❌	Not present
brand/icon.png	❌	Not present
brand/logo.png	❌	Not present
coordinator.py	✅	Central DataUpdateCoordinator
sensor.py	✅	AbstractorSensor entity
config_flow.py	✅	Config + Options flows
filters.py	✅	Filter pipeline (spike, invert, aggregation)
snapshot.py	✅	Export/import snapshot
diagnostics.py	✅	HA diagnostics
repository/device_registry.py	✅ (stub)	Created, never populated, never read
Assessment: The delta between AGENTS.md and code is ~70% unimplemented specification. The current MVP implements the core pipeline (config → coordinator → filter → sensor) correctly for power/energy/water, but the bridge layer and sensor-type extensibility are not yet built.
1.2 Architecture Quality of the Implemented MVP
The implemented pipeline is well-structured for its scope:
- Single DataUpdateCoordinator per HA instance (prevents N parallel polls)
- AbstractorFilterPipeline per config entry with configurable spike/invert/fallback
- Clean separation of config flow (UI), coordinator (data), pipeline (processing), and sensor (entity)
- Snapshot export/import using versioned format with voluptuous validation
- Proper HA integration patterns (coordinatorEntity, Store, config_entry lifecycle)
2. FINDINGS BY SEVERITY
HIGH SEVERITY
H-01: Unique ID Format Inconsistency Between Config Flow and Sensor Platform
- File: config_flow.py:50-51 vs sensor.py:65-70
- Evidence: Config flow generates unique_id as f"abstractor_{device_type}_{'_'.join(sorted(sources))}" (device_type comes first). Sensor platform uses two formats: single-source → f"abstractor_{source_entity_ids[0]}_{device_type}", multi-source → f"abstractor_{device_type}_{'_'.join(sorted(source_entity_ids))}". For single-source entries, these produce different IDs — e.g., config flow yields abstractor_power_sensor.test_power while sensor yields abstractor_sensor.test_power_power.
- Impact: Config entry unique_id and entity unique_id do not match for single-source entries. This can cause HA entity registry mismatch, duplicate entities, and breaks the HA uniqueness contract.
- Remediation: Unify on a single ID format. Use config flow's format everywhere: f"abstractor_{device_type}_{'_'.join(sorted(source_entity_ids))}".
H-02: No GitHub Actions CI/CD Pipeline
- File: .github/workflows/ — directory does not exist
- Evidence: AGENTS.md references validate.yaml with HACS Action + Hassfest validation on push/PR. README.md describes comprehensive Docker test infrastructure. Yet the .github/ directory is completely absent.
- Impact: No automated validation on push/PR. HACS compatibility is untested in CI. No regression gate for PRs.
- Remediation: Create .github/workflows/validate.yaml with:
on: [push, pull_request]
jobs:
  hacs: uses: hacs/action@main
  hassfest: runs-on: ubuntu-latest, steps: [uses: home-assistant/actions/hassfest@master]
  tests: runs-on: ubuntu-latest, steps: [build Dockerfile.test, run pytest, run ruff+mypy]
H-03: No Unit Tests for Sensor Platform
- File: sensor.py (95 lines, zero test coverage)
- Evidence: No test_sensor.py exists. The tests/ directory has 7 test files but none cover AbstractorSensor, async_setup_entry, device class/state class mapping, or unique_id generation.
- Impact: Sensor entity creation, type mapping (power→W/MEASUREMENT, energy→kWh/TOTAL_INCREASING, water→L/TOTAL_INCREASING), and CoordinatorEntity integration are untested. A regression in sensor type mapping would be silent.
- Remediation: Add tests/test_sensor.py covering: entity creation for each device type, native_value from coordinator data, device_info structure, unique_id format for single/multi-source.
H-04: No Unit Tests for Config Flow Validation Paths
- File: tests/test_config_flow.py (41 lines, 1 test)
- Evidence: Only test_form tests the happy path (single source, power type). Missing tests: multi-source entry creation, source_required error path, duplicate entry abortion (_abort_if_unique_id_configured), options flow (AbstractorOptionsFlowHandler), options flow with defaults.
- Impact: AGENTS.md mandates "Config flow needs 100% test coverage" — current coverage is estimated <40%.
- Remediation: Add tests for: multi-source entry, empty source validation error, duplicate detection, options flow form rendering, options flow save, device_type selection.
H-05: No Unit Tests for __init__.py Entry Point
- File: __init__.py (130 lines, zero test coverage)
- Evidence: No test covers async_setup_entry, async_unload_entry, async_migrate_entry, service registration, snapshot persistence lifecycle, coordinator lifecycle (add/remove entries, first refresh vs. subsequent).
- Impact: The integration entry point — the most critical lifecycle code — is untested. Unload, reload, multi-entry, and service registration paths have no regression protection.
- Remediation: Add tests/test_init.py covering: single entry setup, multi-entry setup, entry unload, last-entry unload (coordinator shutdown), service registration idempotency, async_migrate_entry, snapshot save on setup.
MEDIUM SEVERITY
M-01: Config Flow Unique ID Mismatch Pattern (duplicated from H-01)
- File: config_flow.py:50-53
- Evidence: Unique ID uses user_input[CONF_DEVICE_TYPE] before sources — but sources is derived from user_input with potential empty-string filtering. The resulting ID f"abstractor_{device_type}_{'_'.join(sorted(sources))}" includes filtered sources, but the config data stored (user_input) may contain stale CONF_SOURCE_ENTITY_IDS/CONF_SOURCE_ENTITY_ID keys that were popped.
- Impact: Edge case: if both CONF_SOURCE_ENTITY_ID and CONF_SOURCE_ENTITY_IDS are submitted, the pop at line 49 removes the multi key but the single key remains in data — the coordinator reads the deprecated field.
- Remediation: After building sources, always normalize user_input to contain only CONF_SOURCE_ENTITY_IDS and remove CONF_SOURCE_ENTITY_ID.
M-02: DeviceRegistry Instantiated but Never Populated or Used
- File: __init__.py:44-45, repository/device_registry.py
- Evidence: DeviceRegistry() is created in async_setup_entry and stored in domain_data["registry"], but register_device is never called anywhere in the codebase, and get_device has no callers.
- Impact: Dead code — the registry exists in memory but adds no value. The AGENTS.md spec for device deduplication and lookup is not implemented.
- Remediation: Either implement device registration in async_setup_entry (register abstract devices via device_info) or remove the unused registry. If keeping, wire register_device into the sensor platform or config flow.
M-03: InfluxExporter is a Pure Stub — No Actual I/O
- File: influx_exporter.py
- Evidence: async_push only logs "Pushing X=Y to InfluxDB" — no HTTP client, no write call. The constructor stores credentials in plain Python attributes (self.host, self.token). Coordinator instantiates it as self.influx_exporter = None (line 30 of coordinator.py) — it's never set to an actual instance.
- Impact: The export path exists in code but does nothing. Users who configure it would get only log messages with no data persistence.
- Remediation: Either implement the InfluxDB HTTP client (using HA's aiohttp session) or remove the module and note its status clearly in README (which it already does as a known limitation).
M-04: SENSOR_TYPES List is Mutable and Unfinalized
- File: const.py:23-27
- Evidence: SENSOR_TYPES = [TYPE_POWER, TYPE_ENERGY, TYPE_WATER] is a plain mutable list without Final annotation, unlike every other constant in the file.
- Impact: Accidentally appending to or mutating SENSOR_TYPES would silently add invalid options to the config flow dropdowns. Type checkers cannot detect mutations.
- Remediation: Change to SENSOR_TYPES: Final[list[str]] = [...] or use tuple.
M-05: Missing pyproject.toml / Project-Level Tool Configuration
- File: Repository root
- Evidence: No pyproject.toml, setup.cfg, mypy.ini, or ruff.toml exists. Ruff and mypy are run in Docker with bare CLI flags (mypy --cache-dir=/tmp/.mypy_cache --ignore-missing-imports). Pytest configuration (asyncio_mode=auto) is set via CLI flag rather than config file.
- Impact: Non-Docker development workflows (direct pytest, IDE integration) lack consistent configuration. Developers running ruff check or mypy locally get different results than CI.
- Remediation: Add pyproject.toml with [tool.ruff], [tool.mypy], [tool.pytest.ini_options] sections. Use asyncio_mode = "auto" in pytest config.
M-06: coordinator.add_entry Silently Defaults to "power"
- File: coordinator.py:37
- Evidence: config["device_type"] = config.get("device_type", "power") — if device_type is missing from merged config, it silently becomes "power" with no warning.
- Impact: Config corruption or migration errors that strip device_type would silently produce power sensors for energy/water entries, corrupting utility meter data.
- Remediation: Log a warning when defaulting: _LOGGER.warning("device_type missing for entry %s, defaulting to power", entry.entry_id).
M-07: Debug Notification Coupling to Specific HA Entity/Service Names
- File: coordinator.py:80-90
- Evidence: Hardcoded references to input_boolean.automation_debugger and notify.adminnotificationgroup. These entity/service IDs are specific to the author's HA instance.
- Impact: The debug notification feature silently fails (no notification, no error) in any HA instance without these exact IDs. No configuration option exists to customize the debug channel.
- Remediation: Make the debug entity and notification service configurable via config entry options, or document the hardcoded IDs prominently and provide a fallback log message.
M-08: Untracked but Functional Infrastructure Files
- File: Dockerfile.test, docker-compose.test.yml, requirements.txt, requirements_test.txt, scripts/
- Evidence: rtk git status shows all as ?? (untracked). The entrypoint.sh references ruff check custom_components tests but ruff configuration is not project-standardized.
- Impact: New contributors who clone the repo get no Docker test infrastructure, no dependency lists, and no scripts. CI cannot use these files until committed.
- Remediation: Commit all test infrastructure files. Add a .dockerignore if needed for the build context.
M-09: No HACS Brand Assets
- File: custom_components/abstractor/brand/ — directory does not exist
- Evidence: HACS requires icon.png (256×256) and recommends logo.png in custom_components/<domain>/brand/. The hacs.json is present but brand assets are missing.
- Impact: HACS UI shows a default/generic icon. Not a blocker for functionality but poor UX in HACS dashboard.
- Remediation: Add brand/icon.png and brand/logo.png to custom_components/abstractor/.
LOW SEVERITY
L-01: Google-Style Docstrings Missing on Many Public Functions
- Files: coordinator.py:20, config_flow.py:31, sensor.py:27, __init__.py:31
- Evidence: AGENTS.md mandates "Google-style docstrings for all public classes/methods." Many public methods have brief one-liners ("""Set up Abstractor from a config entry.""") but lack Args/Returns/Raises documentation.
- Impact: Reduced maintainability and IDE support. Minor — code is short and readable.
- Remediation: Expand docstrings to Google-style format with Args:, Returns:, Raises: sections.
L-02: futures Import Unnecessary
- File: __init__.py:2
- Evidence: from __future__ import annotations is present but the file uses no forward-reference type annotations (all annotations are simple types like bool, None).
- Impact: None. Cosmetic.
- Remediation: Remove if unused, or keep if anticipating future annotations — benign.
L-03: snapshot.py Validation Schema Lax on Entry Fields
- File: snapshot.py:50-54
- Evidence: Validation checks that data is a dict and options is a dict (if present), but doesn't validate that entry_id, title, unique_id, or version exist in the entry dict. These are informational per the docstring.
- Impact: A well-formed but semantically garbage snapshot passes validation. Export-import round-trip produces data but may be unusable for restore.
- Remediation: Document this as a design decision (validation is intentionally minimal for portability) or add optional field validation.
L-04: Spike Filter State Not Persisted Across Restarts
- File: filters.py:14
- Evidence: self._last_valid_state is set during process()/process_sources() but is never loaded from HA storage or initial state. After HA restart, the spike filter starts with None, so the first value always passes through.
- Impact: On restart, a counter-drop spike can pass through exactly once before the guard re-engages. This is a one-time vulnerability per restart cycle.
- Remediation: Load _last_valid_state from the snapshot's values dict on coordinator initialization.
L-05: async_migrate_entry Returns True for All Versions ≤ 1
- File: __init__.py:96
- Evidence: return config_entry.version <= 1 — a migration that always succeeds without any actual migration logic.
- Impact: If config entry version 1 ever needs schema migration, this function does nothing. Currently version is 1, so it correctly returns True (no migration needed). But future version bumps (e.g., version 2) have no migration path.
- Remediation: Add explicit version-branching logic: if config_entry.version == 1: ... return True. When version 2 is introduced, add the corresponding branch.
L-06: pip install -e . Build Command References Non-Existent script.hassfest
- File: AGENTS.md build instructions
- Evidence: python3 -m script.hassfest --integration-path custom_components/abstractor — script.hassfest is part of the HA core repo, not available as a standalone package. This command only works inside a full HA development environment.
- Impact: The documented build command fails for contributors who clone the repo without setting up the full HA dev environment.
- Remediation: Update documentation to note that this command requires HA core checkout, or replace with HACS Action in CI.
L-07: LASTENHEFT_ABSTRAKTIONS_INTEGRATION.md German-Language Spec with Mixed Audience
- File: LASTENHEFT_ABSTRAKTIONS_INTEGRATION.md (193 lines)
- Evidence: The requirements document is entirely in German, while all code, commits, documentation, and AGENTS.md rules specify English. The docs/REQUIREMENTS.md is also in German.
- Impact: International contributors or tooling that parses requirement documents face a language barrier. AGENTS.md rule: "Externe Doku: English".
- Remediation: Translate LASTENHEFT_ABSTRAKTIONS_INTEGRATION.md and docs/REQUIREMENTS.md to English, or explicitly exempt these from the English-language rule.
L-08: info.md References Non-Existent Documentation URLs
- File: info.md:42-44
- Evidence: Links to docs/REQUIREMENTS.md and docs/REQUIREMENTS_COVERAGE.md as GitHub URLs. These files exist. However, the "Full documentation" link points to the repo root, which is the README — not a dedicated docs site.
- Impact: Minor. The documentation links are valid.
- Remediation: None required — just noting that info.md is the HACS integration description card.
L-09: test_coordinator.py Uses object.__new__ Bypass
- File: tests/test_coordinator.py:16
- Evidence: coordinator = object.__new__(AbstractorDataUpdateCoordinator) bypasses __init__, manually setting coordinator.hass. This is fragile — if __init__ adds required initialization, this test silently breaks.
- Impact: Test isolation technique is valid but fragile. A future refactor adding __init__ logic would cause the test to pass vacuously (missing init) while the real code could fail.
- Remediation: Use AsyncMock for hass and call the real constructor with proper arguments, or use pytest-homeassistant-custom-component fixtures.
L-10: Working Tree Dirty with 28 Modified Files
- File: Working tree
- Evidence: Modified files include 3 integration Python files fixing FlowResult → ConfigFlowResult deprecation, README rewrite, strings.json i18n additions, tests/test_services.py fixture refactor, and heavy graphify-out/ churn. 5 deleted .bak files, 1 added submodule, multiple untracked test infrastructure files.
- Impact: The current working tree is in an intermediate state. The FlowResult → ConfigFlowResult fix is a legitimate HA Core API deprecation and should be committed. The test infrastructure files should also be committed.
- Remediation: Commit the 3 integration fixes, test fixture fix, i18n additions, and test infrastructure as one or more atomic commits. Clean up deleted .bak files.
INFORMATIONAL / OBSERVATIONAL
I-01: Requirements Traceability
The docs/REQUIREMENTS_COVERAGE.md provides a comprehensive FA/NFA audit against LASTENHEFT_ABSTRAKTIONS_INTEGRATION.md. Coverage is strong for the MVP scope:
- 10 of 13 functional requirements implemented (FA-01 through FA-13)
- 2 explicitly marked "unsupported by API" (FA-02 YAML import, FA-09 unique_id migration)
- 1 delegated to HA (FA-08 Utility Meter)
- All 8 non-functional requirements implemented or delegated
Missing from implementation but specified: REQ-COMP-004 (conditional cross-entity fallback), REQ-UTIL-001 (integrated utility meter), REQ-SENS-003 (Riemann integration for energy from power).
I-02: Test Coverage Estimate
Based on manual analysis of test files vs. production code:
Module	Lines	Tests	Coverage Estimate
const.py	27	— (covered by imports)	100% (trivial)
filters.py	85	7 test functions	~85%
snapshot.py	55	2 test functions	~70%
diagnostics.py	27	1 test function	~60%
coordinator.py	90	1 test function (notifications only)	~25%
config_flow.py	133	1 test function (happy path)	~30%
__init__.py	130	2 test functions (services only)	~25%
sensor.py	95	0 tests	0%
influx_exporter.py	17	0 tests	0%
device_registry.py	22	0 tests	0%
Overall estimated coverage: ~40-45% (far below the AGENTS.md goal of 100% config-flow coverage and general testability mandate).
I-03: Dependency Analysis
- Runtime: Zero PyPI dependencies (manifest.json "requirements": []). Depends only on HA core (homeassistant>=2025.1) and voluptuous (bundled with HA).
- Test: pytest-homeassistant-custom-component (provides hass fixture), pytest-asyncio, pytest-cov.
- Static analysis: ruff, mypy (in Dockerfile.test).
- License: MIT — compatible with HA's Apache 2.0 ecosystem.
- No external service dependencies in the current implementation (InfluxDB stub only).
I-04: Security Assessment
- No secrets in code: Verified — no hardcoded tokens, passwords, or API keys. InfluxDB credentials are constructor parameters only (unused stub).
- No network I/O: The integration does not make outbound HTTP calls, open ports, or listen on sockets.
- Storage: All data stored in HA's .storage/ directory via homeassistant.helpers.storage.Store — follows HA security model.
- Service exposure: export_data/import_data services are HA-internal only (no external API exposure).
- Input validation: Import service validates payload via voluptuous schema before storage.
- Risk: LOW. The integration is passive (reads HA states, writes HA entities) with no external attack surface.
3. OVERALL ASSESSMENT
Maturity: EARLY MVP (0.6/1.0)
Dimension	Rating	Notes
Core pipeline	✅ Solid	Coordinator + filter + sensor flow works correctly
Config flow	✅ Solid	UI-based setup with unique IDs and options
Error handling	✅ Good	Non-finite rejection, unavailable guards, fail-soft/fail-closed
Data integrity	✅ Good	Spike filter, versioned snapshots, monotonic guard
Documentation	✅ Good	README, info.md, requirements coverage, inline comments
Architecture	⚠️ Partial	~30% of spec implemented; bridges, sensor types, binary_sensor missing
Testing	⚠️ Minimal	~40% coverage, 0% on sensor and init modules
CI/CD	❌ None	No GitHub Actions, no automated validation
Extensibility	⚠️ Partial	Pipeline pattern is good; adding new types requires code changes
Production readiness	❌ Not ready	No CI, low test coverage, dirty working tree
Risk Assessment: LOW-MEDIUM
The integration poses low operational risk (passive, no network I/O, no secrets). The primary risks are:
1. Regression risk from low test coverage on critical lifecycle code (H-03, H-04, H-05)
2. Unique ID drift between config flow and sensor platform (H-01)
3. Silent data corruption from missing device_type defaulting to "power" (M-06)
4. Blocked CI from missing GitHub Actions (H-02)
Notable Test Gaps (Ranked by Criticality)
1. sensor.py — 0% coverage — Device class, unit, state class mapping for all 3 types, native_value from coordinator, unique_id generation, device_info structure
2. __init__.py — 25% coverage — Entry setup/unload lifecycle, multi-entry, coordinator creation/shutdown, service registration idempotency, snapshot persistence
3. config_flow.py — 30% coverage — Multi-source entry, empty source error, duplicate abortion, options flow form/save, device_type dropdown
4. coordinator.py — 25% coverage — _async_update_data polling, source aggregation, missing device_type defaulting behavior, pipeline creation
5. filters.py — 85% coverage — Aggregate spike filter (only single-value tested), process_sources with spike_filter on multi-source, edge cases: empty source list, all None, mixed valid/invalid
4. REMEDIATION PRIORITIES
Immediate (should be fixed before next release)
Priority	Finding	Effort
P0	H-01: Unify unique_id format between config_flow and sensor	15 min
P0	Commit dirty working tree (FlowResult fix, i18n, test fixtures)	10 min
P1	H-05: Add test_init.py for entry lifecycle	2 hr
P1	H-03: Add test_sensor.py for entity creation	1 hr
P1	H-04: Expand test_config_flow.py to full coverage	1.5 hr
P1	H-02: Create GitHub Actions CI pipeline	1 hr
Short-term (next sprint)
Priority	Finding	Effort
P2	M-01: Normalize config data to single source key	20 min
P2	M-06: Warn on device_type default	5 min
P2	M-09: Add brand icon assets	30 min
P2	M-05: Add pyproject.toml tool config	30 min
P2	M-08: Commit test infrastructure files	10 min
Medium-term (roadmap)
Priority	Finding	Effort
P3	M-02: Wire DeviceRegistry to entity creation or remove	2 hr
P3	M-03: Implement or remove InfluxExporter stub	4 hr
P3	M-07: Make debug notification configurable	1 hr
P3	L-04: Persist spike filter state across restarts	1 hr
P3	L-07: Translate requirements docs to English	2 hr
ARTIFACTS
No files written (read-only audit). All findings are self-contained in this report with file paths, line references, evidence, impact, and remediation steps.
PLAN_STATUS: done
COMPLETED: Full repository audit (architecture, implementation, tests, config, CI/deployment, security, reliability, maintainability, documentation)
PENDING: None (read-only — no modifications to make)
SUMMARY: 28 findings across 5 high, 9 medium, 10 low, 4 informational. Primary concerns: no CI/CD pipeline, ~40% test coverage with 0% on sensor/init modules, unique_id format mismatch between config flow and sensor platform, and a ~70% gap between AGENTS.md architecture spec and implemented code. Core pipeline is solid for MVP scope.