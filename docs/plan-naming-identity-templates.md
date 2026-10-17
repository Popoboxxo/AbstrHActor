# Plan: Naming & Identity — Templates, Resolution Rules and Semantic Entity IDs

**Status:** Proposed
**Scope:** Naming and identity only (device name, entity friendly name, `entity_id`,
`unique_id`). Units, `device_class`, aggregation and value transforms are explicitly
**out of scope** (owned by `specs.py` / the filter pipeline).
**Motivation:** Today Abstractor generates device/entity names from a single global
`device_name` option and hard-coded English `display_name`s, with no per-device
control and a redundant derived `entity_id`. This plan adds (1) a deterministic
naming/ID resolution chain, (2) safe, declarative, local naming templates, and
(3) an explicit, idempotent rename path — without ever touching sensor identity.

**Related:** `docs/plan-logical-identity-and-panel-ux.md` (WS-A) closes the same
gap G3; this document supersedes its naming/identity *scope* and defines the
template layer WS-A did not cover.

---

## 1. Current state (verified against the code)

| Element | Source today | Example |
|---|---|---|
| Sensor identity (`unique_id`) | `CONF_LEGACY_UNIQUE_ID` (`config_flow.py:310-333`), else derived from sources (`sensor.py:125-134`, `config_flow.py:208-224`) | `abstractor_<uuid4>` |
| Device identifier | `(DOMAIN, device_group_id or subentry_id)` | technical |
| Device display name | Root option `CONF_DEVICE_NAME`, default `"Abstract {device_type}"` (`const.py:81`), `{device_type}` → `device_type.capitalize()` (`sensor.py:141-153`, `binary_sensor.py:96-108`) | «Abstract Power» |
| Entity friendly name | `self._attr_name = spec.display_name` — hard-coded (`sensor.py:136`, `binary_sensor.py:88`, `_actuator.py:88`, `specs.py:83-96`) | «Power» / «Door Contact» |
| `entity_id` | Derived by HA from device name + entity name (`has_entity_name = True`) | `sensor.abstract_power_power` |
| `logical_name` / `object_id` | Stored + used only by the ad-hoc `abstractor/logical_rename` websocket (`websocket.py:313-384`); **not** consumed for initial naming | — |
| Localization of entity/device names | **None** (only Config/Options UI is translated) | always English |

**Known warts**
- Redundant `entity_id` (`abstract_power_power`) — gap **G3**.
- Binary device name keeps the underscore: `"Abstract Door_contact"`.
- `logical_name`/`object_id` are persisted by the panel rename but ignored at entity
  creation, so a rename is a registry mutation with no naming model behind it.

---

## 2. Goals & non-goals

**Goals**
- G1 A single, documented **resolution chain** for device name, entity name and `entity_id`.
- G2 Per-device control via **explicit** `logical_name` / `object_id` (GUI + data).
- G3 **Local, declarative templates** for naming/ID schemes, versioned, with inheritance,
  usable in **both** paths: GUI (pick a template) and YAML/git (author a file).
- G4 **Localized default names** via HA's native `translation_key` mechanism.
- G5 **Identity is untouchable**: templates and names can never change `unique_id`.

**Non-goals (this plan)**
- Remote/OFFICIAL template catalog from GitHub with pinned tags + opt-in upgrade →
  **deferred to a later phase** (§8). The local template format is designed so it can
  later be sourced remotely without rework.
- Units, `device_class`, aggregation, transforms, formulas.

---

## 3. Model

### 3.1 Three distinct concerns

| Concern | Key | Mutable? | Persisted where |
|---|---|---|---|
| **Identity** | `unique_id` | **never** | `CONF_LEGACY_UNIQUE_ID` in subentry data |
| **Display** | device name, entity friendly name | yes, cosmetic | subentry data → derived |
| **Address** | `entity_id` / `object_id` | yes, explicit only | subentry `object_id` + registry |

### 3.2 Resolution chain (highest precedence first)

