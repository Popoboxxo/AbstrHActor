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
| FA-13 | Implemented | Deduplicated events log at debug level and notify `notify.adminnotificationgroup` only when `input_boolean.automation_debugger` is on. |
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
Import validates this shape and stores it for review. It does not create
`ConfigEntry` objects: preserving an existing config-entry ID, entity-registry
identity, unique ID, and Recorder/Long-Term Statistics lineage is not exposed
as a safe public migration API. Recreate entries through Config Flow and
perform any registry/history migration manually and installation-specifically.

The following remain outside this MVP: automatic YAML migration, conditional
cross-entity fallback expressions, native replacement for Utility Meter, and
water-package migration, as listed in the source requirements' out-of-scope
section.
