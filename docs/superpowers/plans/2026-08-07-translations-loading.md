# Translations Loading Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Abstractor integration's Config Flow and Options Flow show translated field labels and help text instead of raw schema keys.

**Architecture:** Home Assistant's frontend reads runtime translations from `custom_components/abstractor/translations/<lang>.json`, not from `strings.json` (the latter is only the source developers hand-edit; HACS-published integrations get `translations/*.json` generated from it automatically at release time, but this repo never shipped that generated file). The fix is additive only: ship `translations/en.json` with the same content `strings.json` already has, add a CI check that keeps the two files from silently diverging, and add an E2E test that locks in the user-visible behavior.

**Tech Stack:** Python 3.12+, Home Assistant custom integration, GitHub Actions (`.github/workflows/validate.yaml`), Playwright E2E (`tests_e2e/`, pytest).

## Global Constraints

- English only — no `de.json` or other language files. The project has no existing non-English strings to translate from, and none were requested (per spec `docs/superpowers/specs/2026-08-07-translations-loading-design.md`, "Scope Boundary").
- No Python logic changes — this is a static JSON asset, a CI YAML step, and an E2E test only.
- `translations/en.json`'s `config`/`options`/`services` blocks must be byte-for-byte structurally identical (same keys, same values) to `strings.json`'s corresponding blocks — that's what the CI guard enforces.

---

## File Structure

- Create: `custom_components/abstractor/translations/en.json` — the runtime translation file HA's frontend actually reads.
- Modify: `.github/workflows/validate.yaml` — add a step to the existing `hacs` job (or a new job) that fails CI if `strings.json` and `translations/en.json` diverge.
- Create: `tests_e2e/test_translations_e2e.py` — new E2E test asserting the Options dialog shows translated text.

---

### Task 1: Write the failing E2E test

**Files:**
- Create: `tests_e2e/test_translations_e2e.py`

**Interfaces:**
- Consumes: `logged_in_page`, `hass_base_url` fixtures from `tests_e2e/conftest.py` (already exist, used by every other E2E test in this suite — see `tests_e2e/test_unique_id_stability_e2e.py` for the exact same fixture usage pattern).
- Consumes: the same "add a device, then open its Options dialog via the per-domain page's Configure button" navigation pattern already proven in `tests_e2e/test_unique_id_stability_e2e.py::_add_device` (lines 17–55) and the Options-dialog-opening block in `tests_e2e/test_unique_id_stability_e2e.py::test_reconfiguring_source_keeps_same_entity_id` (lines 90–106). Do not refactor that file to share code — duplicate the minimal needed sequence inline in the new test file, matching the existing suite's convention of light duplication over cross-file helper imports (every existing E2E test file already does this).
- Produces: nothing consumed by later tasks — this is a leaf test file.

- [x] **Step 1: Write the failing test**

```python
"""E2E regression test: Config/Options Flow fields must show their
translated label and help text (from strings.json, loaded at runtime via
translations/en.json), not the raw schema key. See
docs/superpowers/specs/2026-08-07-translations-loading-design.md for the
root cause (HA's frontend reads translations/<lang>.json at runtime, not
strings.json directly — this integration never shipped that file)."""
from __future__ import annotations

import re


def test_options_dialog_shows_translated_labels(
    logged_in_page, hass_base_url, hass_bearer_token
):
    page = logged_in_page

    # Add a device via the Config Flow — same pattern as
    # tests_e2e/test_unique_id_stability_e2e.py::_add_device.
    page.goto(f"{hass_base_url}/config/integrations/dashboard")
    page.get_by_text("Add integration", exact=False).click()
    brand_search = page.get_by_placeholder(re.compile("search for a brand", re.I))
    brand_search.fill("Abstractor")
    brand_search.press("Enter")
    page.get_by_label(re.compile("source_entity_id|source entity$", re.I)).click()
    search_field = page.get_by_placeholder("Search", exact=True)
    search_field.wait_for(state="visible", timeout=5000)
    search_field.press_sequentially("Fridge Power")
    page.get_by_text("Fridge Power", exact=False).first.click()
    page.get_by_role("button", name=re.compile("submit|ok", re.I)).click()
    page.wait_for_timeout(500)
    skip_button = page.get_by_role("button", name=re.compile("finish|skip", re.I))
    if skip_button.count():
        skip_button.first.click()

    # Open this device's Options dialog — same navigation as
    # tests_e2e/test_unique_id_stability_e2e.py lines 90-106.
    page.goto(f"{hass_base_url}/config/integrations/integration/abstractor")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Configure", exact=True).last.click()
    page.wait_for_timeout(500)

    # The bug: without translations/en.json, HA falls back to showing the
    # raw schema key as the field heading. Assert the TRANSLATED heading is
    # visible, and the raw key is not — this fails today and passes once
    # translations/en.json exists (Task 2).
    assert page.get_by_text("Source entities", exact=True).count() > 0, (
        "expected the translated field label 'Source entities' in the "
        "Options dialog — got raw key instead, translations/en.json is "
        "missing or not being read"
    )
    assert page.get_by_text("source_entity_ids", exact=True).count() == 0, (
        "raw schema key 'source_entity_ids' is still visible as a field "
        "heading — translations aren't loading"
    )
    assert page.get_by_text("Enable spike filter", exact=True).count() > 0, (
        "expected the translated field label 'Enable spike filter' in the "
        "Options dialog"
    )
```

