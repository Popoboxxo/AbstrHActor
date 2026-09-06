# Code Review — Non-destructive Device Mapping (feat/device-mapping-ui)

**Review ID:** CR-DEVMAP-20260906  
**Reviewer:** code-reviewer (AbstrHActor)  
**Scope:** Full diff on `feat/device-mapping-ui` — `config_flow.py`, i18n, tests, requirements, design doc.  
**Runtime verified:** Home Assistant 2026.2.3 (union model), pytest-homeassistant-custom-component 0.13.316  
**Floor target:** HA >= 2025.3  

---

## Verdict

**APPROVED_WITH_RECOMMENDATIONS**

No blockers. The critical safety invariant (entity row moved before ownership link dropped) holds on every path. Feature detection is correct and fail-closed. The 2025.3 floor is safe for all APIs used. Test coverage is comprehensive.

Minor recommendations: DRY opportunity in entity-row lookup, remove unnecessary dummy `DeviceEntry` instantiation, and a pre-existing `_normalize` quirk for single-source-via-multi-select.

---

## Blast Radius

| Level | Criterion |
|-------|-----------|
| **SIGNIFICANT (3)** | >5 files, public UI schema changes, backwards-compatible but widespread test additions. No breaking changes to persisted data. |

**Changed files:**
- `custom_components/abstractor/config_flow.py` (+738 lines)
- `custom_components/abstractor/strings.json`
- `custom_components/abstractor/translations/en.json`
- `requirements.txt`
- `requirements_test.txt`
- `tests/test_config_flow.py` (+1,961 lines)
- `docs/device-mapping-ui-design.md` (new)

**Cross-file impact:**
- `sensor.py` — unchanged; unique-id derivation and `DeviceInfo` identifier convention are untouched. `_sensor_unique_id` correctly mirrors `sensor.py` logic (legacy-id-wins, single-source MVP format, multi-source sorted join).
- `const.py` — unchanged; new constants (`CONF_DEVICE_NAME`, `CONF_DEVICE_MANUFACTURER`, etc.) already existed.
- `manifest.json` — unchanged; recommend adding `"homeassistant": "2025.3.0"` to match the new floor.

---

## Quality Rating

**B** — Good, minor SOLID/DRY violations, blast moderate/significant.

- **S** SRP: Config flow now mixes UI orchestration with registry transactions. Acceptable for a HA custom integration of this size, but the registry helpers are already extracted.
- **O** OCP: Feature-detection design (`_registry_capabilities`) avoids version pins and scattered conditionals. Extensible to future kwarg renames.
- **L** LSP: No subtype issues.
- **I** ISP: `RegistryCapabilities` dataclass is lean and purpose-built.
- **D** DIP: Uses HA registry abstractions directly; no tighter coupling than necessary.
- **DRY:** Moderate duplication in entity-row lookup between `_detach_to_own_device` and `_apply_target_mapping`.
- **KISS:** Complex but justified by HA's evolving registry API.
- **YAGNI:** `AbstractorOptionsFlow` (polling/Influx/device-name options) is on the branch but not part of the device-mapping feature itself. It does not interfere.

---

## Findings (prioritized)

### 1. MAJOR — DRY: duplicated entity-row lookup in detach vs. target move
**Files:** `config_flow.py` lines 617–623, 726–731  
**Issue:** Both `_detach_to_own_device` and `_apply_target_mapping` contain the same block:
```python
unique_id = _sensor_unique_id(current_data)
entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
old_device_id = None
if entity_id is not None:
    entity = entity_registry.async_get(entity_id)
    if entity is not None:
        old_device_id = entity.device_id
```
**Suggestion:** Extract a private `_locate_entity_row(current_data) -> tuple[str | None, str | None]` returning `(entity_id, old_device_id)`. Reduces duplication and makes future unique-id format changes edit-in-one-place.

### 2. MAJOR — Unnecessary `dr.DeviceEntry` instantiation in capability probe
**File:** `config_flow.py` line 157  
**Issue:** `_registry_capabilities` instantiates `dummy = dr.DeviceEntry(id="__cap_probe__")` solely to pass it to `_detect_ownership_model`, but that function ignores its `device` parameter and inspects `dr.DeviceEntry` (the class) via `hasattr`. The dummy creation is dead weight and risks a `TypeError` if future HA versions add required constructor fields.
**Suggestion:** Remove `dummy` and call `_detect_ownership_model` with `None`, or change `_detect_ownership_model` to accept `type[dr.DeviceEntry]` and inspect the class directly.

