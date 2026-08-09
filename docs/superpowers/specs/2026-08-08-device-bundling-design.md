# Design: Device Bundling (multiple Abstract sensors on one HA device)

**Date:** 2026-08-08
**Status:** Approved
**Sub-project 2 of 4** (translation bug → device bundling → naming → panel write access)

## Problem

Every Abstractor config entry today creates exactly one Home Assistant device
with exactly one sensor entity (`DeviceInfo.identifiers={(DOMAIN, entry.entry_id)}`
in `custom_components/abstractor/sensor.py`). Users who want, say, "Power",
"Energy", and "Water" abstraction for the same physical location end up with
three separate devices instead of one device with three sensors. This must be
possible both when adding new sensors and when reorganizing existing ones.

## Requirements

- Bundle multiple Abstract sensors (any mix of power/energy/water) onto one HA
  device, both at creation time and retroactively for already-configured
  sensors.
- A new sensor can be added either to a new device or an existing one, chosen
  in the same "Add Integration" flow (no separate UI path for the two cases).
- An existing sensor can be moved to a different existing device, or split
  back out to its own device, via its own Options Flow.
- No change to any existing `unique_id`/`entity_id` or to recorder history —
  non-negotiable, matches this project's established stability guarantee
  (REQ-CORE-001).

## Architecture

Built on Home Assistant's **config subentries** (native since ~HA 2025.2/2025.3
— this project's `homeassistant` floor moves from `2025.1.0` to `2025.3.0` in
`hacs.json`/`manifest.json`). A single singleton "Abstractor" config entry
(`unique_id="abstractor_root"`) becomes the parent; every Abstract sensor
becomes a **subentry** under it, replacing today's one-top-level-entry-per-
sensor model.

**Device bundling mechanism:** multiple subentries can supply the same
`DeviceInfo.identifiers` value — Home Assistant's device registry
automatically merges them into one device (confirmed against the official
`home-assistant/architecture` design discussion for config subentries:
"entities coming from different config subentries of the same config entry
can be linked to the same device"). Moving a sensor between devices, or
splitting it back to its own device, is just changing which device-identifier
value its subentry supplies — no effect on the sensor's own `unique_id`.

**Coordinator:** `AbstractorDataUpdateCoordinator` is already keyed by entry
id (`self.entries[entry.entry_id]`, `self.pipelines[entry.entry_id]` in
`coordinator.py`) and has no device concept at all — it becomes keyed by
`subentry_id` instead. The filter pipeline logic itself (`filters.py`) is
untouched.

**Config flow changes:**
- `AbstractorConfigFlow.async_step_user` becomes the one-time setup step for
  the singleton root entry only (no sensor data collected here anymore).
- New `AbstractorSensorSubentryFlow(ConfigSubentryFlow)` takes over today's
  sensor creation/editing (source entity, device type, and — new — which
  device to attach to: an existing device's identifier, or "new device").
- `AbstractorConfigFlow.async_get_supported_subentry_types` registers the new
  handler.
- **UX entry point:** because the root entry is a singleton (Home Assistant
  blocks a second "Abstractor" integration instance), adding a new sensor to
  an existing setup happens via the subentry "add" action on the existing
  integration entry — Home Assistant's native affordance for this (the same
  pattern MQTT and other subentry-using integrations use) — not by repeating
  "Add Integration".
- `sensor.py`'s `async_setup_entry` reads existing + newly-added subentries,
  passes `config_subentry_id` to `async_add_entities`, and derives
  `DeviceInfo.identifiers` from the subentry's device-identifier field instead
  of `entry.entry_id`.

## Migration

Existing installations have many flat top-level entries, each its own device.
`async_migrate_entry` cannot do this migration: it receives one existing
`ConfigEntry` at a time and can only rewrite that entry's own data/version —
there is no mechanism for an entry to dissolve itself into a differently-
structured entry elsewhere. Verified against Home Assistant's own
`kitchen_sink` reference integration, which demonstrates the actual supported
pattern for this kind of structural change: a one-time reconciliation run
from `async_setup` (the module-level hook that runs once when the integration
domain loads, before any per-entry `async_setup_entry` calls) instead.

On first load after the update, `async_setup` detects any legacy flat
top-level entries, creates the singleton root entry once
(`hass.config_entries.async_add(...)`), converts each legacy entry's data
into a `ConfigSubentry` and attaches it to the root
(`hass.config_entries.async_add_subentry(...)`), then removes the now-empty
legacy entry (`hass.config_entries.async_remove(...)`). **The migration only
ever changes config-entry structure, never `unique_id`, `entity_id`, or
device identifiers**, so recorder history is unaffected. A fresh installation
(no existing entries) skips reconciliation and creates the root entry
directly in the new shape.

**Failure handling:** reconciliation converts one legacy entry at a time —
create its subentry on the root, confirm success, only then remove the
legacy entry. If it fails partway through the batch, already-converted
entries stay converted (harmless — they're already in their new, correct
form) and not-yet-converted entries are simply retried on the next
`async_setup` (unaffected, since they're untouched flat entries until their
own turn). No entry is ever left half-converted.

**Orphaned device references:** if a user deletes a device that another
subentry's stored identifier still points to, Home Assistant simply creates a
new device with that identifier on the next reload — no crash, no data loss,
just a re-appeared device.

## Testing

- **Unit tests:** the migration function in isolation — old flat-entry
  structure in, correct subentry structure out, with `unique_id` verified
  unchanged. No live Home Assistant instance needed.
- **E2E tests:** (1) add a second sensor to an already-existing device via the
  subentry "add" flow and confirm both sensors show under one device; (2) load
  a pre-migration-shaped config (simulating an upgrade) and confirm entity IDs
  are stable after migration runs.

## Out of Scope

- **Custom naming** (device/sensor display names, system-wide naming
  templates) — sub-project 3.
- **Sidebar panel write access** for managing bundling — sub-project 4.
- **Configurable update/polling modes** (real-time / fixed-interval /
  custom-interval) and **configurable per-entity source-failure behavior**
  (fail-soft-to-0 vs. fail-closed-to-unavailable) — raised during this
  sub-project's brainstorming but explicitly out of scope; to become their
  own future sub-project(s), sequenced after sub-projects 1–4.
