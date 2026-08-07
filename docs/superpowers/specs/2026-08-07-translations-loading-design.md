# Design: Load Config/Options Flow Translations

**Date:** 2026-08-07
**Status:** Approved
**Sub-project 1 of 4** (translation bug → device bundling → naming → panel write access)

## Problem

Live-testing the demo instance showed every Config Flow and Options Flow field
rendering its raw schema key (`source_entity_ids`, `spike_filter`,
`net_subtract_entity_id`, ...) instead of the translated label and help text.

## Root Cause

`custom_components/abstractor/strings.json` is complete and correct — every
field has a translated `data` label and a `data_description` help text. But
Home Assistant's frontend does not read `strings.json` directly at runtime;
it reads `custom_components/abstractor/translations/<lang>.json`.
`strings.json` is the *source* file that `translations/*.json` is normally
generated from — automatically for HACS-published integrations at release
time, but not for a `custom_components` folder just dropped into a config
directory. This integration never shipped a `translations/` directory at
all, so the frontend falls back to the raw key names.

## Fix

1. **New file:** `custom_components/abstractor/translations/en.json`,
   content identical to `strings.json`'s `config`, `options`, and `services`
   blocks.
2. **CI guard:** a new step in `.github/workflows/validate.yaml` that fails
   the job if `strings.json` and `translations/en.json` diverge (e.g. a
   Python one-liner comparing the parsed JSON of both files). No build
   tooling — sync stays a manual step, but drift can't merge silently.
3. **E2E regression test:** extend the Playwright suite to assert the
   Options dialog shows translated text (`get_by_text("Source entities")`)
   rather than the raw key (`source_entity_ids`) — locks in the fix so it
   can't regress unnoticed.

## Scope Boundary

English only (`en.json`). No other language files — the project has no
existing non-English strings to translate from, and none were requested.

## Testing

- No new unit tests needed (this is a static asset + a CI diff check, no
  Python logic changes).
- One new/extended E2E test covers the runtime-visible behavior end to end.

## Out of Scope

Sub-projects 2–4 (device bundling, custom naming/nomenclature, writable
sidebar panel) are separate specs — see brainstorming session notes. Device
bundling (sub-project 2) is the architectural foundation the later two
depend on.