- [x] **Step 2: Run test to verify it fails**

Run (from the repo root, via the E2E docker stack — see `docker/README.md` for the required `rm -r docker/ha_config_e2e/.storage` cleanup before a fresh run):

```bash
docker compose -f docker-compose.e2e.yml down -v
rm -r docker/ha_config_e2e/.storage
docker compose -f docker-compose.e2e.yml build e2e
docker compose -f docker-compose.e2e.yml up -d homeassistant
docker compose -f docker-compose.e2e.yml run --rm e2e tests_e2e/test_translations_e2e.py -v
docker compose -f docker-compose.e2e.yml down -v
```

Expected: **FAIL** on the first assertion (`"Source entities"` not found), because `custom_components/abstractor/translations/` doesn't exist yet, so HA falls back to raw keys.

(`docker compose up` cannot target a single test file — `Dockerfile.e2e` sets `ENTRYPOINT ["pytest"]` / `CMD ["tests_e2e/", "-v"]`, so `up` always runs the whole suite. `run --rm e2e <args>` replaces `CMD` and runs only the given file; `run` starts `homeassistant` as a dependency automatically, but bringing it up explicitly first with `up -d homeassistant` avoids a race with the healthcheck.)

- [x] **Step 3: Commit the failing test**

```bash
git add tests_e2e/test_translations_e2e.py
git commit -m "test: add failing E2E test for translated Options dialog labels"
```

---

### Task 2: Add translations/en.json

**Files:**
- Create: `custom_components/abstractor/translations/en.json`
- Read (reference only, do not modify): `custom_components/abstractor/strings.json`

**Interfaces:**
- Consumes: nothing.
- Produces: the file Task 1's test asserts against; also the file Task 3's CI guard compares against `strings.json`.

- [x] **Step 1: Create the translations directory and file**

