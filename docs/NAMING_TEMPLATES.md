# Naming & identity templates

Abstractor keeps an entity's **identity** (`unique_id`) and its **display**
(device name, entity name, suggested `entity_id`) strictly separate. Identity is
pinned once at creation and never changes when you swap hardware; display can be
reshaped freely — per sensor, or with a reusable local template (REQ-NAME-001).

## What a template can and cannot do

- It changes the **device name**, the **entity name**, and the **suggested
  `entity_id``** (only at first creation).
- It never touches a sensor's **`unique_id`** — recorder history, dashboards and
  utility meters stay intact.
- Templates are **data, not code**: a tiny placeholder engine, no `eval`, no
  Jinja, no `str.format`. A template cannot reach into your system.

## Where templates live

```
<config>/abstractor/templates/*.yaml
```

Every `*.yaml` in that directory is loaded at setup (and on options reload).
`default` is reserved and means "built-in behaviour" — you never need a file for
it. A broken or unknown template is skipped with a warning; the sensor falls back
to the built-in naming and setup is never blocked (REQ-NAME-006).

Pick the active template in **Settings → Devices & Services → Abstractor →
Configure → Naming template**.

## Precedence

Highest wins:

1. A subentry's explicit `logical_name` / `entity_name` / `object_id`.
2. The active naming template.
3. The root option `device_name` (legacy `Abstract {device_type}`).
4. The built-in default.

## Example

```yaml
# <config>/abstractor/templates/household.yaml
schema_version: 1
id: household
description: "Home naming for our household"
variables:
  home: "Home"
device_name: "{home} {spec_display_name}"
entity_name:
  default: "{spec_display_name}"
  power: "Power draw"
  energy: "Energy total"
object_id: "{slug(device_name)}_{device_type}"
```

With this template a `power` sensor becomes:

| Output | Value |
|---|---|
| Device name | `Home Power` |
| Entity name | `Power draw` |
| `entity_id` | `home_power_power` |
| `unique_id` | unchanged (pinned at creation) |

## Placeholders

Built-in tokens (plus anything you define under `variables`):

| Token | Meaning | Example (`power`) |
|---|---|---|
| `device_type` | raw type key | `power` |
| `device_type_label` | type key, capitalised | `Power` |
| `spec_display_name` | human display name | `Power` |
| `device_name` | the rendered `device_name` (for `object_id`/`entity_name`) | `Home Power` |

Filters (optional, e.g. `{slug(device_name)}`):

`slug`, `lower`, `upper`, `title`.

Unknown tokens or filters make the template invalid — it is skipped rather than
applied partially.

## Inheritance (`extends`)

A template may extend another by `id`; `entity_name` maps merge with the child
taking precedence.

```yaml
schema_version: 1
id: base
device_name: "{spec_display_name}"
entity_name:
  power: "Power"
```

```yaml
schema_version: 1
id: kitchen
extends: base
entity_name:
  energy: "Kitchen energy"
```

`kitchen` keeps `power: Power` from `base` and adds its own `energy`. Cycles and
inherit chains deeper than 10 are rejected.

## Fields

| Field | Required | Notes |
|---|---|---|
| `schema_version` | yes | must be `1` |
| `id` | yes | the filename-independent identifier you select in the flow |
| `description` | no | shown in the flow |
| `extends` | no | another template `id` to inherit from |
| `variables` | no | free-form `name: value` map of extra tokens |
| `device_name` | no | template for the device name |
| `entity_name` | no | map of `default` plus per-type keys (`power`, `energy`, …) |
| `object_id` | no | template for the suggested `entity_id` suffix (slugified) |