**Device name**
1. Subentry `logical_name` (shared across all members of a `device_group_id`).
2. Active naming template's `device_name` scheme (root option selects the template).
3. Root option `CONF_DEVICE_NAME` (today's value — for installs without a template).
4. Built-in default `"Abstract {device_type}"`.

**Entity friendly name**
1. Explicit per-subentry `entity_name_override`.
2. Active template's `entity_name[type_key]` → `entity_name.default`.
3. `translations/<lang>.json` `entity.<platform>.<translation_key>.name` (localized default).
4. `spec.display_name` (English fallback).

**`entity_id` / `object_id`**
1. Explicit subentry `object_id` — *suggested* at first creation only.
2. `object_id` scheme from the template (still only a suggestion).
3. HA-derived (today's behavior).

**`unique_id`** — unchanged, and never influenced by anything above.

### 3.3 Data-model changes (all additive, all opt-in)

| Key | Where | Type | Default | Back-compat |
|---|---|---|---|---|
| `logical_name` | subentry data | str (1–64) | *absent* → template/today | new, opt-in |
| `object_id` | subentry data | slug `^[a-z0-9_]+$`, ≤64 | *absent* → HA-derived | new, opt-in |
| `entity_name_override` | subentry data | str (1–64) | *absent* → spec name | new, opt-in |
| `naming_template` | root options | str (template id) | `"default"` | new, opt-in |

**Grouped devices:** `logical_name` is a *device* property but lives in subentry data
(the only snapshotted/exportable store). Rule: every subentry with the same
`device_group_id` carries the same `logical_name`; the rename command writes it in one
transaction (`websocket.py:342-356` already does this).

**Snapshot:** `snapshot.py` only requires `data` to be a dict (`snapshot.py:50-54`), so
new keys round-trip without a version bump. `validate_snapshot` stays version `1`.

---

## 4. Template format (local, declarative, safe)

Files live in the HA config dir: `config/abstractor/templates/<id>.yaml`. Read-only,
schema-validated, never executed.

```yaml
schema_version: 1
id: household
description: "German-friendly, area-prefixed names"
extends: default            # optional; single-parent inheritance chain
variables:
  prefix: "Abstract"
device_name: "{prefix} {spec_display_name}"      # device display name
entity_name:                                     # per type_key, else default
  default: "{spec_display_name}"
  power: "Leistung"
  energy: "Energie"
object_id: "{slug(device_name)}_{type_key}"       # suggestion only
```

**Placeholder engine (deliberately restricted)**
- Allowed tokens: `{device_type}`, `{device_type_label}`, `{spec_display_name}`,
  `{source_entity_id}`, `{area}`, `{logical_name}`, `{prefix}`, `{n}`.
- Allowed filters: `slug`, `lower`, `upper`, `title`.
- Custom tokenizer + mapping resolver. **No** Python `str.format`/`format_map` (attribute
  traversal), **no** `eval`, **no** Jinja. Unknown token/filter → validation error, not
  silent empty.
- Hard limits: file ≤ 64 KB, output ≤ 255 chars, slug output enforced for `object_id`.

**Precedence:** subentry explicit value > active template > root `device_name` > built-in.

---

## 5. Identity guarantees (hard rules)

1. `unique_id` is **only** `CONF_LEGACY_UNIQUE_ID` or the source-derived form. A template,
   `logical_name`, `object_id`, locale or `entity_name_override` change **must not** alter it.
2. `entity_id` is *suggested* at first creation via `self.entity_id` (HA honors it once);
   afterwards the registry row wins — an implicit change can never rename a live entity.
   Changing an existing `entity_id` requires the explicit, admin-gated, collision-checked
   rename path (`websocket.py:361-383`, `config_flow.py:834-849`).
3. Every rename is **idempotent** and previewable (old → new), and preserves the registry
   row so recorder history and statistics stay attached.

---

## 6. Both paths

**GUI**
- Options flow gains a `naming_template` selector (list of valid local templates + `default`).
- The panel's existing rename affordance (`abstractor-panel.js`, `logical_name` / `object_id`)
  is rewired to the real resolution model and shows a preview of the resulting `entity_id`.
- Authoring full templates stays YAML/git (a template *editor* GUI is out of scope).

**YAML / git**
- Users drop files into `config/abstractor/templates/`, commit them to their config repo,
  and pick the active one in the Options flow. Fully offline, fully version-controlled by
  the user. This is the "deviate from official" path for the deferred remote phase.

---

## 7. Phases / workstreams

### Phase 1 — Identity wiring + localization (closes G3)
| Step | Content | Size |
|---|---|---|
| 1.1 | `_resolve_identity()` in `sensor.py`/`binary_sensor.py`/`_actuator.py`: device name = `logical_name` → root `device_name` → default; entity name = override → spec; device `DeviceInfo(name=…)` from resolved value. | S |
| 1.2 | `entity_id` suggestion from `object_id` in `__init__`; slug validation + registry collision check on rename. | S |
| 1.3 | Add `logical_name` / `object_id` / `entity_name_override` to `_schema_for`, `_normalize_subentry_data`, snapshot tolerance, strings/translations; group-leader propagation. | M |
| 1.4 | Localization: add `translation_key` per spec (`specs.py`) + `translations/<lang>.json` entity block; German (`de`) added. | S |
| 1.5 | Wire the panel rename to the resolver + preview. | S |

**Acceptance:** default install (no new keys) produces **byte-identical** output to today;
`logical_name="Kitchen Fridge"`, `object_id="kitchen_fridge_energy"` →
`device "Kitchen Fridge"`, friendly `"Kitchen Fridge Energy"`,
`sensor.kitchen_fridge_energy`; reconfigure the source → `unique_id`, `entity_id`,
history unchanged; `de` locale shows `"Leistung"` without any template.

### Phase 2 — Local template files
| Step | Content | Size |
|---|---|---|
| 2.1 | `naming_template.py`: loader + schema validation + `extends`/inheritance + safe placeholder resolver. HA-free (unit-testable, REQ-NFA-002). | M |
| 2.2 | Skip/repair and error surfacing for broken/unknown templates (never crash setup; fall back to built-in with a logged warning). | S |
| 2.3 | Options-flow `naming_template` selector + `strings.json`/`translations`. | S |
| 2.4 | Docs (`README` config reference, a `docs/NAMING_TEMPLATES.md` with the schema) + sample `default` template shipped. | S |

**Acceptance:** a custom template with `device_name: "{area} {spec_display_name}"` produces
area-named devices; an invalid template is rejected at validation, never applied partially;
changing the active template renames nothing that already exists (display-only).

### Phase 3 (future, out of scope now) — Remote catalog
Deferred design slot: official catalog in a GitHub repo, pinned by tag, opt-in upgrade with
diff/preview, hash-pinned, **blueprint-style** import rather than a bespoke fetcher, and
HACS as the distribution channel. The Phase-2 format is the contract that makes this a
pure transport addition. No work in this plan.

---

## 8. Requirements (proposed for `docs/REQUIREMENTS.md`)

- **REQ-NAME-001 (Identity separation):** `unique_id` MUST NOT be derived from any name,
  template or locale; it is pinned at creation and immutable thereafter.
- **REQ-NAME-002 (Device naming):** the device display name MUST follow the documented
  resolution chain; absent new keys MUST reproduce legacy behavior exactly.
- **REQ-NAME-003 (Entity naming & i18n):** entity friendly names MUST be localizable via
  HA's `translation_key`; a per-subentry override MUST take precedence.
- **REQ-NAME-004 (Semantic entity IDs):** an explicit `object_id` SHOULD yield the
  suggested `entity_id` at creation; renaming an existing entity MUST be explicit,
  idempotent and history-preserving.
- **REQ-NAME-005 (Local templates):** naming/ID schemes MUST be definable in safe,
  declarative, versioned local template files with inheritance and a fixed resolution
  precedence.
- **REQ-NAME-006 (Robustness):** invalid/unknown templates MUST fail safe (built-in
  fallback + warning) and MUST never block integration setup or orphan entities.

---

## 9. Security & safety

- Templates are **data**, never code: restricted placeholder engine, no `eval`/Jinja/`format_map`.
- Files read only from the fixed `config/abstractor/templates/` dir (no traversal); size/
  length limits; schema validation before use.
- No network in the setup path (Phase 1–2). The deferred remote phase must add
  hash-pinning, opt-in upgrade with preview, and never auto-apply.
- Renames are admin-gated, collision-checked and never automatic on upgrade.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Template/rename silently orphaning history | Hard rule §5 + registry-row-preserving rename + tests; `unique_id` non-negotiable. |
| Broken template blocking setup | Fail-safe fallback to built-in + warning (REQ-NAME-006). |
| Divergence from `specs.py` "single source of truth" | Clear layering: `specs.py` = *what* (type/units/fail contract); templates = *how it is named/addressed* only. |
| Scope creep into units/formulas | Explicitly out of scope; separate future plan. |
| GUI template authoring complexity | GUI = choose template + rename only; authoring stays YAML/git. |

---

## 11. Testing (DoD)

- Unit: resolver (whitelist, unknown token error, slug filter), precedence chain, inheritance,
  fallback on broken template, snapshot round-trip with new keys.
- Identity: assert a template/locale/`logical_name` change never alters `unique_id`; assert
  `entity_id` is only suggested at creation.
- Config flow: 100% coverage (project rule) for the new fields/selector.
- E2E: create a sensor, rename via panel, verify `entity_id` + friendly name + history intact.

---

## 12. Open decisions

1. `object_id` scheme in templates: suggestion-only vs. enforced slug — proposal: **suggestion-only**.
2. Template discovery surface: only the Options-flow dropdown, or also a panel list? Proposal: dropdown first.
3. Ship a `de` translation in Phase 1, or defer localization to a separate PR? Proposal: include `de` (primary target locale).