Content is `strings.json`'s `config`, `options`, and `services` blocks, copied verbatim (confirmed current content of `strings.json` as of this plan — if `strings.json` has changed since, copy its *current* `config`/`options`/`services` blocks instead of this snapshot):

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Add Abstract Device",
        "description": "Choose the type of abstract device you want to create.",
        "data": {
          "device_type": "Device Type",
          "source_entity_id": "Source entity",
          "source_entity_ids": "Source entities",
          "legacy_unique_id": "Legacy unique ID (optional)"
        },
        "data_description": {
          "device_type": "Power, energy, or water abstraction layer.",
          "source_entity_id": "Single hardware sensor to abstract.",
          "source_entity_ids": "Select one or more entities to sum. Use this instead of the single-source field for aggregation.",
          "legacy_unique_id": "Reuse the unique_id of a migrated YAML template sensor so recorder history keeps counting."
        },
        "error": {
          "source_required": "Select at least one source entity."
        }
      }
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Abstract Device Options",
        "description": "Change the source entities or adjust the value pipeline.",
        "data": {
          "source_entity_ids": "Source entities",
          "spike_filter": "Enable spike filter",
          "invert": "Invert value",
          "fallback_zero": "Fallback to zero",
          "net_subtract_entity_id": "Subtract entity (net flow)",
          "fallback_source_entity_id": "Fallback source entity",
          "fallback_condition_entity_id": "Fallback condition entity",
          "fallback_condition_state": "Fallback condition state"
        },
        "data_description": {
          "source_entity_ids": "Replace or extend the hardware entities feeding this abstract sensor.",
          "spike_filter": "Reject drops below the last valid value (recommended for energy and water counters).",
          "invert": "Multiply the value by -1 (e.g. net flow: load minus feed-in).",
          "fallback_zero": "Report 0 instead of unavailable when no source delivers a value.",
          "net_subtract_entity_id": "Subtracted from the aggregate after summing, e.g. charge minus discharge.",
          "fallback_source_entity_id": "Alternate hardware source used when the primary is unavailable and the condition below is met.",
          "fallback_condition_entity_id": "Optional entity whose state gates the fallback. Leave empty to always allow the fallback.",
          "fallback_condition_state": "State the condition entity must match for the fallback to activate."
        }
      }
    }
  },
  "services": {
    "export_data": {
      "name": "Export Abstractor Data",
      "description": "Persist and log a complete snapshot of all abstract sensor mappings and values."
    },
    "import_data": {
      "name": "Import Abstractor Data",
      "description": "Validate and store a previously exported snapshot. Does not recreate or modify config entries.",
      "fields": {
        "data": {
          "name": "Snapshot",
          "description": "Snapshot object produced by abstractor.export_data."
        }
      }
    }
  }
}
```

- [x] **Step 2: Run the E2E test to verify it now passes**

```bash
docker compose -f docker-compose.e2e.yml down -v
rm -r docker/ha_config_e2e/.storage
docker compose -f docker-compose.e2e.yml build e2e
docker compose -f docker-compose.e2e.yml up -d homeassistant
docker compose -f docker-compose.e2e.yml run --rm e2e tests_e2e/test_translations_e2e.py -v
docker compose -f docker-compose.e2e.yml down -v
```

Expected: **PASS**. (See Task 1 Step 2 for why `run --rm e2e <file>` is used instead of `up`.)

- [x] **Step 3: Run the full E2E suite to check for regressions**

```bash
docker compose -f docker-compose.e2e.yml down -v
rm -r docker/ha_config_e2e/.storage
docker compose -f docker-compose.e2e.yml up --build --abort-on-container-exit --exit-code-from e2e
```

Expected: all 6 tests pass (the 5 pre-existing tests plus the new one). If any pre-existing test now fails, it's very likely because it was relying on the *raw key* text somewhere `get_by_text` matched loosely (e.g. a substring match against `"source_entity_ids"` that no longer appears) — inspect the failure, and if so, update that assertion to match the new translated text instead of reverting this fix. `aria-label`-based locators (e.g. `page.get_by_label(re.compile("source_entity_id|source entity$", re.I))` in `test_config_flow_e2e.py` and `test_unique_id_stability_e2e.py`) are expected to be unaffected — `aria-label` on HA's picker components is generated from the raw field key regardless of translation state, confirmed during the original E2E debugging session (see `test_unique_id_stability_e2e.py` lines 107–109's comment, which documents this as a separate, known mechanism from the visible-heading bug this task fixes).

- [x] **Step 4: Commit**

```bash
git add custom_components/abstractor/translations/en.json
git commit -m "fix: ship translations/en.json so config/options flow labels render"
```

---

### Task 3: Add CI guard against strings.json/translations drift

**Files:**
- Modify: `.github/workflows/validate.yaml`

**Interfaces:**
- Consumes: `custom_components/abstractor/strings.json`, `custom_components/abstractor/translations/en.json` (both from Task 2 and earlier).
- Produces: nothing consumed by later tasks — this is the last task in this plan.

- [x] **Step 1: Add the CI step**

Modify `.github/workflows/validate.yaml`, adding a new job (current file has `hacs` and `hassfest` jobs — add a third, independent job so a translation-sync failure doesn't get bundled into or confused with the HACS validation job's own pass/fail signal):

```yaml
  translations-sync:
    name: Translations in sync with strings.json
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Compare strings.json and translations/en.json
        run: |
          python3 -c "
          import json, sys
          with open('custom_components/abstractor/strings.json') as f:
              source = json.load(f)
          with open('custom_components/abstractor/translations/en.json') as f:
              translated = json.load(f)
          for key in ('config', 'options', 'services'):
              if source.get(key) != translated.get(key):
                  print(f'MISMATCH in {key!r} block between strings.json and translations/en.json')
                  sys.exit(1)
          print('strings.json and translations/en.json are in sync.')
          "
