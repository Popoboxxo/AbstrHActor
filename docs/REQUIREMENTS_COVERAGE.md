# Requirements Coverage

Audit against `LASTENHEFT_ABSTRAKTIONS_INTEGRATION.md`.

| Requirement | Status | Notes |
|---|---|---|
| FA-01 | Implemented | User Config Flow creates power, energy, and water entries. |
| FA-02 | Unsupported by API | YAML entities are not auto-imported; users must recreate mappings in the UI. |
| FA-03 | Implemented | Sources can be changed through Options Flow and reloaded safely. |
| FA-04 | Implemented | Pure Python monotonic spike guard with unit tests. |
| FA-05 | Implemented | `unknown`/`unavailable` paths are bounded and non-throwing. |
| FA-06 | Implemented | Power defaults unavailable sources to zero. |
| FA-07 | Implemented | Energy remains unavailable unless explicitly configured otherwise. |
| FA-08 | Delegated to HA | Existing Utility Meter remains the supported consumer. |
| FA-09 | Unsupported by API | Existing YAML unique IDs cannot be claimed safely by a custom integration. Manual registry/consumer migration is required. |
| FA-10 | Implemented with explicit sources | Multiple selected entities provide aggregation equivalent to pattern matching. |
| FA-11 | Implemented | Multiple source entities are summed. |
| FA-12 | Implemented | Invert and fallback behavior are configurable per entry. Conditional cross-entity fallback is not modeled. |
| FA-13 | Implemented | Deduplicated events log at debug level and notify the configured `notify` entity only while the configured `input_boolean` debug switch is on (root options, REQ-NFA-007; formerly hardcoded). |
| NFA-01 | Implemented | One coordinator poll and deduplicated notifications. |
| NFA-02 | Implemented | Filter and snapshot validation are HA-independent. |
| NFA-03 | Implemented | Manifest/config flow structure is HACS-compatible. |
| NFA-04 | Implemented | Uses current HA coordinator, Store, service, and config-entry APIs. |
| NFA-05 | Implemented | Native logging, diagnostics, and HA Store snapshot. |
| NFA-06 | Delegated to HA | Utility Meter and existing consumers remain external and unchanged. |
| NFA-07 | Implemented | New mappings require no Python changes. |
| NFA-08 | Implemented | Typed, documented Python modules with focused tests. |

## Import Boundary

Exports use `format: abstractor.snapshot`, `version: 1`, an `entries` list
containing portable `data` and `options`, and the latest abstracted `values`.
Import validates this shape, persists it, and restores **missing** sensor
subentries: an entry is recreated only when no existing subentry has the same
stable identity (`legacy_unique_id`, else source-derived unique id), going
through the same normalization as the config flow create path. Existing
subentries are never overwritten or duplicated, and snapshot `entry_id`s are
reused so the `values` map and ungrouped device identifiers stay aligned.
Subentries with no source entity are skipped with a warning. Since recreation
pins the snapshot's identity fields, entity-registry rows and Recorder/Long-Term
Statistics lineage continue on the restored sensors instead of starting over.

The following remain outside this MVP: automatic YAML migration, conditional
cross-entity fallback expressions, native replacement for Utility Meter, and
water-package migration, as listed in the source requirements' out-of-scope
section.

## REQ-CORE-008 (Device Bundling) — bridges to REQ-* scheme

This requirement was added after this document's original FA-*/NFA-* scheme
was established (against `LASTENHEFT_ABSTRAKTIONS_INTEGRATION.md`) and has no
FA-*/NFA-* equivalent. See `docs/REQUIREMENTS.md`, section 2 (Core Features),
REQ-CORE-008, for the full description.

## REQ-CORE-009 / REQ-DATA-003 / REQ-NFA-007 (Phase 1 management backend)

Added after this document's original FA-*/NFA-* scheme was established and have
no FA-*/NFA-* equivalent:

- **REQ-CORE-009** (sensor deletion service, `delete_sensor`, by `subentry_id`
  or `legacy_unique_id`) — see `docs/REQUIREMENTS.md` §2; implemented on
  `feat/phase1-management-backend`.
- **REQ-DATA-003** (import restores missing subentries) — see
  `docs/REQUIREMENTS.md` §7; implemented via the shared
  `_build_new_subentry_data`/`_normalize_subentry_data` helpers (single source
  of truth with the config flow create path).
- **REQ-NFA-007** (configurable debug-notify targets as root options) — see
  `docs/REQUIREMENTS.md` §6.

Tracked issues:

- [GH#18](https://github.com/Popoboxxo/AbstrHActor/issues/18) — device
  bundling via shared subentry device identifiers is not supported by Home
  Assistant's current device model; the bundling UI is withheld pending a
  non-destructive fix.
- [GH#19](https://github.com/Popoboxxo/AbstrHActor/issues/19) — REQ-CORE-001
  regression for non-migrated sensors (a reconfigure could change a
  newly-created sensor's `unique_id`). Fixed on this branch by Task 2 of
  `docs/superpowers/plans/2026-09-04-system-audit-remediation.md`.
