# System Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every Critical/High finding from the 2026-09-04 system audit — a broken CI pipeline with zero passing test evidence, a REQ-CORE-001 identity regression (GH#19), a diagnostics regression, an unflagged security-profile change, and drifted/self-contradicting documentation — then work down through Medium findings, leaving a P2 backlog of smaller hardening items for later.

**Architecture:** No architectural rewrite. Every task is a targeted, independently testable fix to the existing singleton-root/subentry design (`config_flow.py`, `coordinator.py`, `sensor.py`, `diagnostics.py`, `filters.py`), its CI/dependency pins, or its documentation. Tasks are ordered so CI is fixed first (Task 1) — every later code task's tests need a working pytest run to actually mean something — then correctness/security code fixes, then docs, then repo/agent-meta hygiene, then optional hardening.

**Tech Stack:** Python 3.13 (bumped from 3.12 in CI, Task 1), Home Assistant ≥2025.3.0, pytest + pytest-homeassistant-custom-component, GitHub Actions.

**Spec:** `docs/SYSTEM_AUDIT_2026-09-04.md` (this plan implements its §3 findings index; finding IDs like `ARCH-1`, `CI-1`, `SEC-1`, `DOC-1`, `INFRA-1` below refer to that document).

## Global Constraints

- `homeassistant` floor is `2025.3.0` (per `hacs.json` and `Dockerfile.test`) — never reintroduce a pin below that.
- Every code task must leave `pytest tests/ -v --cov=custom_components/abstractor --cov-report=term-missing` green in CI (verify via the Task 1 fix; native pytest cannot run on Windows — `fcntl` — so local verification of exact command output isn't possible on this dev machine; rely on the CI run for final confirmation, and on direct code reading for correctness in the meantime).
- No `from x import *`; PEP 604 `str | None` union syntax; `_LOGGER` calls use `%s`-style formatting, never f-strings; Google-style docstrings; type hints everywhere (per CLAUDE.md Code-Konventionen).
- Never derive an Abstract sensor's `unique_id` from anything that can change on a legitimate reconfigure (the exact class of bug this plan fixes in Task 2 — do not reintroduce it elsewhere).
- All new/changed tests follow the existing style in `tests/*.py`: plain `Mock()`/`AsyncMock()` for coordinator/hass objects (not full HA fixtures) for unit-level sensor/coordinator/diagnostics/filter tests; `MockConfigEntry` + `hass.config_entries.subentries.async_init/async_configure` for config-flow integration tests (see `tests/test_config_flow.py`).
- Conventional Commits, English commit messages, max 72 chars in the subject line (per `.claude/rules/commit-conventions.md`).

---

## Task 1: Fix the CI pipeline so the test suite can run at all (CI-1, CI-2, CI-3, CI-4, DOC-8, SEC-3)

**Files:**
- Modify: `requirements.txt`
- Modify: `.github/workflows/validate.yaml:55-57`

**Interfaces:** None (dependency/CI config only, no code interfaces).

This is Task 1 because every other task's tests are currently unverifiable in CI — nothing has passed since 2026-08-16. Both changes below are required together; either alone leaves CI broken (see audit §3.1 root-cause detail).

- [ ] **Step 1: Tighten the `homeassistant` pin to match the code's real floor, with a ceiling to survive one more HA Python-floor bump**

Edit `requirements.txt`:
```diff
 # Abstractor — production dependencies (installed by Home Assistant core, listed for dev reference)
 # No PyPI dependencies required — manifest.json requirements: []
-homeassistant>=2025.1
+homeassistant>=2025.3.0,<2026.6.0
 voluptuous>=0.15.2
```
(`<2026.6.0` is a deliberate stopgap: that's the next version where HA's `requires_python` floor jumps again, to `>=3.14.2`. Track that as a separate future issue — see Task 17.)

- [ ] **Step 2: Bump the Pytest job's Python version so a compatible HA version can actually be installed**

Edit `.github/workflows/validate.yaml`:
```diff
   pytest:
     name: Pytest suite
     runs-on: ubuntu-latest
     steps:
       - uses: actions/checkout@v4
       - uses: actions/setup-python@v5
         with:
-          python-version: "3.12"
+          python-version: "3.13"
       - name: Install dependencies
         run: |
           python -m pip install --upgrade pip
           pip install -r requirements.txt -r requirements_test.txt
       - name: Run pytest
         run: pytest tests/ -v --cov=custom_components/abstractor --cov-report=term-missing
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt .github/workflows/validate.yaml
git commit -m "fix(ci): unblock pytest suite — HA floor was one minor too low for ConfigSubentry"
```

- [ ] **Step 4: Push and verify in CI**

```bash
git push
gh run watch $(gh run list --branch <this-branch> --workflow validate.yaml --limit 1 --json databaseId --jq '.[0].databaseId')
```
Expected: the `pytest` job now installs a real `homeassistant` version (2025.3.x–2026.5.x range) and the 12 test files collect and run — some may now show real (not import-error) failures if any of Tasks 2–8 below haven't landed yet; that's expected progress, not a blocker to merging this task alone.

---

## Task 2: Auto-generate a stable identity for every new Abstract sensor subentry (ARCH-1 / GH#19)

**Files:**
- Modify: `custom_components/abstractor/config_flow.py:229-253` (`AbstractorSensorSubentryFlowHandler.async_step_user`)
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `CONF_LEGACY_UNIQUE_ID` (existing constant, `const.py:17`), `self._normalize(user_input, sources)` (existing method, unchanged signature).
- Produces: every newly created subentry's `data[CONF_LEGACY_UNIQUE_ID]` is always set (never empty) after creation — `sensor.py:93-95` already treats a set `legacy_unique_id` as the winning identity source, so no change is needed there.

The mechanism that keeps identity stable already exists and works (`sensor.py:93-95`, `config_flow.py::_normalize` lines 365-385 carry a pinned id forward unconditionally). The bug is that nothing ever *sets* it for a brand-new sensor — it's just one more optional field a user can skip. This task auto-fills it at creation time only; reconfigure already refuses to change or clear an existing one.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config_flow.py` (near `test_subentry_create_form`):

```python
import re


async def test_subentry_create_auto_generates_stable_unique_id(hass: HomeAssistant) -> None:
    """A newly created subentry gets a stable identity without the user
    typing anything into the optional 'legacy unique id' field (GH#19)."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.test_power",
        },
    )
    await hass.async_block_till_done()

    subentry = next(iter(root_entry.subentries.values()))
    stable_id = subentry.data[CONF_LEGACY_UNIQUE_ID]
    assert re.match(r"^abstractor_[0-9a-f]{32}$", stable_id)


async def test_subentry_reconfigure_keeps_auto_generated_id_after_source_swap(
    hass: HomeAssistant,
) -> None:
    """The whole point (GH#19): swapping a sensor's source hardware via
    reconfigure must NOT change its unique_id, because a stable id was
    already auto-generated at creation time."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    create_result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )
    await hass.config_entries.subentries.async_configure(
        create_result["flow_id"],
        {CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.old_plug"},
    )
    await hass.async_block_till_done()
    subentry_id, subentry = next(iter(root_entry.subentries.items()))
    original_id = subentry.data[CONF_LEGACY_UNIQUE_ID]

    reconfigure_result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": subentry_id,
        },
    )
    await hass.config_entries.subentries.async_configure(
        reconfigure_result["flow_id"],
        {CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.new_plug"},
    )
    await hass.async_block_till_done()

    updated_subentry = root_entry.subentries[subentry_id]
    assert updated_subentry.data[CONF_SOURCE_ENTITY_ID] == "sensor.new_plug"
    assert updated_subentry.data[CONF_LEGACY_UNIQUE_ID] == original_id
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (in the Docker test container — see `Dockerfile.test`/`docker-compose.test.yml`, since native pytest doesn't run on Windows): `pytest tests/test_config_flow.py -k "auto_generates_stable or keeps_auto_generated" -v`
Expected: FAIL — the first asserts a regex match against a currently-absent key (`KeyError` or the field being empty); the second currently fails because `sensor.py`'s pre-fix derivation would change on source swap if no legacy id was ever set (demonstrates the actual bug before the fix).

- [ ] **Step 3: Write the minimal implementation**

Edit `custom_components/abstractor/config_flow.py`. Add `import uuid` near the top (alongside the existing imports), then change `async_step_user`:

```python
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Create a new Abstract sensor subentry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            sources = user_input.get(CONF_SOURCE_ENTITY_IDS) or [
                user_input.get(CONF_SOURCE_ENTITY_ID)
            ]
            sources = [source for source in sources if source]
            if not sources:
                errors["base"] = "source_required"
            else:
                if not user_input.get(CONF_LEGACY_UNIQUE_ID):
                    # No stable identity was typed in manually — generate one
                    # now, at creation time only. This is what closes GH#19:
                    # without it, a brand-new sensor's unique_id is derived
                    # from its source entity ids (see sensor.py) and changes
                    # the moment the user reconfigures it onto different
                    # hardware, orphaning the entity and its recorder
                    # history. _normalize()/sensor.py already treat a set
                    # legacy_unique_id as permanent and winning over any
                    # later source change — this just makes sure one always
                    # exists from the start.
                    user_input = {
                        **user_input,
                        CONF_LEGACY_UNIQUE_ID: f"abstractor_{uuid.uuid4().hex}",
                    }
                data = self._normalize(user_input, sources)
                device_type = data[CONF_DEVICE_TYPE]
                return self.async_create_entry(
                    title=f"Abstract {device_type}", data=data
                )

        return self.async_show_form(
            step_id="user", data_schema=self._schema(), errors=errors
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_config_flow.py -k "auto_generates_stable or keeps_auto_generated" -v`
Expected: PASS.

- [ ] **Step 5: Run the full config-flow test file to check for regressions**

Run: `pytest tests/test_config_flow.py -v`
Expected: all 27 tests (25 existing + 2 new) PASS. In particular, confirm `test_subentry_create_form` still passes unmodified — it doesn't assert on `CONF_LEGACY_UNIQUE_ID` at all, so the new auto-fill shouldn't break it.

- [ ] **Step 6: Update the field's user-facing label so it no longer only reads as a migration aid**

Edit `custom_components/abstractor/strings.json` and `custom_components/abstractor/translations/en.json` — find the `legacy_unique_id` field description (near "Legacy unique ID (optional)") and change its description to reflect that it is now optional purely as a manual-override escape hatch, not the only way to get a stable id, e.g.:
```
"Manually reuse a specific unique_id (e.g. from a migrated YAML template sensor). Leave blank to have one generated automatically — either way, this sensor's identity will never change again, even if you later swap its source hardware."
```
Keep the exact same JSON key name (`legacy_unique_id`) in both files — do not rename the field itself, only its `name`/`description` text, so the sync check between `strings.json` and `translations/en.json` (the CI `translations-sync` job) still passes.

- [ ] **Step 7: Commit**

```bash
git add custom_components/abstractor/config_flow.py tests/test_config_flow.py custom_components/abstractor/strings.json custom_components/abstractor/translations/en.json
git commit -m "fix(config-flow): auto-generate stable sensor identity at creation (GH#19)"
```

---

## Task 3: Fix `diagnostics.py` pipeline_config keying (ARCH-2)

**Files:**
- Modify: `custom_components/abstractor/diagnostics.py:28-32`
- Modify: `tests/test_diagnostics.py` (fix an existing test that currently can't catch this bug, plus add a new one that does)

**Interfaces:**
- Consumes: `coordinator.pipelines: dict[str, AbstractorFilterPipeline]` (existing, keyed by `subentry_id` — see `coordinator.py:82-87`), `entry.subentries: dict[str, ConfigSubentry]` (HA-provided).
- Produces: `pipeline_config: dict[str, dict]` keyed by `subentry_id`, containing every subentry belonging to `entry` (previously: always empty except in one coincidental case).

- [ ] **Step 1: Write the failing test**

The existing `test_config_entry_diagnostics_uses_shared_coordinator` (`tests/test_diagnostics.py:9-20`) passes today only because it never gives `entry` any `subentries` or `coordinator.pipelines` any non-empty content — it can't distinguish correct from buggy behavior. Fix it and add a new test:

```python
async def test_config_entry_diagnostics_uses_shared_coordinator(hass) -> None:
    """Diagnostics should read the coordinator, not entry data."""
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.subentries = {}
    entry.as_dict.return_value = {"entry_id": entry.entry_id}
    coordinator = Mock(data={entry.entry_id: 12.0}, pipelines={})
    hass.data[DOMAIN] = {"coordinator": coordinator, entry.entry_id: entry.data}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["coordinator_data"] == {entry.entry_id: 12.0}
    assert result["pipeline_config"] == {}


async def test_pipeline_config_is_keyed_by_subentry_id_not_entry_id() -> None:
    """[GH regression] pipeline_config must include every subentry belonging
    to the entry, keyed by subentry_id — not filtered by entry.entry_id,
    which never matches a subentry_id except in one legacy-promotion edge
    case. Reproduces the bug: coordinator.pipelines is keyed by subentry_id
    ("subentry-a"), which is NOT entry.entry_id ("entry-1")."""
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.subentries = {"subentry-a": Mock(), "subentry-b": Mock()}
    entry.as_dict.return_value = {"entry_id": "entry-1"}
    pipeline_a = Mock(config={"device_type": "power"})
    pipeline_b = Mock(config={"device_type": "energy"})
    coordinator = Mock(
        data={}, pipelines={"subentry-a": pipeline_a, "subentry-b": pipeline_b}
    )
    hass = Mock()
    hass.data = {DOMAIN: {"coordinator": coordinator}}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["pipeline_config"] == {
        "subentry-a": {"device_type": "power"},
        "subentry-b": {"device_type": "energy"},
    }
```
(Note: `hass` is a plain `Mock()` here, not the `hass` pytest fixture, matching the style already used elsewhere for pure-unit tests in this file's neighbors like `test_sensor.py`.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_diagnostics.py -k pipeline_config_is_keyed -v`
Expected: FAIL — `result["pipeline_config"]` is `{}` instead of the two-entry dict, because today's filter `if key == entry.entry_id` never matches `"subentry-a"`/`"subentry-b"` against `"entry-1"`.

- [ ] **Step 3: Write the minimal implementation**

Edit `custom_components/abstractor/diagnostics.py`:

```python
    return {
        "entry": entry_data,
        "coordinator_data": coordinator.data or {},
        "pipeline_config": {
            subentry_id: pipeline.config
            for subentry_id, pipeline in coordinator.pipelines.items()
            if subentry_id in entry.subentries
        },
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_diagnostics.py -v`
Expected: all 4 tests (3 existing, now including the fixed one, + 1 new) PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/abstractor/diagnostics.py tests/test_diagnostics.py
git commit -m "fix(diagnostics): key pipeline_config by subentry_id, not entry_id"
```

---

## Task 4: Seed the spike-filter guard from the persisted snapshot (ARCH-3, ARCH-4 / old F-09)

**Files:**
- Modify: `custom_components/abstractor/filters.py:12-15`
- Modify: `custom_components/abstractor/coordinator.py:82-87`
- Modify: `custom_components/abstractor/__init__.py:420-421`
- Test: `tests/test_filters.py`, `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `domain_data["stored_snapshot"]["values"]: dict[str, float | None]` (already loaded at `__init__.py:388-390`, already populated by `_save_snapshot`/`build_snapshot` — see `snapshot.py:13-30` — but never previously read back).
- Produces: `AbstractorFilterPipeline.__init__(config, initial_last_valid_state=None)` — new optional constructor parameter; `AbstractorDataUpdateCoordinator.add_subentry(subentry_id, subentry_data, initial_last_valid_state=None)` — new optional parameter, passed straight through to the pipeline it constructs.

**Why this fixes both ARCH-3 and ARCH-4 in one change:** tracing `async_unload_entry` shows that editing *any single* subentry causes HA to reload the whole singleton entry, which removes every subentry from the coordinator, finds `subentry_data` now empty, and fully shuts the coordinator down (`__init__.py:489-508`) — so `async_setup_entry` always rebuilds a brand-new coordinator and brand-new `AbstractorFilterPipeline` objects from scratch, for every sensor, on every single edit, not just the one being edited. In-memory state cannot survive this by construction — only genuine persistence-and-reload can. `_save_snapshot` already runs synchronously right before that shutdown (`__init__.py:502`) and already captures `coordinator.data` (the last-known accepted aggregate per subentry) into the Store. This task is simply: read that already-persisted value back in when a pipeline is (re)constructed, whether the rebuild was triggered by an unrelated sensor's edit (ARCH-3) or a real HA restart (ARCH-4/old F-09) — both go through the exact same code path.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_filters.py` (matching the existing plain-`AbstractorFilterPipeline(config)` construction style already used throughout that file):

```python
def test_pipeline_seeds_last_valid_state_from_constructor() -> None:
    """A pipeline built with a known prior value rejects an immediate spike
    on its very FIRST process() call — proving the seed takes effect before
    any value has flowed through this pipeline instance."""
    pipeline = AbstractorFilterPipeline(
        {"spike_filter": True}, initial_last_valid_state=100.0
    )

    result = pipeline.process("40")

    assert result == 100.0
    assert pipeline.last_event == "spike rejected"


def test_pipeline_without_seed_defaults_to_none() -> None:
    """No initial_last_valid_state given -> starts at None as before
    (backward-compatible default, matches every existing call site)."""
    pipeline = AbstractorFilterPipeline({"spike_filter": True})

    assert pipeline._last_valid_state is None
```

Add to `tests/test_coordinator.py` (matching the existing `test_add_and_remove_subentry` style):

```python
async def test_add_subentry_seeds_pipeline_from_initial_last_valid_state() -> None:
    """add_subentry passes initial_last_valid_state straight through to the
    new pipeline — this is the seam __init__.py uses to restore the spike
    guard from a persisted snapshot after any coordinator rebuild."""
    coordinator = AbstractorDataUpdateCoordinator(Mock())

    coordinator.add_subentry(
        "subentry-1",
        {"device_type": "energy", "source_entity_id": "sensor.x"},
        initial_last_valid_state=456.7,
    )

    assert coordinator.pipelines["subentry-1"]._last_valid_state == 456.7


async def test_add_subentry_without_seed_defaults_to_none() -> None:
    """No prior value known (e.g. brand-new subentry) -> pipeline starts
    unguarded, exactly as before this change."""
    coordinator = AbstractorDataUpdateCoordinator(Mock())

    coordinator.add_subentry(
        "subentry-1", {"device_type": "power", "source_entity_id": "sensor.x"}
    )

    assert coordinator.pipelines["subentry-1"]._last_valid_state is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_filters.py tests/test_coordinator.py -k "seed" -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'initial_last_valid_state'` (pipeline) and the equivalent for `add_subentry`.

- [ ] **Step 3: Write the minimal implementation**

Edit `custom_components/abstractor/filters.py`:
```python
    def __init__(
        self, config: dict[str, Any], initial_last_valid_state: float | None = None
    ):
        self.config = config
        self._last_valid_state: float | None = initial_last_valid_state
        self.last_event: str | None = None
```

Edit `custom_components/abstractor/coordinator.py`:
```python
    def add_subentry(
        self,
        subentry_id: str,
        subentry_data: dict,
        initial_last_valid_state: float | None = None,
    ) -> None:
        """Add a subentry to central polling.

        ``initial_last_valid_state`` seeds the new pipeline's spike-filter
        guard, typically from the last value persisted in the snapshot Store
        (see __init__.py). Without it, a coordinator rebuild — which happens
        on every reload, including one triggered by editing an unrelated
        subentry — would otherwise let one unguarded low reading through on
        the very next poll (REQ-COMP-001).
        """
        config = dict(subentry_data)
        config["device_type"] = config.get("device_type", "power")
        self.subentry_data[subentry_id] = config
        self.pipelines[subentry_id] = AbstractorFilterPipeline(
            config, initial_last_valid_state
        )
```

Edit `custom_components/abstractor/__init__.py` — change the subentry-population loop in `async_setup_entry` (around line 420-421):
```python
    stored_values = domain_data.get("stored_snapshot", {}).get("values", {})
    for subentry_id, subentry in entry.subentries.items():
        coordinator.add_subentry(
            subentry_id,
            dict(subentry.data),
            initial_last_valid_state=stored_values.get(subentry_id),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_filters.py tests/test_coordinator.py -v`
Expected: all tests in both files PASS, including the 4 new ones.

- [ ] **Step 5: Run the full suite for a regression check**

Run: `pytest tests/ -v`
Expected: no new failures introduced (some tests in `test_lifecycle.py`/`test_reconciliation.py` construct coordinators/pipelines directly — confirm none of them break on the new optional constructor parameter, since it defaults to `None` and is purely additive).

- [ ] **Step 6: Commit**

```bash
git add custom_components/abstractor/filters.py custom_components/abstractor/coordinator.py custom_components/abstractor/__init__.py tests/test_filters.py tests/test_coordinator.py
git commit -m "fix(coordinator): restore spike-filter guard from persisted snapshot on rebuild"
```

---

## Task 5: Unify `device_type` default handling and log when it happens (ARCH-5)

**Files:**
- Modify: `custom_components/abstractor/coordinator.py:82-87`
- Modify: `custom_components/abstractor/sensor.py:43-44`
- Test: `tests/test_coordinator.py`, `tests/test_sensor.py`

**Interfaces:** No signature changes — both functions keep their existing parameters; only their internal fallback/logging behavior changes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_coordinator.py`:
```python
def test_add_subentry_logs_warning_when_device_type_missing(caplog) -> None:
    """A corrupted/legacy subentry with no device_type still defaults to
    'power' for polling, but must not do so silently."""
    coordinator = AbstractorDataUpdateCoordinator(Mock())

    coordinator.add_subentry("subentry-1", {"source_entity_id": "sensor.x"})

    assert coordinator.subentry_data["subentry-1"]["device_type"] == "power"
    assert "device_type" in caplog.text
    assert "subentry-1" in caplog.text
```

Add to `tests/test_sensor.py`:
```python
def test_missing_device_type_defaults_to_power_with_warning(caplog) -> None:
    """[ARCH-5] sensor.py must default a missing device_type the same way
    coordinator.py does ('power', not ''), and must log a warning — a
    corrupted/legacy subentry should be visible, not silently mismapped."""
    hass = Mock()
    coordinator = Mock()
    hass.data = {DOMAIN: {"coordinator": coordinator}}
    coordinator.hass = hass
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.subentries = {
        "subentry-1": Mock(
            data={CONF_SOURCE_ENTITY_ID: "sensor.original"}  # no CONF_DEVICE_TYPE
        )
    }
    added = []
    async_add_entities = Mock(
        side_effect=lambda entities, config_subentry_id=None: added.extend(entities)
    )

    import asyncio

    asyncio.get_event_loop().run_until_complete(
        async_setup_entry(hass, entry, async_add_entities)
    ) if False else None  # placeholder removed below

```

Note: the snippet above is intentionally not the final form — `async_setup_entry` is an async function and this test file's existing async tests (e.g. `test_unique_id_derived_from_subentry_data`) are plain `async def test_...(): ...` functions relying on `pytest-asyncio`'s auto mode (confirmed via `pytest.ini`/`pyproject.toml`'s `asyncio_mode=auto`, referenced in `docs/SYSTEM_AUDIT.md:369`). Write it consistently with those neighbors instead:

```python
async def test_missing_device_type_defaults_to_power_with_warning(caplog) -> None:
    """[ARCH-5] sensor.py must default a missing device_type the same way
    coordinator.py does ('power', not ''), and must log a warning — a
    corrupted/legacy subentry should be visible, not silently mismapped."""
    entry = Mock()
    entry.entry_id = "entry-1"
    subentry = Mock()
    subentry.data = {CONF_SOURCE_ENTITY_ID: "sensor.original"}  # no CONF_DEVICE_TYPE
    entry.subentries = {"subentry-1": subentry}
    hass = Mock()
    coordinator = Mock()
    hass.data = {DOMAIN: {"coordinator": coordinator}}
    coordinator.hass = hass
    added = []
    async_add_entities = Mock(
        side_effect=lambda entities, config_subentry_id=None: added.extend(entities)
    )

    await async_setup_entry(hass, entry, async_add_entities)

    assert added[0]._device_type == "power"
    assert added[0].device_class == "power"
    assert "device_type" in caplog.text
    assert "subentry-1" in caplog.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_coordinator.py tests/test_sensor.py -k "device_type" -v`
Expected: the coordinator test currently passes the value-equality assertion (unchanged behavior there) but FAILS on the `caplog.text` assertions (no warning logged today). The sensor test FAILS both on `added[0]._device_type == "power"` (today it's `""`) and on the missing warning.

- [ ] **Step 3: Write the minimal implementation**

Edit `custom_components/abstractor/coordinator.py`:
```python
    def add_subentry(
        self,
        subentry_id: str,
        subentry_data: dict,
        initial_last_valid_state: float | None = None,
    ) -> None:
        """Add a subentry to central polling."""
        config = dict(subentry_data)
        if not config.get("device_type"):
            _LOGGER.warning(
                "Subentry %s has no device_type configured; defaulting to "
                "'power' for polling",
                subentry_id,
            )
            config["device_type"] = "power"
        self.subentry_data[subentry_id] = config
        self.pipelines[subentry_id] = AbstractorFilterPipeline(
            config, initial_last_valid_state
        )
```
(This folds into the same method Task 4 already touched — apply both edits together if doing Tasks 4 and 5 back-to-back; they don't conflict.)

Edit `custom_components/abstractor/sensor.py`, in `async_setup_entry` (around line 44):
```python
    for subentry_id, subentry in entry.subentries.items():
        device_type = subentry.data.get(CONF_DEVICE_TYPE)
        if not device_type:
            _LOGGER.warning(
                "Subentry %s has no device_type configured; defaulting to "
                "'power'",
                subentry_id,
            )
            device_type = "power"
```
(`_LOGGER` already exists at `sensor.py:33`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_coordinator.py tests/test_sensor.py -v`
Expected: all tests PASS, including the 2 new ones. Re-check `test_unique_id_derived_from_subentry_data` and its neighbors in `test_sensor.py` still pass unmodified (they all supply `CONF_DEVICE_TYPE: "power"` explicitly, so the new fallback path shouldn't affect them).

- [ ] **Step 5: Commit**

```bash
git add custom_components/abstractor/coordinator.py custom_components/abstractor/sensor.py tests/test_coordinator.py tests/test_sensor.py
git commit -m "fix: unify missing device_type fallback and log a warning (ARCH-5)"
```

---

## Task 6: Add SSRF-awareness validation to the InfluxDB host field (SEC-1 partial)

**Files:**
- Modify: `custom_components/abstractor/config_flow.py:160-163`
- Test: `tests/test_config_flow.py`

**Interfaces:** No new interfaces — this validates a value at the point it's already collected in `AbstractorOptionsFlow.async_step_init`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config_flow.py`:
```python
async def test_options_flow_rejects_influx_host_without_scheme(hass: HomeAssistant) -> None:
    """[SEC-1] CONF_INFLUX_HOST must be rejected if it isn't http(s):// —
    a bare host/IP with no scheme is exactly the shape of an accidental (or
    malicious) internal-network SSRF target slipped into a free-text field."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POLL_INTERVAL: str(DEFAULT_POLL_INTERVAL),
            CONF_INFLUX_HOST: "169.254.169.254",
            CONF_INFLUX_TOKEN: "",
            CONF_INFLUX_ORG: "",
            CONF_INFLUX_BUCKET: "",
            CONF_DEVICE_NAME: DEFAULT_DEVICE_NAME,
            CONF_DEVICE_MANUFACTURER: DEFAULT_DEVICE_MANUFACTURER,
            CONF_DEVICE_MODEL: DEFAULT_DEVICE_MODEL,
        },
    )

    assert result2["type"] == "form"
    assert result2["errors"]["base"] == "invalid_influx_host"


async def test_options_flow_accepts_influx_host_with_https_scheme(hass: HomeAssistant) -> None:
    """A properly-schemed host is accepted, matching today's behavior."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POLL_INTERVAL: str(DEFAULT_POLL_INTERVAL),
            CONF_INFLUX_HOST: "https://influx.local:8086",
            CONF_INFLUX_TOKEN: "",
            CONF_INFLUX_ORG: "",
            CONF_INFLUX_BUCKET: "",
            CONF_DEVICE_NAME: DEFAULT_DEVICE_NAME,
            CONF_DEVICE_MANUFACTURER: DEFAULT_DEVICE_MANUFACTURER,
            CONF_DEVICE_MODEL: DEFAULT_DEVICE_MODEL,
        },
    )

    assert result2["type"] == "create_entry"
    assert result2["data"][CONF_INFLUX_HOST] == "https://influx.local:8086"


async def test_options_flow_accepts_empty_influx_host(hass: HomeAssistant) -> None:
    """An empty host (Influx export disabled) is not a validation error."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POLL_INTERVAL: str(DEFAULT_POLL_INTERVAL),
            CONF_INFLUX_HOST: "",
            CONF_INFLUX_TOKEN: "",
            CONF_INFLUX_ORG: "",
            CONF_INFLUX_BUCKET: "",
            CONF_DEVICE_NAME: DEFAULT_DEVICE_NAME,
            CONF_DEVICE_MANUFACTURER: DEFAULT_DEVICE_MANUFACTURER,
            CONF_DEVICE_MODEL: DEFAULT_DEVICE_MODEL,
        },
    )

    assert result2["type"] == "create_entry"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_config_flow.py -k "influx_host" -v`
Expected: the rejection test FAILS (`result2["type"] == "create_entry"` today, no validation exists); the two acceptance tests currently PASS already (nothing to break yet) — that's fine, they lock in the non-regression behavior for step 3.

- [ ] **Step 3: Write the minimal implementation**

Edit `custom_components/abstractor/config_flow.py`, in `AbstractorOptionsFlow.async_step_init` — add validation right after `submitted = dict(user_input)`:

```python
        if user_input is not None:
            submitted = dict(user_input)
            influx_host = submitted.get(CONF_INFLUX_HOST, "")
            if influx_host and not influx_host.startswith(("http://", "https://")):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._init_schema(current, interval_value),
                    errors={"base": "invalid_influx_host"},
                )
            interval_value = submitted[CONF_POLL_INTERVAL]
            ...
```

This introduces a call to a not-yet-existing `self._init_schema(...)` helper because the schema-building block currently lives inline in the "show form" branch at the bottom of `async_step_init` (lines 145-192) and needs to be reusable from this new early-return too. Extract it:

```python
    @staticmethod
    def _init_schema(current: dict[str, Any], interval_value: str) -> vol.Schema:
        """Build the main options-flow schema (shared by the initial render
        and the re-render-with-errors path after a validation failure)."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_POLL_INTERVAL, default=interval_value
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            *(str(value) for value in POLL_INTERVAL_PRESETS),
                            "custom",
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_INFLUX_HOST, default=current.get(CONF_INFLUX_HOST, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_INFLUX_TOKEN, default=current.get(CONF_INFLUX_TOKEN, "")
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Optional(
                    CONF_INFLUX_ORG, default=current.get(CONF_INFLUX_ORG, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_INFLUX_BUCKET, default=current.get(CONF_INFLUX_BUCKET, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DEVICE_NAME,
                    default=current.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME),
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DEVICE_MANUFACTURER,
                    default=current.get(
                        CONF_DEVICE_MANUFACTURER, DEFAULT_DEVICE_MANUFACTURER
                    ),
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DEVICE_MODEL,
                    default=current.get(CONF_DEVICE_MODEL, DEFAULT_DEVICE_MODEL),
                ): selector.TextSelector(),
            }
        )
```

And update `async_step_init` to call it in the existing "show form" branch at the bottom too:
```python
        return self.async_show_form(
            step_id="init",
            data_schema=self._init_schema(current, interval_value),
        )
```
replacing the old inline `vol.Schema({...})` block there (delete the now-duplicated inline schema — `_init_schema` is its only home).

Finally, add the error message to `strings.json`/`translations/en.json` under the options-flow `init` step's `"error"` block (create one if it doesn't exist yet — check the current file structure first):
```json
"error": {
  "invalid_influx_host": "InfluxDB host must start with http:// or https://"
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_config_flow.py -v`
Expected: all tests PASS (25 existing + 2 from Task 2 + 3 new here = 30), including confirming the extraction of `_init_schema` didn't change the rendered form for the existing happy-path options-flow tests (if none exist yet for `async_step_init`'s form rendering specifically, this is also new coverage worth having — check `tests/test_config_flow.py` for an existing `async_step_init`/options test to make sure it still passes; if none exists, that itself is a coverage gap worth noting but out of this task's scope).

- [ ] **Step 5: Commit**

```bash
git add custom_components/abstractor/config_flow.py custom_components/abstractor/strings.json custom_components/abstractor/translations/en.json tests/test_config_flow.py
git commit -m "fix(security): reject InfluxDB host values without http(s):// scheme"
```

---

## Task 7: Pin dev/test dependency versions (SEC-4, SEC-5)

**Files:**
- Modify: `requirements_test.txt`
- Modify: `Dockerfile.test:52-58`

**Interfaces:** None (dependency pins only).

- [ ] **Step 1: Check current latest-known-good versions**

Run (or check the most recent successful Docker-based test run's pip freeze if available):
```bash
pip index versions pytest-homeassistant-custom-component
pip index versions ruff
pip index versions mypy
```
Pick the newest version of each that is compatible with `homeassistant==2025.3.0` and Python 3.13 (cross-check `pytest-homeassistant-custom-component`'s own `homeassistant` pin in its `setup.py`/`pyproject.toml` on PyPI if uncertain — it tracks HA versions closely and an overly-new version can require a newer HA than this project pins).

- [ ] **Step 2: Pin `requirements_test.txt`**

```diff
 pytest>=8.0
 pytest-asyncio>=0.24
 pytest-cov>=5.0
-pytest-homeassistant-custom-component
+pytest-homeassistant-custom-component==0.13.351
```
(Use the version confirmed compatible in Step 1 — `0.13.351` was observed already installed in one investigation this session; verify it's still current before committing, don't copy blindly.)

- [ ] **Step 3: Pin `Dockerfile.test`'s dev tools**

Edit `Dockerfile.test:52-58`:
```diff
 RUN pip install --no-cache-dir \
         "homeassistant==${HOMEASSISTANT_VERSION}" \
-        "pytest-homeassistant-custom-component" \
-        "pytest-cov" \
-        "pytest-asyncio" \
-        "ruff" \
-        "mypy"
+        "pytest-homeassistant-custom-component==0.13.351" \
+        "pytest-cov==5.0.0" \
+        "pytest-asyncio==0.24.0" \
+        "ruff==0.8.4" \
+        "mypy==1.13.0"
```
(Confirm each version against Step 1's findings before writing it — do not invent numbers; if a version differs from the placeholders above based on actual `pip index versions` output, use the real one.)

- [ ] **Step 4: Verify the Docker image still builds and tests still pass**

```bash
docker compose -f docker-compose.test.yml build
docker compose -f docker-compose.test.yml run --rm pytest
```
Expected: image builds successfully; test run behaves identically to before pinning (same pass/fail set as whatever Tasks 1–6 have already fixed by this point).

- [ ] **Step 5: Commit**

```bash
git add requirements_test.txt Dockerfile.test
git commit -m "chore(deps): pin dev/test tool versions for reproducible builds"
```

---

## Task 8: Fix CLAUDE.md and AGENTS.md — remove fictional "Besondere Patterns" content and phantom dependencies (DOC-1, DOC-3, SEC-6)

**Files:**
- Modify: `CLAUDE.md` (the managed "Architektur" → "Besondere Patterns" and "Tech-Stack" sections)
- Modify: `AGENTS.md` (mirrors the same managed content)
- Modify: `.meta-config/project.yaml` (the source of truth these are generated from — see `use-lazy-rules.md`/`architecture.md` skill for how agent-meta templates work)

**Interfaces:** None — documentation only, but the fix must go through `.meta-config/project.yaml` + `sync.py`, not hand-edit the generated `CLAUDE.md`/`AGENTS.md` directly, or the next sync will silently overwrite the fix.

- [ ] **Step 1: Locate the source fields**

Read `.meta-config/project.yaml` and find the fields that render into CLAUDE.md's "Besondere Patterns" section (likely a `SPECIAL_PATTERNS` or similar key — grep for a snippet of the current fictional text, e.g. `grep -n "Bridge Pattern" .meta-config/project.yaml`) and the `Key-Dependencies` tech-stack field (`grep -n "pyserial" .meta-config/project.yaml`).

- [ ] **Step 2: Rewrite the patterns field to describe what's actually implemented**

Replace the fictional bullet list with one describing the real, current architecture (cross-check every claim against `docs/ARCHITECTURE.md`, which the docs-hygiene audit track confirmed is accurate and code-verified):
```yaml
special_patterns: |
  - **Singleton root + subentries**: one root ConfigEntry (unique_id ROOT_UNIQUE_ID)
    holds every Abstract sensor as a ConfigSubentry, created/edited through
    ConfigSubentryFlow rather than per-sensor config entries.
  - **DataUpdateCoordinator (HA)**: one shared coordinator polls all subentries'
    sources every poll interval; a single _async_update_data call updates every
    sensor's cached value, avoiding N parallel polls.
  - **Filter pipeline (AbstractorFilterPipeline)**: per-subentry spike filter,
    invert, fail-soft/fail-closed, net-subtract, and REQ-COMP-004 fallback-source
    logic, applied per poll in coordinator.py.
  - **Stable identity via CONF_LEGACY_UNIQUE_ID**: every subentry's unique_id is
    pinned at creation (auto-generated, or explicitly set for migrated sensors)
    and never re-derived from source entity ids afterward, so a later hardware
    swap via reconfigure cannot orphan the entity or its recorder history.
  - **In-memory DeviceRegistry**: a lightweight write-side device registry
    (custom_components/abstractor/repository/device_registry.py) records
    device metadata as sensors are created; HA's own device registry (via
    DeviceInfo) is the actual source of truth for entity/device grouping.
  - **Config Flow with a singleton root unique_id**: the root entry uses a
    fixed unique_id (ROOT_UNIQUE_ID); there is currently no discovery step
    (USB/DHCP/MQTT) or reauth flow.
```
(Adjust exact YAML key/structure to match whatever the real field is named in `project.yaml` — read it first, don't guess the key name.)

- [ ] **Step 3: Fix the phantom dependency list**

In the same file, find the `key_dependencies`/tech-stack field listing `pyserial`/`paho-mqtt` and remove both lines (they correspond to a `bridge/` layer that was never built and is correctly marked "PLANNED / roadmap" elsewhere in the same generated tree). Leave `homeassistant`/`aiohttp`/`voluptuous` as the accurate current list.

- [ ] **Step 4: Re-run sync to regenerate CLAUDE.md and AGENTS.md**

```bash
py .agent-meta/scripts/sync.py --config .meta-config/project.yaml
```
Review `sync.log` for errors/warnings related to this change specifically.

- [ ] **Step 5: Verify the fix**

```bash
grep -n "Bridge Pattern\|AbstractSensor\|pyserial\|paho-mqtt" CLAUDE.md AGENTS.md
```
Expected: no matches (aside from any deliberately-kept historical/roadmap note that explicitly says "not yet built" — re-check the "Architektur" tree section itself is untouched and still correctly says `bridge/`/`sensor_types/` don't exist yet).

- [ ] **Step 6: Commit**

```bash
git add .meta-config/project.yaml CLAUDE.md AGENTS.md .meta-config/context-hashes.json
git commit -m "docs: replace fictional Bridge/Strategy architecture claims with reality"
```

---

## Task 9: Fix stale README claims about InfluxDB and device customization (DOC-4, DOC-5)

**Files:**
- Modify: `README.md` (the "Known limitations" and "Features" sections)

**Interfaces:** None — documentation only.

- [ ] **Step 1: Fix the InfluxDB claim**

Find the "Known limitations" bullet (around line 227-229 per the audit) currently reading approximately: *"InfluxDB push is scaffolded only. The `InfluxExporter` class exists for the optional telemetry push, but it is not yet wired into the Config Flow or activated in the coordinator."*

Replace with:
```markdown
- **InfluxDB export is live** (since 1.1.0-rc.1): configure `influx_host` and
  `influx_token` in the integration's Options to push every poll's aggregated
  value to InfluxDB v2's `/api/v2/write` endpoint. Leave `influx_host` empty
  to disable it entirely (the default). The host must start with `http://` or
  `https://`.
```

- [ ] **Step 2: Fix the device-customization claim**

Find the "Features" → device registry bullet (around line 37-41) currently claiming manufacturer/model customization "is not implemented yet." Split it into what's actually true:
```markdown
- **Device registry integration**: each Abstract sensor appears as a logical
  device in the HA device registry, with a configurable name, manufacturer,
  and model (via Options). Clustering multiple Abstract sensors under one
  shared device is not yet supported by a safe UI path — see
  [Known limitations](#known-limitations) and
  [GH#18](https://github.com/Popoboxxo/AbstrHActor/issues/18).
```

- [ ] **Step 3: Verify against the code one more time before committing**

```bash
grep -n "influx_host\|influx_token" custom_components/abstractor/config_flow.py custom_components/abstractor/coordinator.py
grep -n "device_manufacturer\|device_model" custom_components/abstractor/sensor.py custom_components/abstractor/config_flow.py
```
Confirm both features are indeed wired exactly as the new README text says (already confirmed during the audit — this is a final sanity check before committing doc changes).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: correct stale README claims about InfluxDB export and device options"
```

---

## Task 10: Add Device Bundling traceability and a CHANGELOG caveat (DOC-2, DOC-6, DOC-7)

**Files:**
- Modify: `docs/REQUIREMENTS.md`
- Modify: `docs/REQUIREMENTS_COVERAGE.md`
- Modify: `CHANGELOG.md`
- Delete or fulfill the dangling reference: `docs/SENSOR_TYPES.md` (choose in Step 1)

**Interfaces:** None — documentation/traceability only.

- [ ] **Step 1: Decide on `docs/SENSOR_TYPES.md`**

Either (a) create it — a short table of the 3 sensor types (`power`/`energy`/`water`) and their `device_class`/`unit`/`state_class` mapping, sourced directly from `custom_components/abstractor/sensor.py:126-137` (this content already exists informally in README's "Sensor mapping" table per the audit — this file can just be that table promoted to its own doc), or (b) remove the two dangling references to it in `CLAUDE.md`'s and `AGENTS.md`'s file-tree comments (via `.meta-config/project.yaml`, same mechanism as Task 8) if the team decides a separate file isn't worth maintaining. Recommendation: (a), since the content already exists and a dedicated file is cheap to keep in sync with 3 sensor types.

If choosing (a), create `docs/SENSOR_TYPES.md`:
```markdown
# Supported Sensor Types

Source of truth: `custom_components/abstractor/sensor.py` (device_class/unit/state_class
assignment) and `custom_components/abstractor/const.py` (`SENSOR_TYPES`).

| `device_type` | `device_class` | `native_unit_of_measurement` | `state_class` |
|---|---|---|---|
| `power` | `SensorDeviceClass.POWER` | `W` | `SensorStateClass.MEASUREMENT` |
| `energy` | `SensorDeviceClass.ENERGY` | `kWh` | `SensorStateClass.TOTAL_INCREASING` |
| `water` | `SensorDeviceClass.WATER` | `L` | `SensorStateClass.TOTAL_INCREASING` |

Adding a new type requires changes in three places: `const.py` (`SENSOR_TYPES`),
`sensor.py` (the device_class/unit/state_class if/elif chain — see ARCH-9 in
`docs/SYSTEM_AUDIT_2026-09-04.md` for the case to make this declarative instead),
and `filters.py`'s fail-soft-vs-fail-closed check (`device_type == "power"`).
```

- [ ] **Step 2: Add a Device Bundling requirement**

Append to `docs/REQUIREMENTS.md` (matching its existing `REQ-*` numbering style):
```markdown
## REQ-CORE-008: Device Bundling (Subentry-Based)

**Status:** Partially implemented — foundation shipped in 1.1.0-rc.1, bundling
UI withheld (see GH#18).

The integration SHALL allow multiple Abstract sensors to be organized as
subentries under a single root config entry (REQ-NFA "single config entry"
simplification). Each subentry SHALL retain an independently stable identity
(see REQ-CORE-001) regardless of any later change to its device grouping.

Clustering multiple subentries onto one shared HA device via the UI is
currently withheld: Home Assistant's current device-registry behavior does
not allow reassigning a subentry's device link without destroying another
subentry's entity-registry row on the same device (GH#18). The underlying
`device_group_id` mechanism (`sensor.py`, `config_flow.py::_normalize`) exists
and is exercised only by the legacy-entry migration path today.
```

- [ ] **Step 3: Add a coverage row bridging the two ID schemes**

Append to `docs/REQUIREMENTS_COVERAGE.md`:
```markdown
## REQ-CORE-008 (Device Bundling) — bridges to REQ-* scheme

This requirement was added after this document's original FA-*/NFA-* scheme
was established (against `LASTENHEFT_ABSTRAKTIONS_INTEGRATION.md`) and has no
FA-*/NFA-* equivalent. See `docs/REQUIREMENTS.md#req-core-008` directly.
Tracked issues: [GH#18](https://github.com/Popoboxxo/AbstrHActor/issues/18)
(bundling UI withheld), [GH#19](https://github.com/Popoboxxo/AbstrHActor/issues/19)
(REQ-CORE-001 regression for non-migrated sensors — fixed by
`docs/superpowers/plans/2026-09-04-system-audit-remediation.md` Task 2).
```

- [ ] **Step 4: Add the CHANGELOG caveat**

Edit `CHANGELOG.md`'s `## [1.1.0-rc.1]` entry — find the "Subentry-based device bundling..." line under "Added" and append a caveat in place:
```diff
-- Subentry-based device bundling: create Abstract sensors as subentries and reconcile legacy flat entries on setup
+- Subentry-based device bundling foundation: create Abstract sensors as subentries and reconcile legacy flat entries on setup. **The bundling UI itself (grouping multiple sensors onto one shared device) is withheld pending GH#18** — see Known limitations.
```

- [ ] **Step 5: Commit**

```bash
git add docs/SENSOR_TYPES.md docs/REQUIREMENTS.md docs/REQUIREMENTS_COVERAGE.md CHANGELOG.md
git commit -m "docs: add Device Bundling traceability (REQ-CORE-008) and changelog caveat"
```

---

## Task 11: Repo hygiene — gitignore, relocate stray files, resolve docs/state.md (DOC-9, DOC-10, DOC-11)

**Files:**
- Modify: `.gitignore`
- Move: `CLAUDE.md.sync-backup-20260830-112452`, `audit_report.json`, `reqogniloom_reqs.json`, `scratch_audit.py`, `scratch_decompose.py`, `test_mcp.py`, `task.md` (out of this repo)
- Fold: `docs/state.md` into `CHANGELOG.md`, then remove the standalone file

**Interfaces:** None — filesystem/git hygiene only.

- [ ] **Step 1: Add the missing gitignore pattern**

Edit `.gitignore` — find the existing `AGENTS.md.sync-backup-*` line and add a sibling:
```diff
 AGENTS.md.sync-backup-*
+CLAUDE.md.sync-backup-*
```

- [ ] **Step 2: Remove the current sync-backup file and the ReqogniLoom scratch litter**

These are not AbstrHActor project content (confirmed during the audit: `task.md`/`audit_report.json`/`reqogniloom_reqs.json`/`scratch_audit.py`/`scratch_decompose.py`/`test_mcp.py` describe ReqogniLoom's own self-model/migration work, not this integration). Move them out of the working tree rather than deleting outright, in case they're needed elsewhere:
```bash
mkdir -p ../reqogniloom-scratch-recovered
mv CLAUDE.md.sync-backup-20260830-112452 audit_report.json reqogniloom_reqs.json scratch_audit.py scratch_decompose.py test_mcp.py task.md ../reqogniloom-scratch-recovered/
```
(Confirm with whoever owns the ReqogniLoom self-model workflow that `../reqogniloom-scratch-recovered/` — or wherever they actually belong — is an acceptable landing spot before deleting the copy left here.)

- [ ] **Step 3: Fold `docs/state.md` into the changelog, then remove it**

`docs/state.md`'s content (Device Bundling PR outcome: 7 tasks, 4 critical bugs found/fixed, bundling withdrawn, GH#18/#19, "69/69 unit tests green") is already substantially captured by Task 10's CHANGELOG caveat and the new REQ-CORE-008 entry. Verify nothing in `docs/state.md` is missing from `CHANGELOG.md`'s 1.1.0-rc.1 entry; add any missing detail (e.g. "4 critical bugs found and fixed during the migration, before it went live" is worth a line in the changelog's own notes if not already implied), then:
```bash
git rm --cached docs/state.md 2>/dev/null; rm docs/state.md
```

- [ ] **Step 4: Verify a clean `git status`**

```bash
git status --short
```
Expected: none of the 7 stray files listed in Step 2 appear anymore; no `CLAUDE.md.sync-backup-*` appears even after a future `sync.py` run (verify by re-running `py .agent-meta/scripts/sync.py --config .meta-config/project.yaml --dry-run --check` and confirming no new sync-backup file shows as untracked); `docs/state.md` is gone.

- [ ] **Step 5: Commit**

```bash
git add .gitignore CHANGELOG.md
git rm docs/state.md
git commit -m "chore: gitignore CLAUDE.md sync backups, fold docs/state.md into CHANGELOG"
```
(The 7 relocated files were never tracked, so moving them out of the tree needs no `git add`/`git rm` — only `git status --short` confirmation that they're gone from the untracked list.)

---

## Task 12: Clean up dangling `frontend-component-engineer` references and fix AGENTS.md merge corruption (INFRA-1, INFRA-2)

**Files:**
- Modify: `.claude/pipeline-details/feature-lifecycle.md:13`
- Modify: `.gemini/pipeline-details/feature-lifecycle.md:13`
- Modify: `.opencode/pipeline-details/feature-lifecycle.md:13`
- Modify: `.gemini/agents/orchestrator.md:60`
- Modify: `.opencode/agents/orchestrator.md:59`
- Modify: `AGENTS.md:531-603` (merge corruption)

**Interfaces:** None — configuration/docs cleanup only.

- [ ] **Step 1: Strip the dangling role from all 5 files**

In each of the 5 pipeline-detail/orchestrator files, find the line matching:
```
3. Prüfe: Agent in Stage `implement` ∈ {junior-developer, developer, senior-developer, frontend-component-engineer} → sonst `developer`
```
and remove `, frontend-component-engineer` from the set:
```
3. Prüfe: Agent in Stage `implement` ∈ {junior-developer, developer, senior-developer} → sonst `developer`
```

- [ ] **Step 2: Verify sync.py no longer warns about it**

```bash
py .agent-meta/scripts/sync.py --config .meta-config/project.yaml --dry-run --check 2>&1 | grep -i "frontend-component-engineer"
```
Expected: no output (the warning is gone).

- [ ] **Step 3: Fix AGENTS.md's duplicated "Eigene Notizen" section**

Read `AGENTS.md:520-605` in full to see the exact current corrupted state (line numbers may have shifted slightly since the audit). Identify:
- The genuine `<!-- agent-meta:managed-end -->` marker.
- The first `## Eigene Notizen` header immediately after it.
- The garbled `<!-- agent-meta:managed-begin -->` line with leaked explanatory prose spliced onto it.
- The second, duplicate `## Eigene Notizen` header further down, right before `<!-- agent-meta:bootstrap-begin -->`.

Rewrite that whole span to a single, clean manual-notes section:
```markdown
<!-- agent-meta:managed-end -->

## Eigene Notizen

Hier kannst du eigene, projektspezifische Notizen eintragen. Dieser Bereich wird von `agent-meta` nicht überschrieben!

<!-- agent-meta:bootstrap-begin -->
```
(Preserve any genuine hand-written content that was in either of the two "Eigene Notizen" sections before deleting — read both fully first; if either contains real notes beyond the templated boilerplate sentence, merge that content in rather than discarding it. The audit's own INFRA-6 finding about a stale `claude-expert`/submodule-version note lives in this same span — Task 16 handles that separately, so leave it in place here unless it's easy to fix at the same time.)

- [ ] **Step 4: Commit**

```bash
git add .claude/pipeline-details/feature-lifecycle.md .gemini/pipeline-details/feature-lifecycle.md .opencode/pipeline-details/feature-lifecycle.md .gemini/agents/orchestrator.md .opencode/agents/orchestrator.md AGENTS.md
git commit -m "chore(agent-meta): remove dangling frontend-component-engineer refs, fix AGENTS.md merge corruption"
```

---

## Task 13: Re-sync agent-meta and reconcile the ReqogniLoom external-skill drift (INFRA-3, INFRA-4, INFRA-8)

**Files:**
- Regenerated by sync.py: `.claude/agents/change-manager.md`, `.claude/agents/quality-auditor.md`, `.claude/agents/risk-analyst.md`, `.claude/agents/test-engineer.md` (+ Gemini/Opencode mirrors, + their skill-copy counterparts)
- Modify: `.claude/settings.json`, `.claude/settings.local.json` (remove leftover `mcpServers` keys)
- Modify: `.meta-config/project.yaml` or upstream `external/ReqogniLoom` (for `requirements-architect`, see Step 3)

**Interfaces:** None — sync/config only.

- [ ] **Step 1: Run sync in write mode to pick up the 25 pending writes**

```bash
py .agent-meta/scripts/sync.py --config .meta-config/project.yaml
```
Review `sync.log` for the expected `[WRITE]`/`[COPY]` lines for the 4 ReqogniLoom agents across all 3 providers.

- [ ] **Step 2: Verify drift is resolved**

```bash
py .agent-meta/scripts/sync.py --config .meta-config/project.yaml --dry-run --check
echo "exit code: $?"
```
Expected: exit code `0` (previously `1` with 25 pending writes). If `requirements-architect`'s `[WARN] Skill entry not found` still appears, that's expected — it's Step 3's separate issue, not fixed by a sync run.

- [ ] **Step 3: Reconcile `requirements-architect`**

This skill's template doesn't exist in `external/ReqogniLoom/docs/agent-templates/` at the currently-pinned submodule commit. Two options:
- (a) If ReqogniLoom's own maintainers can add it upstream, file that as a request there and leave a `# TODO(upstream): requirements-architect template missing` note in `.meta-config/project.yaml`'s `external-skills:` list next to the entry.
- (b) If it's not coming, remove `requirements-architect` from `.meta-config/project.yaml`'s `external-skills:` list and from AGENTS.md's manual "Active agents" table, then re-run sync.

Recommendation: (b) for now (removes a permanently-broken warning), with a one-line note pointing at wherever this project tracks upstream ReqogniLoom asks, so it's not silently forgotten.

- [ ] **Step 4: Remove the leftover `mcpServers` keys**

```bash
grep -n "mcpServers" .claude/settings.json .claude/settings.local.json
```
Manually remove the `mcpServers` key (and its value) from both files — it has no effect in this location per sync.py's own warning. Verify each file is still valid JSON after editing:
```bash
python -c "import json; json.load(open('.claude/settings.json'))"
python -c "import json; json.load(open('.claude/settings.local.json'))"
```

- [ ] **Step 5: Final verification**

```bash
py .agent-meta/scripts/sync.py --config .meta-config/project.yaml --dry-run --check; echo "exit code: $?"
```
Expected: exit code `0`, no warnings about `requirements-architect` or `mcpServers`.

- [ ] **Step 6: Commit**

```bash
git add .claude .gemini .opencode .meta-config/project.yaml .meta-config/context-hashes.json AGENTS.md
git commit -m "chore(agent-meta): resync stale ReqogniLoom agents, remove leftover mcpServers keys"
```

---

## Task 14: Add GitHub branch protection on `main` (INFRA-5)

**Files:** None (GitHub repository setting, not a file in the repo).

**Interfaces:** None.

> **This task changes how every future PR merges into `main` for every contributor — it is a consequential, team-wide policy change, not a reversible local edit. Confirm with the user/repo owner before running Step 1 for real; do not execute it autonomously even though it's listed here as a task.**

- [ ] **Step 1 (requires explicit approval before running): enable branch protection requiring the CI checks**

```bash
gh api repos/Popoboxxo/AbstrHActor/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["HACS validation","Hassfest validation","Translations in sync with strings.json","Pytest suite"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews=null \
  --field restrictions=null
```
(Adjust the `contexts` list to match the exact job names as they currently appear in a real check run — confirm via `gh api repos/Popoboxxo/AbstrHActor/commits/main/check-runs --jq '.check_runs[].name'` first, since GitHub Actions job names must match exactly.)

- [ ] **Step 2: Verify**

```bash
gh api repos/Popoboxxo/AbstrHActor/branches/main/protection
```
Expected: `200 OK` with the configured `required_status_checks.contexts` list (previously `404 Not Found`).

- [ ] **Step 3: Document the change**

Update `.claude/rules/dod-criteria.md` to note that "Tests: Test vorhanden & grün" is now also a mechanically-enforced GitHub branch-protection gate, not only a `validator`-agent judgment call — this closes the gap INFRA-5 identified between the documented DoD and its actual enforcement.

```bash
git add .claude/rules/dod-criteria.md
git commit -m "docs: note that main branch protection now enforces the tests-green DoD gate"
```

---

## Task 15: Fix remaining low-severity agent-meta doc precision issues (INFRA-6, INFRA-7)

**Files:**
- Modify: `AGENTS.md` (the "Known agent-meta health items" manual note)
- Modify: `.claude/rules/a2a-delegation-gates.md`

**Interfaces:** None.

- [ ] **Step 1: Update or remove the stale "Known agent-meta health items" note**

In `AGENTS.md`'s manual section (same area touched by Task 12 Step 3), find the note dated "(as of 2026-08-02)" claiming `claude-expert` merely lacks an agent file, and that the submodule is pinned to v0.91.3. Both premises are now false — `claude-expert` was fully removed from `roles:` (Task 12 area confirms no other references remain), and the submodule is on v0.101.0-beta.5. Either delete the note entirely (recommended — it no longer describes anything actionable) or rewrite it to reflect current reality if the team wants a running log of known issues kept here.

- [ ] **Step 2: Fix the hook-file attribution in `a2a-delegation-gates.md`**

Find the line attributing sentinel-declaration parsing to `.claude/hooks/orchestrator-guard.sh` and update it to `.claude/hooks/orchestrator-guard-impl.sh` (the actual location since the #630 wrapper/impl split — `orchestrator-guard.sh` is now just a thin wrapper per its own header comment).

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md .claude/rules/a2a-delegation-gates.md
git commit -m "docs: fix stale agent-meta health note and hook-file attribution"
```

---

## Task 16: CI hygiene — pip caching, pinned action refs, HA-version canary tracking (CI-5, CI-6, CI-7)

**Files:**
- Modify: `.github/workflows/validate.yaml`

**Interfaces:** None.

- [ ] **Step 1: Add pip caching to the pytest job**

```diff
       - uses: actions/setup-python@v5
         with:
           python-version: "3.13"
+          cache: pip
```

- [ ] **Step 2: Pin the floating action refs to specific tags/SHAs**

```bash
gh api repos/hacs/action/releases/latest --jq .tag_name
gh api repos/home-assistant/actions/releases/latest --jq .tag_name
```
Then:
```diff
-      - uses: hacs/action@main
+      - uses: hacs/action@<resolved-tag-or-sha>
...
-      - uses: home-assistant/actions/hassfest@master
+      - uses: home-assistant/actions/hassfest@<resolved-tag-or-sha>
```
(Use the actual resolved values from Step 1's `gh api` calls — do not leave the placeholder text in the committed file.)

- [ ] **Step 3: Open a tracking issue for the next HA Python-floor bump**

```bash
gh issue create \
  --title "Track HA 2026.6.0's Python 3.14 floor bump (next requirements.txt ceiling break)" \
  --body "requirements.txt currently pins homeassistant>=2025.3.0,<2026.6.0 (see Task 1 of docs/superpowers/plans/2026-09-04-system-audit-remediation.md). HA 2026.6.0 raises its Python floor to >=3.14.2, the same class of break that caused the ConfigSubentry CI failure this audit fixed. Before that ceiling is reached, bump validate.yaml's Python version to 3.14 and re-test, then raise the requirements.txt ceiling accordingly."
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/validate.yaml
git commit -m "chore(ci): add pip caching, pin floating action refs"
```

---

## Task 17: Triage stale issue #14 (DOC-12)

**Files:** None (GitHub issue only).

- [ ] **Step 1: Re-check whether #14 still reproduces**

Read `gh issue view 14` for its original repro steps, then check the current E2E workflow's recent runs:
```bash
gh run list --workflow e2e.yaml --limit 5
```
If E2E has been passing consistently since #14 was filed, the underlying flakiness may already be fixed by unrelated churn (per the docs-hygiene audit's note that heavy CI/E2E work landed since #14's creation with zero comment activity on the issue itself).

- [ ] **Step 2: Close or update**

If resolved: `gh issue close 14 --comment "No longer reproduces — E2E has been passing consistently across the last 5 runs since this was filed. Reopen if it resurfaces."`
If still reproducing: `gh issue comment 14 --body "Confirmed still reproducing as of 2026-09-0X during the system-audit remediation pass. <describe current symptom>."` and leave it open.

---

## Task 18: Update `docs/E2E_TESTING.md`'s coverage table (CI-8)

**Files:**
- Modify: `docs/E2E_TESTING.md`

- [ ] **Step 1: Add the two missing rows**

Add `test_device_bundling_e2e.py` and `test_translations_e2e.py` to the existing coverage table, matching its current column format (test file, what it covers, roughly how the other rows are described).

- [ ] **Step 2: Commit**

```bash
git add docs/E2E_TESTING.md
git commit -m "docs: add missing E2E test files to coverage table"
```

---

## Self-review

**Spec coverage:** every Critical and High finding from `docs/SYSTEM_AUDIT_2026-09-04.md` §3 has a task above (CI-1/2/3/4 → Task 1; ARCH-1 → Task 2; ARCH-2 → Task 3; ARCH-3/4 → Task 4; SEC-1 → Task 6 (partial — see backlog for the `iot_class`/full-documentation angle already covered by Task 9); DOC-1/3/SEC-6 → Task 8; DOC-9 → Task 11; INFRA-1/3 → Tasks 12/13). All Medium findings have a task (ARCH-5 → Task 5; DOC-4/5 → Task 9; DOC-2/6/7 → Task 10; DOC-10/11 → Task 11; SEC-2 is intentionally deferred to the backlog below with a documented reason; INFRA-2/4/5/8 → Tasks 12/13/14). Remaining Low-severity findings not given a full task above are in the backlog immediately below, each with a concrete one-line fix rather than a vague placeholder.

**Placeholder scan:** every step above contains real code, real file paths, and real commands. The two exceptions are explicitly marked as requiring a live lookup before finalizing (Task 7's exact pinned versions; Task 14/16's exact check-run/action-ref values) — both call out precisely what command to run to get the real value, which is the correct pattern for values that are only knowable at execution time (a dependency's current release, a live check-run name), not a disguised placeholder for something knowable now.

**Type consistency:** `AbstractorFilterPipeline.__init__`'s new `initial_last_valid_state` parameter (Task 4) and `AbstractorDataUpdateCoordinator.add_subentry`'s new parameter of the same name (Task 4) match in name and type (`float | None = None`) end to end, including at their one call site in `__init__.py`. Task 5's edits to the same `add_subentry` method are written to apply on top of Task 4's version, not to conflict with it (both were verified against the same current source).

---

## P2/P3 Backlog (not detailed to full TDD granularity — concrete, one-line fixes for later)

These are real, verified findings from the audit that are lower-value-per-effort than the tasks above. Each line is a concrete, actionable fix — not a vague "handle X" placeholder — just not broken into bite-sized TDD steps, since they're smaller in scope than a full task warrants.

- **ARCH-6** (hardcoded debug-notify targets): add `CONF_DEBUG_TOGGLE_ENTITY_ID`/`CONF_DEBUG_NOTIFY_SERVICE` as two new Optional fields in `AbstractorOptionsFlow`'s schema (same pattern as the Influx fields), and read them in `coordinator.py:_async_notify_debug` instead of the hardcoded `input_boolean.automation_debugger`/`notify.adminnotificationgroup` strings, defaulting to the current hardcoded values so existing installs keep working unchanged.
- **ARCH-7** (`DeviceRegistry` write-only): either delete `repository/device_registry.py` and its one call site (`sensor.py:122-124`) entirely since `get_device` has zero readers, or wire the frontend panel (`www/abstractor-panel.js`) to actually call `get_device` for its device listing instead of independently re-deriving the same info from `hass.devices` — pick one, don't leave it write-only.
- **ARCH-8** (`SENSOR_TYPES` mutable list): `const.py:46` → `SENSOR_TYPES: Final[tuple[str, ...]] = (TYPE_POWER, TYPE_ENERGY, TYPE_WATER)`. One-line change; check the two call sites (`config_flow.py`'s `SelectSelectorConfig(options=SENSOR_TYPES, ...)` and any iteration) still accept a tuple (they do — both only iterate/pass it to a selector, no list-mutation call sites exist).
- **ARCH-9** (if/elif instead of EntityDescription): either implement a real `AbstractorSensorEntityDescription` dataclass registry (moderate effort, ~40 lines, replaces `sensor.py:126-137`) or — cheaper — amend Task 8's CLAUDE.md rewrite to stop claiming this pattern is used, and note the if/elif chain as the deliberate current approach for exactly 3 types.
- **ARCH-10** (`async_get_device_diagnostics` missing): add it to `diagnostics.py`, delegating to the same data `async_get_config_entry_diagnostics` already assembles, filtered to the one device's subentries (needs a `device_id → subentry_id(s)` lookup via `dr.async_get(hass)`).
- **ARCH-11** (`__init__.py` god-module): extract lines 57-374 (everything from `_SubentrySnapshotView` through `_async_reconcile_legacy_entries`) into a new `custom_components/abstractor/migration.py`, imported and called once from `async_setup`. Pure move, no behavior change — safe to do mechanically once Task 1's CI fix is in place to verify nothing broke.
- **ARCH-12** (`process_sources` mutates shared config): give `AbstractorFilterPipeline.process()` an explicit `apply_spike_filter: bool = True` parameter instead of the `self.config["spike_filter"]` toggle-and-restore dance in `process_sources` (`filters.py:66-84`).
- **SEC-2** (permissive `validate_snapshot`): deferred deliberately — the audit confirmed `stored_snapshot` is currently write-only (never read back to reconstruct entries), so tightening the schema now has no live security payoff. Revisit the moment any future feature starts consuming `stored_snapshot` for restore — at that point, whitelist `entry["data"]`/`entry["options"]` keys against the known `CONF_*` constants in `const.py` before this becomes a real vulnerability, not after.
- **DOC-13** (`strings.json`/`translations/en.json` `title` key diff): no action — confirmed standard HA i18n convention, not a bug.