```

Full resulting file:

```yaml
name: Validate

on:
  push:
  pull_request:
  schedule:
    - cron: "0 3 * * *"
  workflow_dispatch:

jobs:
  hacs:
    name: HACS validation
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: integration

  hassfest:
    name: Hassfest validation
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master

  translations-sync:
    name: Translations in sync with strings.json
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Compare strings.json and translations/en.json
        run: |
          python3 -c "
          import json, sys
          with open('custom_components/abstractor/strings.json') as f:
              source = json.load(f)
          with open('custom_components/abstractor/translations/en.json') as f:
              translated = json.load(f)
          for key in ('config', 'options', 'services'):
              if source.get(key) != translated.get(key):
                  print(f'MISMATCH in {key!r} block between strings.json and translations/en.json')
                  sys.exit(1)
          print('strings.json and translations/en.json are in sync.')
          "
```

- [x] **Step 2: Dry-run the comparison locally to verify it passes on the current (in-sync) files**

```bash
python3 -c "
import json, sys
with open('custom_components/abstractor/strings.json') as f:
    source = json.load(f)
with open('custom_components/abstractor/translations/en.json') as f:
    translated = json.load(f)
for key in ('config', 'options', 'services'):
    if source.get(key) != translated.get(key):
        print(f'MISMATCH in {key!r} block between strings.json and translations/en.json')
        sys.exit(1)
print('strings.json and translations/en.json are in sync.')
"
```

Expected: prints `strings.json and translations/en.json are in sync.` and exits 0.

- [x] **Step 3: Dry-run the comparison against an intentionally mismatched copy to verify it correctly fails**

```bash
cp custom_components/abstractor/translations/en.json /tmp/en.json.bak
python3 -c "
import json
with open('custom_components/abstractor/translations/en.json') as f:
    d = json.load(f)
d['config']['step']['user']['data']['device_type'] = 'DRIFTED'
with open('custom_components/abstractor/translations/en.json', 'w') as f:
    json.dump(d, f)
"
python3 -c "
import json, sys
with open('custom_components/abstractor/strings.json') as f:
    source = json.load(f)
with open('custom_components/abstractor/translations/en.json') as f:
    translated = json.load(f)
for key in ('config', 'options', 'services'):
    if source.get(key) != translated.get(key):
        print(f'MISMATCH in {key!r} block between strings.json and translations/en.json')
        sys.exit(1)
print('strings.json and translations/en.json are in sync.')
"
echo "exit code: $?"
cp /tmp/en.json.bak custom_components/abstractor/translations/en.json
rm /tmp/en.json.bak
```

Expected: prints `MISMATCH in 'config' block...` and the exit code line shows `exit code: 1`. Then confirm the restore worked: `git status` shows no changes to `translations/en.json`.

- [x] **Step 4: Commit**

```bash
git add .github/workflows/validate.yaml
git commit -m "ci: fail validate.yaml if translations/en.json drifts from strings.json"
```

---

## Self-Review

**Spec coverage:** Spec's 3 fix items (translations/en.json, CI guard, E2E test) map to Task 2, Task 3, Task 1 respectively. Spec's scope boundary (English only) is respected — no other language files created. Spec's "no new unit tests needed" respected — no unit test tasks included.

**Placeholder scan:** No TBD/TODO. Every step has literal, runnable commands or complete file content — no "similar to X" hand-waving, no "add appropriate handling."

**Type consistency:** N/A — no functions/classes are introduced across tasks; only static JSON, a YAML step, and one self-contained test file.
