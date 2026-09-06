# Device-mapping UI re-enablement design

## Scope and verified runtime

This document is the implementation plan for re-enabling non-destructive device
mapping in `abstractor` (GH #18). It intentionally does not change production
code or tests.

The installed environment was inspected directly:

| Item | Observed value |
| --- | --- |
| Home Assistant package | `2026.2.3` |
| `homeassistant.__file__` | `/home/hermes/.local/lib/python3.13/site-packages/homeassistant/__init__.py` |
| `homeassistant.const.MAJOR_VERSION`, `MINOR_VERSION` | `2026`, `2` |
| `pytest-homeassistant-custom-component` | `0.13.316` |
| Plugin's HA requirement | `homeassistant==2026.2.3` |

The installed registry APIs are:

```text
DeviceRegistry.async_get_or_create(
    *, config_entry_id, config_subentry_id=..., ..., identifiers=..., ...
)

DeviceRegistry.async_update_device(
    device_id, *, add_config_entry_id=..., add_config_subentry_id=...,
    remove_config_entry_id=..., remove_config_subentry_id=..., ...
)

EntityRegistry.async_update_entity(
    entity_id, *, config_entry_id=..., config_subentry_id=...,
    device_id=..., ...
)
```

The installed device registry stores ownership in the union-style
`config_entries`/`config_entries_subentries` fields and supports the
`add_config_*`/`remove_config_*` names. The entity registry has the required
`device_id` argument. HA 2026.8's single-owner behavior is nevertheless the
compatibility target: mapping code must not assume that adding a second
subentry to an existing device is harmless.

## Decision

**Context:** HA's device registry changed from a multi-owner association to a
single-owner association, and an implicit device collision can synchronously
delete another subentry's entity row and its recorder history.

**Choice:** Re-add the mapping controls, but make every mapping operation an
explicit registry transaction. Detach is supported. A target owned by another
subentry is rejected on single-owner HA and only uses the old union operation
when the runtime demonstrably supports the union ownership model. Same-owner
targets are always allowed.

**Alternatives rejected:**

* Calling `async_get_or_create` with a target identifier and relying on HA to
  merge it was rejected because it is the GH #18 destructive path.
* Always allowing cross-subentry bundling was rejected because it is unsafe on
  HA 2026.8+.
* Always rejecting all target devices was rejected because it would unnecessarily
  remove safe same-owner moves and the old union-compatible behavior.

**Consequences:** The implementation has one small registry-reparenting helper
and a fail-loud UI error. On new HA, a stale ownership link may intentionally
remain after a detach if removing it would make HA delete another entity; this
is preferable to deleting user data and is logged for later cleanup.

## Config-flow UI

### Fields

Add both fields to `_schema()` for both create (`user`) and reconfigure steps:

```python
vol.Optional(CONF_TARGET_DEVICE_ID): selector.DeviceSelector(
    selector.DeviceSelectorConfig(integration=DOMAIN)
),
vol.Optional(CONF_CREATE_NEW_DEVICE, default=False): selector.BooleanSelector(),
```

The integration filter limits choices to Abstractor devices. The target is an
HA opaque `device_id`; it must never be persisted. The checkbox is the explicit
detach signal. Keep the existing source and legacy-ID behavior unchanged.

On reconfigure, build suggested values from the current subentry, then add the
mapping-specific values before calling
`add_suggested_values_to_schema`:

* `CONF_TARGET_DEVICE_ID`: resolve the current `CONF_DEVICE_GROUP_ID` as
  `(DOMAIN, group_id)`. If no group is stored, resolve the current own device
  as `(DOMAIN, current_subentry_id)`.
* `CONF_CREATE_NEW_DEVICE`: `False` by default. It must not be inferred from
  absence of a group; absence means “carry forward/no mapping change”.

The target selector's suggested value is only a UI value. `_normalize()` must
preserve the existing group field for a same-device/no-op submission and must
not turn an ungrouped sensor into an explicit group of its own subentry ID.

Retain the current normalization priority:

1. An explicitly submitted target is resolved to a device/group operation.
2. `CONF_CREATE_NEW_DEVICE=True` with no target means detach.
3. Neither mapping control means carry forward the existing group unchanged.

If both controls are submitted, target wins only when it passes the ownership
safety check; otherwise return the mapping conflict form error and do not write
the subentry.

### Translations

Add the same entries to `strings.json` and `translations/en.json`, under both
`config_subentries.sensor.step.user` and `.reconfigure`:

```json
"target_device_id": "Target device",
"create_new_device": "Create a separate device"
```

Use these descriptions in both files (the reconfigure description may mention
that it is a move):

```json
"target_device_id": "Add this sensor to an existing Abstractor device.",
"create_new_device": "Detach this sensor from its current device and create a separate device."
```

Add the same fail-loud error under each step's `error` object:

```json
"device_mapping_conflict": "This device is owned by another Abstractor sensor. Bundling is blocked because Home Assistant could delete that sensor and its recorder history. Choose a device owned by this sensor or create a separate device."
```

The two JSON files must remain byte-for-byte equivalent in their corresponding
translation structure; the existing CI synchronization check is the gate.

## Registry transaction design

Implement a focused helper (in `config_flow.py`, or a small registry helper
module if the implementation needs to be shared) that receives the root entry,
current subentry, current entity registry row, and requested mapping. It must
run on the HA event-loop thread and be called before the subentry update causes
platform/entity reconciliation.

First resolve the target device and inspect its Abstractor ownership. Never
identify ownership from an identifier alone: inspect
`device.config_entries_subentries[root_entry.entry_id]` and distinguish the
current subentry from a different subentry.

### Runtime compatibility gate

Use a small feature-detection function, not an upper HA version pin:

* Detect the ownership model from the registry object. A runtime exposing the
  new singular owner fields (`config_entry_id`/`config_subentry_id`) is treated
  as single-owner. A runtime exposing only the installed union fields is treated
  as union-compatible.
* Detect registry keyword names once with `inspect.signature`. Prefer the
  currently verified `add_config_entry_id`/`add_config_subentry_id` and
  `remove_config_entry_id`/`remove_config_subentry_id`; if a supported HA API
  exposes the `new_config_*` form instead, adapt in this helper. Do not scatter
  version checks through the flow.
* Require `device_id` in `EntityRegistry.async_update_entity`. If it is absent,
  reject the mapping with the same fail-loud error because no safe reparenting
  operation is possible.

Unknown ownership/API shapes fail closed. The helper must not call
`async_get_or_create` against a target before the safety decision.

### (a) Detach

Requested state: `CONF_CREATE_NEW_DEVICE=True`, no target.

1. Resolve or create the destination device using identifier `(DOMAIN,
   current_subentry_id)`, `config_entry_id=root_entry.entry_id`, and
   `config_subentry_id=current_subentry_id`.
2. Locate this sensor's entity row by its stable unique ID/entity ID.
3. Call `entity_registry.async_update_entity(entity_id, device_id=new_device.id)`
   **before** removing any ownership from the old device. This is the critical
   operation that preserves the entity row and recorder history.
4. On union HA, remove only the current subentry link from the old device with
   `async_update_device(old.id, remove_config_entry_id=root_id,
   remove_config_subentry_id=current_subentry_id)`.
5. On single-owner HA, remove the old link only when no other entity rows are
   attached to the old device. If other rows exist, leave the old ownership link
   in place and log a warning: removing it would synchronously invoke the HA
   entity-registry listener and delete those rows. The current sensor has still
   left the old device because its entity row now points to the new device.

Thus, on old HA, dropping the group link is sufficient after moving this entity;
on new HA, explicitly moving this entity is mandatory, and dropping the old
link is conditional. Never drop a link first. Do not bulk-move other entities
as part of a user detach: their ownership/data may belong to another
subentry, and the safe fallback is to preserve the old link rather than risk a
destructive listener callback.

### (b) Target owned by a different subentry

Resolve the target device's Abstractor group identifier and inspect ownership
before any mutation.

* **Single-owner runtime:** return the form with
  `errors={"base": "device_mapping_conflict"}`. Do not call
  `async_get_or_create`, `async_update_device`, `async_update_entity`, or write
  updated subentry data. The translated error explicitly explains the possible
  entity/history deletion.
* **Union-compatible runtime:** perform an explicit, ordered move:
  1. Add the current root/subentry link to the target with
     `async_update_device(target.id, add_config_entry_id=root_id,
     add_config_subentry_id=current_subentry_id)`.
  2. Move this entity row with
     `async_update_entity(entity_id, device_id=target.id)`.
  3. Remove the current subentry link from the old device, only after step 2.
     Other subentry links remain untouched.

The subentry data is committed only after this transaction succeeds. If any
registry operation raises, return a form error and leave both registry and
subentry data unchanged as far as the HA API permits; log the exception with
`_LOGGER.error` using `%s` arguments.

### (c) Same-owner target and no-op

If the target device is already owned by the current subentry, allow the
operation. If the entity already has that `device_id`, do nothing to the
registries and only persist ordinary sensor changes. If the current subentry
owns both source and target devices, use the same safe sequence as a move:

1. Add/verify the current subentry ownership on the target.
2. Update this entity's `device_id` to the target.
3. Remove the current subentry link from the old device only after step 2 and
   only if no entity for the current subentry still uses it.

This path is safe on both ownership models because no other subentry is being
re-parented or displaced. A selected target that resolves to the current
ungrouped device `(DOMAIN, subentry_id)` is a no-op and must preserve the
absence of `CONF_DEVICE_GROUP_ID` in stored data.

## Flow integration order

The current `_normalize()` should remain a pure data-shaping operation for
source lists, legacy IDs, and the requested mapping intent. Add a separate
validation/registry step in both create and reconfigure handlers:

1. Validate source entities.
2. Resolve mapping intent and perform the ownership safety check.
3. Execute the ordered registry transaction only for a real move/detach.
4. Normalize and persist data, removing UI-only target/checkbox keys.

For a new subentry, there is no existing entity row: create the subentry data,
then the normal entity setup creates the entity on the requested safe device.
For reconfigure, the existing entity row must be moved explicitly before the
subentry update/reload can remove its old device association. Keep the current
feature detection for `_get_entry()` versus `_get_reconfigure_entry()`.

## Requirements files

Pin the test plugin to the version verified in this environment:

```text
pytest-homeassistant-custom-component==0.13.316
```

That plugin pins `homeassistant==2026.2.3`, which is above the required
`2025.3` floor and fixes the CI import mismatch. Change
`requirements.txt` from `homeassistant>=2025.1` to `homeassistant>=2025.3`.
Do not lower the floor and do not add an upper bound: production code retains
the dual `_get_entry`/`_get_reconfigure_entry` detection and the registry API
feature detection described above.

## Files to change during implementation

* `custom_components/abstractor/config_flow.py`: selectors, suggested values,
  mapping safety/transaction helper, conflict error handling.
* `custom_components/abstractor/strings.json`: fields/descriptions/errors for
  both subentry steps.
* `custom_components/abstractor/translations/en.json`: exact synchronized copy
  of the same translation additions.
* `requirements.txt`: raise the development reference floor to `>=2025.3`.
* `requirements_test.txt`: pin
  `pytest-homeassistant-custom-component==0.13.316`.
* `tests/test_config_flow.py`: tests listed below.

No change is required to `sensor.py`'s stable unique-ID derivation or its
`DeviceInfo` identifier convention.

## Test plan

Update `tests/test_config_flow.py` as follows. Tests must assert registry rows
and entity rows, not only returned flow data.

1. **Create schema:** assert both mapping fields are present; assert the target
   uses `DeviceSelector` filtered to `DOMAIN`, and the checkbox defaults false.
2. **Reconfigure schema:** assert both fields are present and the target is
   prefilled with the current device ID; assert detach is prefilled false.
3. **Detach:** create two subentries/entities on a grouped device, detach one,
   then assert its entity row points to a new `(DOMAIN, subentry_id)` device,
   the other entity row still exists with the same entity ID/unique ID, and its
   recorder identity is not recreated. Run the assertion against the current
   HA fixture and a union-model registry fixture/helper.
4. **Safe bundle:** target a device already owned by the same subentry (and a
   same-owner re-point between two devices); assert the entity moves and no
   other row changes.
5. **Destructive bundle:** target a device owned by a different subentry under
   a single-owner fixture; assert a form with
   `device_mapping_conflict`, no subentry data change, no device ownership
   change, and both entity rows still present.
6. **Union bundle:** under the union-compatible fixture, assert the ordered
   add-link, entity move, remove-old-link behavior and preservation of the
   other entity.
7. **Carry-forward:** reconfigure without either mapping control and assert
   `CONF_DEVICE_GROUP_ID` remains unchanged (the existing regression test stays).
8. **Legacy unique ID:** retain the existing pinned-ID and first-time-ID tests;
   mapping fields must not alter the legacy ID or unique ID.
9. **Invalid/unknown target:** assert a form error and zero registry mutation
   when the selected device does not resolve to an Abstractor identifier or
   the registry API lacks `device_id` support.
10. **Existing assertions to update:** the options-flow assertions around
    current lines 584–586 must no longer claim the mapping fields are absent;
    replace them with assertions that they are absent from the *options* flow
    but present in subentry schemas. Restore/adapt the removed
    `test_subentry_reconfigure_prefills_target_device` test and remove its GH#18
    workaround comment. Direct `_normalize` tests should additionally assert
    that UI-only mapping keys are not persisted.

These cases cover every new branch in the mapping helper and preserve the
existing source-required, carry-forward, and legacy identity coverage needed
for 100% `config_flow.py` coverage. After implementation, run the full test
suite, coverage, Ruff, mypy, and Hassfest; this design task itself intentionally
does not run or modify production tests.