### 3. MINOR — Pre-existing `_normalize` drops single-source submitted via multi-select
**File:** `config_flow.py` lines 901–904  
**Issue:** If a user submits `CONF_SOURCE_ENTITY_IDS: ["sensor.a"]` (exactly one source in the multi-select field), `_normalize` pops `CONF_SOURCE_ENTITY_IDS` and does **not** populate `CONF_SOURCE_ENTITY_ID`. The subentry data ends up with no source key at all. `sensor.py` then derives `unique_id = f"abstractor_{device_type}_"` (empty join), which is stable but not meaningful. This is a pre-existing quirk, not introduced by the mapping feature, but it lives in the same function under review.
**Suggestion:** In the `else` branch (`len(sources) == 1`), set `data[CONF_SOURCE_ENTITY_ID] = sources[0]` after popping `CONF_SOURCE_ENTITY_IDS`. This keeps the single-source MVP id format consistent.

### 4. MINOR — `manifest.json` lacks `"homeassistant"` version key
**File:** `custom_components/abstractor/manifest.json`  
**Issue:** The integration now depends on subentry APIs (`ConfigSubentryFlow`, `_get_reconfigure_entry` / `_get_entry`) that require HA >= 2025.3. `requirements.txt` reflects this, but `manifest.json` does not. HACS Action / Hassfest may flag a mismatch.
**Suggestion:** Add `"homeassistant": "2025.3.0"` to `manifest.json`.

### 5. NIT — Typo in test name
**File:** `tests/test_config_flow.py` line 1412  
**Issue:** `test_subentry_reconfigure_same_owner_reponts_between_two_devices` — "reponts" should be "repoints".
**Suggestion:** Rename test.

---

## Focus-Point Answers

### 1. Correctness of registry-ordering invariant
**Verdict: HOLDS ON EVERY PATH.**

- **Detach (`_detach_to_own_device`):** The entity row is moved via `async_update_entity(entity_id, device_id=new_device.id)` (line 633) **before** `_remove_owner_link` is called (line 671). On single-owner HA, the old link is only dropped after verifying `remaining == []` (line 656).
- **Target move (`_apply_target_mapping`):** The new ownership link is added first (lines 748–759), then the entity row is moved (line 763), then `_drop_old_link` runs last (line 768). The entity row is never dropped before it is reparented.
- **Partial-transaction risk:** If `async_update_entity` raises after `_add_owner_link` succeeded, the new link remains but the entity stays on the old device. This is a benign partial state (not destructive) and is acknowledged in the design doc.

### 2. Feature-detection robustness
**Verdict: CORRECT AND FAIL-CLOSED.**

- `_detect_ownership_model` inspects `hasattr(dr.DeviceEntry, "config_entry_id")` and `hasattr(dr.DeviceEntry, "config_subentry_id")`. On the installed 2026.2.3 runtime these are absent → "union". On 2026.8+ they are present → "single-owner". Correct.
- Unknown API shapes (e.g. missing `device_id` kwarg on `async_update_entity`) are caught by the early `capabilities.entity_update_has_device_id` gate (line 523) and return `device_mapping_conflict` before any mutation.
- If `target_device.config_entries_subentries` disappears in a future HA version, the access inside `_apply_target_mapping` raises `AttributeError`, is caught by the broad `except Exception` (line 775), logs the error, and returns False → conflict error. Fail-closed.

### 3. `device_mapping_conflict` fail-loud path
**Verdict: CORRECTLY REACHED ONLY WHEN UNSAFE.**

- **Union runtime + cross-subentry target:** The guard `is_cross_subentry and not capabilities.union` (line 711) is **False** (union is True), so the path proceeds to the safe ordered move. The error is **not** reached.
- **Single-owner runtime + cross-subentry target:** The guard is **True** → returns False → `_validate_device_mapping` returns `{"base": "device_mapping_conflict"}`. Zero registry mutation. Verified by tests `test_subentry_create_with_cross_subentry_target_rejected_on_single_owner` and `test_subentry_reconfigure_cross_subentry_bundle_rejected_on_single_owner`.
- **Missing registry kwargs:** `_add_owner_link` / `_remove_owner_link` raise `RuntimeError` when expected kwargs are absent; the `except Exception` block catches this and surfaces the same conflict error. Fail-closed.

