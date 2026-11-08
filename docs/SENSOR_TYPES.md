# Supported Abstractor Types

Source of truth: `custom_components/abstractor/specs.py` (`SPEC_REGISTRY`).
The config/WS schemas, the panel type catalogue (`abstractor/types`), the
entity platforms and the filter pipeline all derive from this registry — do
not add a second list in JS or Python.

## Shipped types (`enabled=True`)

| `device_type` | Platform | `device_class` | Unit | `state_class` | Failure contract | Numeric |
|---|---|---|---|---|---|---|
| `power` | `sensor` | `power` | `W` | `measurement` | `soft_zero` | yes |
| `energy` | `sensor` | `energy` | `kWh` | `total_increasing` | `fail_closed` | yes |
| `water` | `sensor` | `water` | `L` | `total_increasing` | `fail_closed` | yes |
| `door_contact` | `binary_sensor` | `door` | — | — | `pass_through` | no |
| `motion` | `binary_sensor` | `motion` | — | — | `pass_through` | no |
| `smoke` | `binary_sensor` | `smoke` | — | — | `pass_through` | no |
| `switch_state` | `switch` | — | — | — | `pass_through` | no |
| `light_state` | `light` | — | — | — | `pass_through` | no |
| `cover_position` | `cover` | — | `%` | — | `pass_through` | no |

Numeric types expose the optional value pipeline (aggregation, spike filter,
invert, net subtract, fallback). Pass-through types render the source state
verbatim and never expose numeric-only fields.

## Declared but not shipped

| `device_type` | Why it is disabled |
|---|---|
| `riemann_energy` | Decision **D-1** (audit follow-up 2026-11): keep `enabled=False` until REQ-SENS-003 is re-reviewed against HA Core's own Riemann integration; it also depends on the external `riemann_left` integration. Enabling it is an explicit, reviewed change. |

## Additive options (per subentry)

| Field | Effect |
|---|---|
| `display_unit` / `display_precision` | Presentation only. The persisted value and Influx payload keep the spec unit; the panel converts/rounds at the render boundary. |
| `warn_above` / `warn_below` | Threshold-derived `ok`/`warn`/`bad` health (optional condition gate via `warn_condition_entity_id`). |
| `logical_name` / `object_id` / `entity_name` | Naming only; never touches the pinned `legacy_unique_id`. |

**No warn companion entity** (decision **D-2**): the health chip, Health tab
and threshold metadata cover the use case without adding a `binary_sensor`
per sensor (which would surprise dashboards and change entity counts).

## Adding a new type

1. Register one `AbstractSpec` in `specs.py` (platform, device class, unit,
   failure contract, display name).
2. If the platform is new, add the platform to `__init__.py`'s `PLATFORMS`
   and implement the entity class.
3. Add the type to the relevant test tables (`tests/test_specs.py`,
   `tests/test_schema.py`) — the catalogue, WS validation and panel chips
   follow automatically.