### 4. Blast radius on schema, normalize, flow handlers, `_sensor_unique_id`
**Verdict: NO REGRESSION.**

- `_schema()` re-adds optional `CONF_TARGET_DEVICE_ID` and `CONF_CREATE_NEW_DEVICE` for both create and reconfigure. They are UI-only and popped by `_normalize`.
- `_normalize()` carry-forward logic (lines 937–938) preserves existing `CONF_DEVICE_GROUP_ID` when neither mapping control is submitted. Verified by `test_subentry_reconfigure_preserves_device_group_when_unset`.
- Legacy unique id pinning is unchanged: `_normalize` carries `CONF_LEGACY_UNIQUE_ID` forward unconditionally if already set (lines 919–926). Verified by existing tests.
- Source deduplication is unchanged.
- `_sensor_unique_id` derivation matches `sensor.py` exactly:
  - Legacy wins.
  - Single source: `abstractor_{source}_{type}`.
  - Multi-source: `abstractor_{type}_{sorted_join}`.
  - Empty sources filtered.

### 5. DRY/SOLID, dynamic splat, naming
**Verdict: ACCEPTABLE WITH RECOMMENDATIONS.**

- **DRY:** Finding #1 covers the duplicated entity-row lookup. The dynamic `**{kwarg: value}` splat in `_add_owner_link` / `_remove_owner_link` is a necessary and accepted trade-off for runtime kwarg detection (noted in design doc).
- **Naming:** `_drop_old_link` vs `_remove_owner_link` is clear enough (conditional wrapper vs. raw union operation). `_validate_device_mapping` is a bit of a misnomer because it also **executes** the registry transaction, not just validation. A name like `_execute_safe_device_mapping` would be more honest, but the docstring clarifies the dual role.

### 6. Conventions
**Verdict: FOLLOWS PROJECT CONVENTIONS.**

- PEP8 / Ruff formatting observed.
- `_LOGGER` calls use `%s` style, no f-strings (e.g. line 526, 549, 557).
- English throughout.
- Docstrings are high-quality and explain rationale (e.g. lines 84–95, 496–512).
- `has_entity_name = True` and stable `unique_id` invariants are preserved in `sensor.py`.

### 7. HA 2025.3 floor compatibility
**Verdict: SAFE.**

| API / Symbol | 2025.3.0 status | Notes |
|---|---|---|
| `selector.DeviceSelectorConfig(integration=...)` | **Present** | Verified in `selector.py` tag 2025.3.0 |
| `selector.DeviceSelector` | **Present** | Long-standing |
| `er.EntityRegistry.async_update_entity(device_id=...)` | **Present** | `device_id` kwarg exists in 2025.3.0 source |
| `er.async_get_entity_id(domain, platform, unique_id)` | **Present** | Long-standing |
| `dr.DeviceRegistry.async_get_device(identifiers=...)` | **Present** | Long-standing |
| `dr.DeviceRegistry.async_get_or_create(config_entry_id, config_subentry_id, identifiers)` | **Present** | `config_subentry_id` added with subentries |
| `dr.DeviceRegistry.async_update_device(add_config_entry_id, add_config_subentry_id, remove_config_entry_id, remove_config_subentry_id)` | **Present** | Union-style kwargs in 2025.3.0 |
| `ConfigSubentryFlow._get_reconfigure_entry()` | **Present** | Renamed to `_get_entry` post-2025.3.24; code features-detects the rename correctly |

No API used by the mapping path is missing at the 2025.3 floor.

---

## Blockers

None.

## Recommendations Summary

1. Extract `_locate_entity_row` to DRY the duplicated entity lookup (major).
2. Remove the unnecessary `dr.DeviceEntry(id="__cap_probe__")` instantiation in `_registry_capabilities` (major).
3. Fix the pre-existing `_normalize` single-source-via-multi-select quirk by writing `CONF_SOURCE_ENTITY_ID` when `len(sources) == 1` (minor).
4. Add `"homeassistant": "2025.3.0"` to `manifest.json` (minor).
5. Rename `test_subentry_reconfigure_same_owner_reponts_between_two_devices` (nit).

## Next Step

Merge is safe. Address recommendations in a follow-up commit or defer to the next refactor cycle.
