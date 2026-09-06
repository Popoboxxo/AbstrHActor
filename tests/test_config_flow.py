"""Test the Abstractor config flow."""

import inspect
import re
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abstractor.config_flow import (
    AbstractorConfigFlow,
    AbstractorOptionsFlow,
    AbstractorSensorSubentryFlowHandler,
    RegistryCapabilities,
    _detect_ownership_model,
    _device_group_id_for_device,
    _registry_capabilities,
    _sensor_unique_id,
)
from custom_components.abstractor.const import (
    CONF_CREATE_NEW_DEVICE,
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_INFLUX_BUCKET,
    CONF_INFLUX_HOST,
    CONF_INFLUX_ORG,
    CONF_INFLUX_TOKEN,
    CONF_LEGACY_UNIQUE_ID,
    CONF_POLL_INTERVAL,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    CONF_SPIKE_FILTER,
    CONF_TARGET_DEVICE_ID,
    DEFAULT_DEVICE_MANUFACTURER,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_DEVICE_NAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    POLL_INTERVAL_MAX,
    POLL_INTERVAL_MIN,
    POLL_INTERVAL_PRESETS,
)


async def test_form(hass: HomeAssistant) -> None:
    """The top-level flow only creates the singleton root entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"

    with patch(
        "custom_components.abstractor.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "Abstractor"
    assert result2["data"] == {}
    assert len(mock_setup_entry.mock_calls) == 1


async def test_subentry_create_form(hass: HomeAssistant) -> None:
    """A subentry flow creates a sensor under the root entry."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == "form"

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.test_power",
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "Abstract power"
    subentries = list(root_entry.subentries.values())
    assert len(subentries) == 1
    assert subentries[0].data[CONF_DEVICE_TYPE] == "power"
    assert subentries[0].data[CONF_SOURCE_ENTITY_ID] == "sensor.test_power"


async def test_subentry_create_auto_generates_stable_unique_id(hass: HomeAssistant) -> None:
    """A newly created subentry gets a stable identity without the user
    typing anything into the optional 'legacy unique id' field (GH#19)."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.test_power",
        },
    )
    await hass.async_block_till_done()

    subentry = next(iter(root_entry.subentries.values()))
    stable_id = subentry.data[CONF_LEGACY_UNIQUE_ID]
    assert re.match(r"^abstractor_[0-9a-f]{32}$", stable_id)


async def test_subentry_reconfigure_keeps_auto_generated_id_after_source_swap(
    hass: HomeAssistant,
) -> None:
    """The whole point (GH#19): swapping a sensor's source hardware via
    reconfigure must NOT change its unique_id, because a stable id was
    already auto-generated at creation time."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    create_result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )
    await hass.config_entries.subentries.async_configure(
        create_result["flow_id"],
        {CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.old_plug"},
    )
    await hass.async_block_till_done()
    subentry_id, subentry = next(iter(root_entry.subentries.items()))
    original_id = subentry.data[CONF_LEGACY_UNIQUE_ID]

    reconfigure_result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": subentry_id,
        },
    )
    await hass.config_entries.subentries.async_configure(
        reconfigure_result["flow_id"],
        {CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.new_plug"},
    )
    await hass.async_block_till_done()

    updated_subentry = root_entry.subentries[subentry_id]
    assert updated_subentry.data[CONF_SOURCE_ENTITY_ID] == "sensor.new_plug"
    assert updated_subentry.data[CONF_LEGACY_UNIQUE_ID] == original_id


async def test_device_group_id_for_device_found(hass: HomeAssistant) -> None:
    """Resolves the (DOMAIN, X) identifier's X for a device registered under it."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    device_reg = dr.async_get(hass)
    device = device_reg.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        identifiers={(DOMAIN, "existing-group")},
    )

    assert _device_group_id_for_device(hass, device.id) == "existing-group"


async def test_device_group_id_for_device_no_domain_identifier(
    hass: HomeAssistant,
) -> None:
    """Returns None when the device exists but has no DOMAIN identifier."""
    other_entry = MockConfigEntry(domain="other_domain", data={})
    other_entry.add_to_hass(hass)

    device_reg = dr.async_get(hass)
    device = device_reg.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={("other_domain", "not-abstractor")},
    )

    assert _device_group_id_for_device(hass, device.id) is None


async def test_device_group_id_for_device_not_found(hass: HomeAssistant) -> None:
    """Returns None when the device_id does not resolve in the registry at all."""
    assert _device_group_id_for_device(hass, "nonexistent-device-id") is None


async def test_subentry_create_form_requires_source(hass: HomeAssistant) -> None:
    """Submitting without any source entity re-shows the form with an error."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {CONF_DEVICE_TYPE: "power"},
    )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "source_required"}
    assert len(root_entry.subentries) == 0


async def test_subentry_create_form_multi_source_dedup(hass: HomeAssistant) -> None:
    """Multiple source entities are deduplicated and sorted into CONF_SOURCE_ENTITY_IDS."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_IDS: [
                "sensor.b_power",
                "sensor.a_power",
                "sensor.a_power",
            ],
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    subentries = list(root_entry.subentries.values())
    assert len(subentries) == 1
    assert subentries[0].data[CONF_SOURCE_ENTITY_IDS] == [
        "sensor.a_power",
        "sensor.b_power",
    ]


async def test_subentry_create_form_legacy_unique_id(hass: HomeAssistant) -> None:
    """A legacy unique id supplied in the form ends up in the subentry data."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.test_power",
            CONF_LEGACY_UNIQUE_ID: "old_unique_id_123",
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    subentries = list(root_entry.subentries.values())
    assert len(subentries) == 1
    assert subentries[0].data[CONF_LEGACY_UNIQUE_ID] == "old_unique_id_123"


# Non-destructive device mapping (GH#18): CONF_TARGET_DEVICE_ID and
# CONF_CREATE_NEW_DEVICE are UI-only fields of the SUBENTRY schema (create and
# reconfigure). _validate_device_mapping turns them into an explicit, safe
# registry transaction before any data write, and _normalize strips them so
# they are never persisted — CONF_DEVICE_GROUP_ID alone identifies a device in
# stored data. The tests below drive _normalize directly for its pure
# data-shaping contract; the registry/entity-row behavior is covered by the
# full-flow mapping tests further down.
async def test_normalize_resolves_target_device_id_to_group_id(
    hass: HomeAssistant,
) -> None:
    """A submitted CONF_TARGET_DEVICE_ID resolves to this integration's own
    group id."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    device_reg = dr.async_get(hass)
    device = device_reg.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        identifiers={(DOMAIN, "existing-group")},
    )

    flow = AbstractorSensorSubentryFlowHandler()
    flow.hass = hass
    data = flow._normalize(
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.test_power",
            CONF_TARGET_DEVICE_ID: device.id,
        },
        ["sensor.test_power"],
    )

    assert data[CONF_DEVICE_GROUP_ID] == "existing-group"
    assert CONF_TARGET_DEVICE_ID not in data
    assert CONF_CREATE_NEW_DEVICE not in data


async def test_normalize_reconfigure_moves_device(hass: HomeAssistant) -> None:
    """A submitted CONF_TARGET_DEVICE_ID during a reconfigure moves the
    subentry onto that device's own group id."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    existing_subentry_id = "existing-subentry-id"
    device_registry = dr.async_get(hass)
    target_device = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        identifiers={(DOMAIN, existing_subentry_id)},
    )

    flow = AbstractorSensorSubentryFlowHandler()
    flow.hass = hass
    data = flow._normalize(
        {
            CONF_DEVICE_TYPE: "energy",
            CONF_SOURCE_ENTITY_ID: "sensor.b",
            CONF_TARGET_DEVICE_ID: target_device.id,
        },
        ["sensor.b"],
        current_data={CONF_DEVICE_TYPE: "energy", CONF_SOURCE_ENTITY_ID: "sensor.b"},
    )

    assert data[CONF_DEVICE_GROUP_ID] == existing_subentry_id
    assert CONF_TARGET_DEVICE_ID not in data
    assert CONF_CREATE_NEW_DEVICE not in data


async def test_normalize_target_without_domain_identifier_writes_no_group(
    hass: HomeAssistant,
) -> None:
    """A target device without a DOMAIN identifier resolves to no group id
    and the UI-only keys are still stripped."""
    other_entry = MockConfigEntry(domain="other_domain", data={})
    other_entry.add_to_hass(hass)
    foreign = dr.async_get(hass).async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={("other_domain", "not-abstractor")},
    )

    flow = AbstractorSensorSubentryFlowHandler()
    flow.hass = hass
    data = flow._normalize(
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_TARGET_DEVICE_ID: foreign.id,
            CONF_CREATE_NEW_DEVICE: True,
        },
        ["sensor.a"],
    )

    assert CONF_DEVICE_GROUP_ID not in data
    assert CONF_TARGET_DEVICE_ID not in data
    assert CONF_CREATE_NEW_DEVICE not in data


async def test_subentry_reconfigure_preserves_device_group_when_unset(
    hass: HomeAssistant,
) -> None:
    """Reconfiguring a bundled sensor without touching the device selector
    must NOT silently un-bundle it from its device (regression for the
    blocker where _normalize only wrote CONF_DEVICE_GROUP_ID when
    CONF_TARGET_DEVICE_ID was present in the current form submission)."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    device_reg = dr.async_get(hass)
    device_reg.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        identifiers={(DOMAIN, "existing-group")},
    )

    grouped_subentry = ConfigSubentry(
        data={
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_DEVICE_GROUP_ID: "existing-group",
        },
        subentry_type="sensor",
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, grouped_subentry)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": grouped_subentry.subentry_id,
        },
    )
    # Only change device_type — the device selector is not touched/resubmitted.
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "energy",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"
    updated = root_entry.subentries[grouped_subentry.subentry_id]
    assert updated.data[CONF_DEVICE_GROUP_ID] == "existing-group"
    assert updated.data[CONF_DEVICE_TYPE] == "energy"


async def test_subentry_reconfigure_prefills_target_device(
    hass: HomeAssistant,
) -> None:
    """[design #2] The reconfigure form exposes both mapping fields and
    pre-fills the target selector with the subentry's current device."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    grouped_device = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        identifiers={(DOMAIN, "existing-group")},
    )
    grouped_subentry = ConfigSubentry(
        data={
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_DEVICE_GROUP_ID: "existing-group",
        },
        subentry_type="sensor",
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, grouped_subentry)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": grouped_subentry.subentry_id,
        },
    )

    assert result["type"] == "form"
    schema = result["data_schema"]
    target_marker, target_validator = _schema_field(schema, CONF_TARGET_DEVICE_ID)
    assert isinstance(target_validator, selector.DeviceSelector)
    assert target_validator.config["integration"] == DOMAIN
    assert target_marker.description == {"suggested_value": grouped_device.id}
    create_marker, create_validator = _schema_field(schema, CONF_CREATE_NEW_DEVICE)
    assert isinstance(create_validator, selector.BooleanSelector)
    assert create_marker.default() is False


async def test_subentry_reconfigure_prefills_target_device_from_own_device(
    hass: HomeAssistant,
) -> None:
    """[design #2] An ungrouped sensor pre-fills its own (DOMAIN, subentry_id)
    device as the suggested target."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    subentry = ConfigSubentry(
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.a"},
        subentry_type="sensor",
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, subentry)
    own_device = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=subentry.subentry_id,
        identifiers={(DOMAIN, subentry.subentry_id)},
    )

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": subentry.subentry_id,
        },
    )

    target_marker, _target_validator = _schema_field(
        result["data_schema"], CONF_TARGET_DEVICE_ID
    )
    assert target_marker.description == {"suggested_value": own_device.id}


async def test_subentry_reconfigure_prefills_target_device_when_device_missing(
    hass: HomeAssistant,
) -> None:
    """[design #2] A stored group whose device no longer resolves yields no
    suggested target value."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    subentry = ConfigSubentry(
        data={
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_DEVICE_GROUP_ID: "ghost-group",
        },
        subentry_type="sensor",
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, subentry)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": subentry.subentry_id,
        },
    )

    target_marker, _target_validator = _schema_field(
        result["data_schema"], CONF_TARGET_DEVICE_ID
    )
    assert target_marker.description == {"suggested_value": None}


async def test_normalize_reconfigure_detaches_with_create_new_device(
    hass: HomeAssistant,
) -> None:
    """_normalize's explicit-detach signal (CONF_CREATE_NEW_DEVICE=True, no
    target device) leaves CONF_DEVICE_GROUP_ID fully absent from the result,
    not just falsy — a regression for the round-1 fix's unintended side
    effect, which made this split impossible (per design spec line 23-24)."""
    flow = AbstractorSensorSubentryFlowHandler()
    flow.hass = hass
    data = flow._normalize(
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_CREATE_NEW_DEVICE: True,
        },
        ["sensor.a"],
        current_data={
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_DEVICE_GROUP_ID: "existing-group",
        },
    )

    assert CONF_DEVICE_GROUP_ID not in data
    assert CONF_CREATE_NEW_DEVICE not in data
    assert CONF_TARGET_DEVICE_ID not in data


async def test_subentry_reconfigure_requires_source(hass: HomeAssistant) -> None:
    """Reconfiguring without any source entity re-shows the form with an error."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    subentry = ConfigSubentry(
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.a"},
        subentry_type="sensor",
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, subentry)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": subentry.subentry_id,
        },
    )
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {CONF_DEVICE_TYPE: "power"},
    )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "source_required"}
    assert root_entry.subentries[subentry.subentry_id].data == subentry.data


async def test_subentry_reconfigure_cannot_clear_a_pinned_legacy_unique_id(
    hass: HomeAssistant,
) -> None:
    """A pinned legacy unique id survives a reconfigure that omits the field.

    Once a subentry carries CONF_LEGACY_UNIQUE_ID it IS that sensor's identity
    — set either by a YAML template migration or by the device-bundling
    reconciliation pinning the pre-migration unique_id. Reconfiguring for an
    unrelated reason (here: toggling the spike filter) must not drop it, or
    the unique_id gets re-derived from the current sources and the existing
    entity, plus its recorder history, is orphaned.
    """
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    pinned_subentry = ConfigSubentry(
        data={
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.old",
            CONF_SOURCE_ENTITY_IDS: ["sensor.new_x", "sensor.new_y"],
            CONF_LEGACY_UNIQUE_ID: "abstractor_sensor.old_power",
        },
        subentry_type="sensor",
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, pinned_subentry)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": pinned_subentry.subentry_id,
        },
    )
    # The field is not even offered any more once it is set.
    assert CONF_LEGACY_UNIQUE_ID not in [
        str(key) for key in result["data_schema"].schema
    ]

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.old",
            CONF_SOURCE_ENTITY_IDS: ["sensor.new_x", "sensor.new_y"],
            CONF_SPIKE_FILTER: True,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"
    updated = root_entry.subentries[pinned_subentry.subentry_id]
    assert updated.data[CONF_LEGACY_UNIQUE_ID] == "abstractor_sensor.old_power"
    assert updated.data[CONF_SPIKE_FILTER] is True


async def test_subentry_reconfigure_ignores_a_submitted_legacy_unique_id(
    hass: HomeAssistant,
) -> None:
    """Even a submission that bypasses the form cannot change a pinned id.

    The schema hiding the field protects the UI path; identity must not depend
    on that alone, so _normalize carries the existing value forward whatever
    arrives.
    """
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    pinned_subentry = ConfigSubentry(
        data={
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.old",
            CONF_LEGACY_UNIQUE_ID: "fridge_power_template",
        },
        subentry_type="sensor",
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, pinned_subentry)

    flow = AbstractorSensorSubentryFlowHandler()
    flow.hass = hass
    for submitted in (
        {},
        {CONF_LEGACY_UNIQUE_ID: ""},
        {CONF_LEGACY_UNIQUE_ID: "other"},
    ):
        data = flow._normalize(
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.old",
                **submitted,
            },
            ["sensor.old"],
            current_data=pinned_subentry.data,
        )
        assert data[CONF_LEGACY_UNIQUE_ID] == "fridge_power_template", submitted


async def test_subentry_reconfigure_can_set_a_first_legacy_unique_id(
    hass: HomeAssistant,
) -> None:
    """A sensor without one can still be given a legacy unique id later.

    Pinning must not turn into "nobody may ever set one": REQ-CORE-003's
    opt-in stays available for sensors that do not have one yet, it just
    becomes permanent from then on.
    """
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    subentry = ConfigSubentry(
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.a"},
        subentry_type="sensor",
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, subentry)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": subentry.subentry_id,
        },
    )
    assert CONF_LEGACY_UNIQUE_ID in [str(key) for key in result["data_schema"].schema]

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_LEGACY_UNIQUE_ID: "fridge_power_template",
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    updated = root_entry.subentries[subentry.subentry_id]
    assert updated.data[CONF_LEGACY_UNIQUE_ID] == "fridge_power_template"


def _schema_field(data_schema, field_name: str) -> tuple:
    """Return (vol marker, validator) for a named field of a rendered schema."""
    for marker, validator in data_schema.schema.items():
        if marker.schema == field_name:
            return marker, validator
    raise AssertionError(f"field {field_name} not present in schema")


def _options_entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    """Create and register the singleton root entry, optionally with options."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="abstractor_root", data={}, options=options or {}
    )
    entry.add_to_hass(hass)
    return entry


async def test_async_get_options_flow_returns_options_flow() -> None:
    """The root flow hands out an AbstractorOptionsFlow for the options UI (REQ-CORE-007)."""
    flow = AbstractorConfigFlow.async_get_options_flow(MockConfigEntry())
    assert isinstance(flow, AbstractorOptionsFlow)


async def test_options_flow_renders_init_form_with_defaults(
    hass: HomeAssistant,
) -> None:
    """[REQ-CORE-007] The init step renders every option field with defaults."""
    root_entry = _options_entry(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)

    assert result["type"] == "form"
    assert result["step_id"] == "init"

    schema = result["data_schema"]
    for field in (
        CONF_POLL_INTERVAL,
        CONF_INFLUX_HOST,
        CONF_INFLUX_TOKEN,
        CONF_INFLUX_ORG,
        CONF_INFLUX_BUCKET,
        CONF_DEVICE_NAME,
        CONF_DEVICE_MANUFACTURER,
        CONF_DEVICE_MODEL,
    ):
        _schema_field(schema, field)
    # The device-mapping controls live only in the SUBENTRY schemas, never in
    # the root options flow (which is what these assertions pin). Their
    # presence in the subentry schemas is covered by
    # test_subentry_create_schema_exposes_mapping_fields and the
    # test_subentry_reconfigure_prefills_target_device tests.
    assert CONF_TARGET_DEVICE_ID not in [str(m.schema) for m in schema.schema]
    assert CONF_CREATE_NEW_DEVICE not in [str(m.schema) for m in schema.schema]

    poll_marker, poll_validator = _schema_field(schema, CONF_POLL_INTERVAL)
    assert poll_marker.default() == str(DEFAULT_POLL_INTERVAL)
    assert poll_validator.config["options"] == [
        *(str(value) for value in POLL_INTERVAL_PRESETS),
        "custom",
    ]
    assert poll_validator.config["mode"] == selector.SelectSelectorMode.DROPDOWN

    _token_marker, token_validator = _schema_field(schema, CONF_INFLUX_TOKEN)
    assert isinstance(token_validator, selector.TextSelector)
    assert token_validator.config["type"] == selector.TextSelectorType.PASSWORD

    _name_marker, name_validator = _schema_field(schema, CONF_DEVICE_NAME)
    assert isinstance(name_validator, selector.TextSelector)
    assert name_validator.config.get("type") is None
    _mf_marker, mf_validator = _schema_field(schema, CONF_DEVICE_MANUFACTURER)
    assert isinstance(mf_validator, selector.TextSelector)
    assert _mf_marker.default() == DEFAULT_DEVICE_MANUFACTURER
    _model_marker, model_validator = _schema_field(schema, CONF_DEVICE_MODEL)
    assert isinstance(model_validator, selector.TextSelector)


async def test_options_flow_renders_current_preset_interval_selected(
    hass: HomeAssistant,
) -> None:
    """[REQ-CORE-007] A current preset interval is shown as its own option."""
    root_entry = _options_entry(hass, {CONF_POLL_INTERVAL: 5})

    result = await hass.config_entries.options.async_init(root_entry.entry_id)

    poll_marker, _ = _schema_field(result["data_schema"], CONF_POLL_INTERVAL)
    assert poll_marker.default() == "5"


async def test_options_flow_saves_preset_interval_and_merges_defaults(
    hass: HomeAssistant,
) -> None:
    """[REQ-CORE-007] Saving a preset persists an int interval plus the
    remaining DEFAULT_OPTIONS, without touching the singleton root's data."""
    root_entry = _options_entry(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POLL_INTERVAL: "5",
            CONF_INFLUX_HOST: "http://influx.local:8086",
            CONF_INFLUX_ORG: "energy",
            CONF_INFLUX_BUCKET: "abstractor",
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["data"][CONF_POLL_INTERVAL] == 5
    assert result2["data"][CONF_INFLUX_HOST] == "http://influx.local:8086"
    assert result2["data"][CONF_INFLUX_ORG] == "energy"
    assert result2["data"][CONF_INFLUX_BUCKET] == "abstractor"
    # The device presentation defaults are merged in for every save.
    assert result2["data"][CONF_DEVICE_MANUFACTURER] == DEFAULT_DEVICE_MANUFACTURER
    assert result2["data"][CONF_DEVICE_MODEL] == DEFAULT_DEVICE_MODEL
    assert result2["data"][CONF_DEVICE_NAME] == DEFAULT_DEVICE_NAME
    # Options go to the entry's options; the singleton root's data stays {}.
    assert root_entry.options[CONF_POLL_INTERVAL] == 5
    assert root_entry.data == {}


async def test_options_flow_custom_interval_reveals_bounded_number_field(
    hass: HomeAssistant,
) -> None:
    """[REQ-CORE-007] Choosing "custom" transitions to a Number step whose
    bounds match POLL_INTERVAL_MIN/POLL_INTERVAL_MAX."""
    root_entry = _options_entry(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: "custom"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "poll_interval"
    poll_marker, poll_validator = _schema_field(
        result2["data_schema"], CONF_POLL_INTERVAL
    )
    assert poll_marker.default() == DEFAULT_POLL_INTERVAL
    assert poll_validator.config["min"] == POLL_INTERVAL_MIN
    assert poll_validator.config["max"] == POLL_INTERVAL_MAX
    assert poll_validator.config["step"] == 1
    assert poll_validator.config["mode"] == selector.NumberSelectorMode.BOX


async def test_options_flow_custom_interval_saves_integer(
    hass: HomeAssistant,
) -> None:
    """[REQ-CORE-007] The Number step persists a plain int interval."""
    root_entry = _options_entry(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: "custom"}
    )
    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {CONF_POLL_INTERVAL: 7}
    )
    await hass.async_block_till_done()

    assert result3["type"] == "create_entry"
    assert result3["data"][CONF_POLL_INTERVAL] == 7
    assert root_entry.options[CONF_POLL_INTERVAL] == 7
    assert root_entry.data == {}


async def test_options_flow_reopen_with_custom_interval_prefills(
    hass: HomeAssistant,
) -> None:
    """[REQ-CORE-007] A non-preset current interval re-opens as "custom" and
    the Number step is pre-filled with the current value."""
    root_entry = _options_entry(hass, {CONF_POLL_INTERVAL: 7})

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    poll_marker, _ = _schema_field(result["data_schema"], CONF_POLL_INTERVAL)
    assert poll_marker.default() == "custom"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: "custom"}
    )
    assert result2["step_id"] == "poll_interval"
    poll_marker2, _ = _schema_field(result2["data_schema"], CONF_POLL_INTERVAL)
    assert poll_marker2.default() == 7

    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {CONF_POLL_INTERVAL: 7}
    )
    assert result3["data"][CONF_POLL_INTERVAL] == 7


async def test_options_flow_custom_interval_preserves_other_submitted_fields(
    hass: HomeAssistant,
) -> None:
    """[REQ-CORE-007] Fields submitted together with "custom" survive the
    two-step transition instead of being dropped on the Number step."""
    root_entry = _options_entry(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POLL_INTERVAL: "custom",
            CONF_INFLUX_HOST: "http://influx.local:8086",
            CONF_INFLUX_TOKEN: "secret-token",
            CONF_INFLUX_ORG: "energy",
            CONF_INFLUX_BUCKET: "abstractor",
            CONF_DEVICE_MANUFACTURER: "Acme Labs",
            CONF_DEVICE_MODEL: "OptiSense 3000",
        },
    )
    assert result2["step_id"] == "poll_interval"

    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {CONF_POLL_INTERVAL: 12}
    )
    await hass.async_block_till_done()

    assert result3["type"] == "create_entry"
    assert result3["data"][CONF_POLL_INTERVAL] == 12
    assert result3["data"][CONF_INFLUX_HOST] == "http://influx.local:8086"
    assert result3["data"][CONF_INFLUX_TOKEN] == "secret-token"
    assert result3["data"][CONF_INFLUX_ORG] == "energy"
    assert result3["data"][CONF_INFLUX_BUCKET] == "abstractor"
    assert result3["data"][CONF_DEVICE_MANUFACTURER] == "Acme Labs"
    assert result3["data"][CONF_DEVICE_MODEL] == "OptiSense 3000"
    assert root_entry.options[CONF_POLL_INTERVAL] == 12


async def test_options_flow_rejects_influx_host_without_scheme(hass: HomeAssistant) -> None:
    """[SEC-1] CONF_INFLUX_HOST must be rejected if it isn't http(s):// —
    a bare host/IP with no scheme is exactly the shape of an accidental (or
    malicious) internal-network SSRF target slipped into a free-text field."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POLL_INTERVAL: str(DEFAULT_POLL_INTERVAL),
            CONF_INFLUX_HOST: "169.254.169.254",
            CONF_INFLUX_TOKEN: "",
            CONF_INFLUX_ORG: "",
            CONF_INFLUX_BUCKET: "",
            CONF_DEVICE_NAME: DEFAULT_DEVICE_NAME,
            CONF_DEVICE_MANUFACTURER: DEFAULT_DEVICE_MANUFACTURER,
            CONF_DEVICE_MODEL: DEFAULT_DEVICE_MODEL,
        },
    )

    assert result2["type"] == "form"
    assert result2["errors"]["base"] == "invalid_influx_host"


async def test_options_flow_accepts_influx_host_with_https_scheme(hass: HomeAssistant) -> None:
    """A properly-schemed host is accepted, matching today's behavior."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POLL_INTERVAL: str(DEFAULT_POLL_INTERVAL),
            CONF_INFLUX_HOST: "https://influx.local:8086",
            CONF_INFLUX_TOKEN: "",
            CONF_INFLUX_ORG: "",
            CONF_INFLUX_BUCKET: "",
            CONF_DEVICE_NAME: DEFAULT_DEVICE_NAME,
            CONF_DEVICE_MANUFACTURER: DEFAULT_DEVICE_MANUFACTURER,
            CONF_DEVICE_MODEL: DEFAULT_DEVICE_MODEL,
        },
    )

    assert result2["type"] == "create_entry"
    assert result2["data"][CONF_INFLUX_HOST] == "https://influx.local:8086"


async def test_options_flow_accepts_influx_host_with_mixed_case_scheme(
    hass: HomeAssistant,
) -> None:
    """A scheme check that is case-insensitive: Http:// is accepted, not rejected."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POLL_INTERVAL: str(DEFAULT_POLL_INTERVAL),
            CONF_INFLUX_HOST: "Http://influx.local:8086",
            CONF_INFLUX_TOKEN: "",
            CONF_INFLUX_ORG: "",
            CONF_INFLUX_BUCKET: "",
            CONF_DEVICE_NAME: DEFAULT_DEVICE_NAME,
            CONF_DEVICE_MANUFACTURER: DEFAULT_DEVICE_MANUFACTURER,
            CONF_DEVICE_MODEL: DEFAULT_DEVICE_MODEL,
        },
    )

    assert result2["type"] == "create_entry"
    assert result2["data"][CONF_INFLUX_HOST] == "Http://influx.local:8086"


async def test_options_flow_accepts_empty_influx_host(hass: HomeAssistant) -> None:
    """An empty host (Influx export disabled) is not a validation error."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(root_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POLL_INTERVAL: str(DEFAULT_POLL_INTERVAL),
            CONF_INFLUX_HOST: "",
            CONF_INFLUX_TOKEN: "",
            CONF_INFLUX_ORG: "",
            CONF_INFLUX_BUCKET: "",
            CONF_DEVICE_NAME: DEFAULT_DEVICE_NAME,
            CONF_DEVICE_MANUFACTURER: DEFAULT_DEVICE_MANUFACTURER,
            CONF_DEVICE_MODEL: DEFAULT_DEVICE_MODEL,
        },
    )

    assert result2["type"] == "create_entry"


def test_subentry_flow_get_entry_falls_back_on_old_ha() -> None:
    """On HA versions before the `_get_entry` rename, the subentry flow
    resolves its config entry through `_get_reconfigure_entry` instead."""
    from unittest.mock import Mock

    from homeassistant.config_entries import ConfigSubentryFlow

    flow = AbstractorSensorSubentryFlowHandler()
    flow._get_reconfigure_entry = Mock(return_value="resolved-entry")

    # hasattr() must report the seam as absent for the fallback to trigger.
    with patch.object(
        ConfigSubentryFlow,
        "_get_entry",
        property(lambda self: (_ for _ in ()).throw(AttributeError)),
        create=True,
    ):
        assert flow._get_subentry_config_entry() == "resolved-entry"


# ---------------------------------------------------------------------------
# Non-destructive device mapping (design doc: docs/device-mapping-ui-design.md)
# ---------------------------------------------------------------------------


def _root_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create and register the singleton root entry."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    entry.add_to_hass(hass)
    return entry


def _add_sensor_subentry(
    hass: HomeAssistant,
    root_entry: MockConfigEntry,
    *,
    source_entity_id: str,
    device_type: str = "power",
    device_group_id: str | None = None,
    legacy_unique_id: str | None = None,
) -> ConfigSubentry:
    """Register a sensor subentry under the root entry."""
    data: dict[str, Any] = {
        CONF_DEVICE_TYPE: device_type,
        CONF_SOURCE_ENTITY_ID: source_entity_id,
    }
    if device_group_id is not None:
        data[CONF_DEVICE_GROUP_ID] = device_group_id
    if legacy_unique_id is not None:
        data[CONF_LEGACY_UNIQUE_ID] = legacy_unique_id
    subentry = ConfigSubentry(
        data=data,
        subentry_type="sensor",
        title=f"Abstract {device_type}",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, subentry)
    return subentry


def _register_sensor_entity(
    hass: HomeAssistant,
    root_entry: MockConfigEntry,
    *,
    unique_id: str,
    device_id: str,
    subentry_id: str,
) -> er.RegistryEntry:
    """Register the entity registry row of a sensor subentry."""
    entity_registry = er.async_get(hass)
    return entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        unique_id,
        config_entry=root_entry,
        config_subentry_id=subentry_id,
        device_id=device_id,
    )


def _capabilities_single_owner(
    *,
    new_config_entry_id: str | None = "new_config_entry_id",
    new_config_subentry_id: str | None = "new_config_subentry_id",
    entity_update_has_device_id: bool = True,
) -> RegistryCapabilities:
    """Build the single-owner (HA 2026.8+) registry shape for mocking."""
    return RegistryCapabilities(
        owv_model="single-owner",
        add_config_entry_id=None,
        add_config_subentry_id=None,
        remove_config_entry_id=None,
        remove_config_subentry_id=None,
        new_config_entry_id=new_config_entry_id,
        new_config_subentry_id=new_config_subentry_id,
        entity_update_has_device_id=entity_update_has_device_id,
    )


def _capabilities_union(
    *,
    add_config_entry_id: str | None = "add_config_entry_id",
    add_config_subentry_id: str | None = "add_config_subentry_id",
    remove_config_entry_id: str | None = "remove_config_entry_id",
    remove_config_subentry_id: str | None = "remove_config_subentry_id",
) -> RegistryCapabilities:
    """Build the union (installed 2026.2.3) registry shape for mocking."""
    return RegistryCapabilities(
        owv_model="union",
        add_config_entry_id=add_config_entry_id,
        add_config_subentry_id=add_config_subentry_id,
        remove_config_entry_id=remove_config_entry_id,
        remove_config_subentry_id=remove_config_subentry_id,
        new_config_entry_id=None,
        new_config_subentry_id=None,
        entity_update_has_device_id=True,
    )


async def _start_reconfigure(
    hass: HomeAssistant, root_entry: MockConfigEntry, subentry_id: str
) -> dict[str, Any]:
    """Start the reconfigure flow for a subentry and return the form result."""
    return await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": subentry_id,
        },
    )


def _patch_capabilities(capabilities: RegistryCapabilities) -> Any:
    """Patch the runtime capability detection to a specific registry shape."""
    return patch(
        "custom_components.abstractor.config_flow._registry_capabilities",
        return_value=capabilities,
    )


async def test_subentry_create_schema_exposes_mapping_fields(
    hass: HomeAssistant,
) -> None:
    """[design #1] The create schema exposes CONF_TARGET_DEVICE_ID as a
    DeviceSelector filtered to DOMAIN and CONF_CREATE_NEW_DEVICE defaulting
    to False."""
    root_entry = _root_entry(hass)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == "form"

    schema = result["data_schema"]
    _target_marker, target_validator = _schema_field(schema, CONF_TARGET_DEVICE_ID)
    assert isinstance(target_validator, selector.DeviceSelector)
    assert target_validator.config["integration"] == DOMAIN
    create_marker, create_validator = _schema_field(schema, CONF_CREATE_NEW_DEVICE)
    assert isinstance(create_validator, selector.BooleanSelector)
    assert create_marker.default() is False


async def test_subentry_create_with_detach_flag_is_noop(hass: HomeAssistant) -> None:
    """[design #3] A create flow with the detach checkbox set has no entity
    row to detach: the sensor is created ungrouped and no registry row is
    touched."""
    root_entry = _root_entry(hass)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_CREATE_NEW_DEVICE: True,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    subentries = list(root_entry.subentries.values())
    assert len(subentries) == 1
    assert CONF_DEVICE_GROUP_ID not in subentries[0].data
    assert CONF_CREATE_NEW_DEVICE not in subentries[0].data
    assert CONF_TARGET_DEVICE_ID not in subentries[0].data


async def test_subentry_create_with_target_owned_by_other_subentry_succeeds_on_union(
    hass: HomeAssistant,
) -> None:
    """[design #6] Creating a sensor onto a device already owned by another
    subentry is allowed on the installed union runtime: no entity row exists
    yet, so nothing can be destroyed."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)

    sub_b = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.b", device_group_id="group-b"
    )
    device_b = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_b.subentry_id,
        identifiers={(DOMAIN, "group-b")},
    )

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_TARGET_DEVICE_ID: device_b.id,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    new_subentries = [
        subentry
        for subentry in root_entry.subentries.values()
        if subentry.subentry_id != sub_b.subentry_id
    ]
    assert len(new_subentries) == 1
    assert new_subentries[0].data[CONF_DEVICE_GROUP_ID] == "group-b"
    assert CONF_TARGET_DEVICE_ID not in new_subentries[0].data
    assert CONF_CREATE_NEW_DEVICE not in new_subentries[0].data


async def test_subentry_create_with_cross_subentry_target_rejected_on_single_owner(
    hass: HomeAssistant,
) -> None:
    """[design #5] The destructive bundle is rejected at CREATE time on a
    single-owner runtime: the form re-shows with the conflict error and no
    subentry is created."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)

    sub_b = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.b", device_group_id="group-b"
    )
    device_b = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_b.subentry_id,
        identifiers={(DOMAIN, "group-b")},
    )

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )
    with _patch_capabilities(_capabilities_single_owner()):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_TARGET_DEVICE_ID: device_b.id,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "device_mapping_conflict"}
    assert len(root_entry.subentries) == 1
    assert next(iter(root_entry.subentries.values())).subentry_id == sub_b.subentry_id


async def test_subentry_reconfigure_detach_moves_entity_and_preserves_other(
    hass: HomeAssistant,
) -> None:
    """[design #3] Detaching one of two bundled sensors moves ONLY its entity
    row to a fresh (DOMAIN, subentry_id) device; the other sensor's row keeps
    its entity_id/unique_id and stays on the grouped device (GH#18
    regression)."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="shared-group"
    )
    sub_b = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.b", device_group_id="shared-group"
    )
    # A realistically bundled device is owned by BOTH subentries (the union
    # runtime records each subentry that bundled onto it).
    grouped = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "shared-group")},
    )
    device_registry.async_update_device(
        grouped.id,
        add_config_entry_id=root_entry.entry_id,
        add_config_subentry_id=sub_b.subentry_id,
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=grouped.id,
        subentry_id=sub_a.subentry_id,
    )
    entity_b = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.b_power",
        device_id=grouped.id,
        subentry_id=sub_b.subentry_id,
    )

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_CREATE_NEW_DEVICE: True,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"

    own_device = device_registry.async_get_device({(DOMAIN, sub_a.subentry_id)})
    assert own_device is not None
    moved = entity_registry.async_get(entity_a.entity_id)
    assert moved is not None
    assert moved.entity_id == entity_a.entity_id
    assert moved.unique_id == entity_a.unique_id
    assert moved.device_id == own_device.id

    other = entity_registry.async_get(entity_b.entity_id)
    assert other is not None
    assert other.entity_id == entity_b.entity_id
    assert other.unique_id == entity_b.unique_id
    assert other.device_id == grouped.id

    owners = device_registry.async_get(grouped.id).config_entries_subentries.get(
        root_entry.entry_id, ()
    )
    assert sub_a.subentry_id not in owners
    assert sub_b.subentry_id in owners

    updated = root_entry.subentries[sub_a.subentry_id].data
    assert CONF_DEVICE_GROUP_ID not in updated
    assert CONF_CREATE_NEW_DEVICE not in updated
    assert CONF_TARGET_DEVICE_ID not in updated


async def test_subentry_reconfigure_detach_on_single_owner_keeps_stale_link_when_other_rows_remain(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """[design #3] On a single-owner runtime the old ownership link is left in
    place (with a warning) when another entity row still lives on the old
    device; removing it would delete that row on such a runtime."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="shared-group"
    )
    sub_b = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.b", device_group_id="shared-group"
    )
    grouped = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "shared-group")},
    )
    device_registry.async_update_device(
        grouped.id,
        add_config_entry_id=root_entry.entry_id,
        add_config_subentry_id=sub_b.subentry_id,
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=grouped.id,
        subentry_id=sub_a.subentry_id,
    )
    _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.b_power",
        device_id=grouped.id,
        subentry_id=sub_b.subentry_id,
    )

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with _patch_capabilities(_capabilities_single_owner()):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_CREATE_NEW_DEVICE: True,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    own_device = device_registry.async_get_device({(DOMAIN, sub_a.subentry_id)})
    assert entity_registry.async_get(entity_a.entity_id).device_id == own_device.id
    owners = device_registry.async_get(grouped.id).config_entries_subentries.get(
        root_entry.entry_id, ()
    )
    assert sub_a.subentry_id in owners
    assert sub_b.subentry_id in owners
    assert "leaving the stale ownership link" in caplog.text


async def test_subentry_reconfigure_detach_on_single_owner_when_alone(
    hass: HomeAssistant,
) -> None:
    """[design #3] With no other entity row on the old device the single-owner
    detach still succeeds; the remove-link helper is a no-op on that model."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    grouped = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        identifiers={(DOMAIN, "shared-group")},
    )
    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="shared-group"
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=grouped.id,
        subentry_id=sub_a.subentry_id,
    )

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with _patch_capabilities(_capabilities_single_owner()):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_CREATE_NEW_DEVICE: True,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    own_device = device_registry.async_get_device({(DOMAIN, sub_a.subentry_id)})
    assert entity_registry.async_get(entity_a.entity_id).device_id == own_device.id


async def test_subentry_reconfigure_same_owner_target_is_noop(
    hass: HomeAssistant,
) -> None:
    """[design #4] Selecting a device already owned by this subentry while the
    entity already sits on it is a no-op: only the ordinary sensor data
    change is persisted."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="own-group"
    )
    target = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "own-group")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=target.id,
        subentry_id=sub_a.subentry_id,
    )

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_TARGET_DEVICE_ID: target.id,
            CONF_SPIKE_FILTER: True,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert entity_registry.async_get(entity_a.entity_id).device_id == target.id
    updated = root_entry.subentries[sub_a.subentry_id].data
    assert updated[CONF_DEVICE_GROUP_ID] == "own-group"
    assert updated[CONF_SPIKE_FILTER] is True
    assert CONF_TARGET_DEVICE_ID not in updated
    assert CONF_CREATE_NEW_DEVICE not in updated


async def test_subentry_reconfigure_same_owner_repoints_between_two_devices(
    hass: HomeAssistant,
) -> None:
    """[design #4] The same subentry owning both source and target devices can
    re-point its entity between them safely; only its own rows change."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    device_b = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-b")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_TARGET_DEVICE_ID: device_b.id,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert entity_registry.async_get(entity_a.entity_id).device_id == device_b.id
    # The union runtime drops the last subentry link after the entity moved
    # and removes the orphaned, empty device shell along with it.
    assert device_registry.async_get(device_a.id) is None
    owners_b = device_registry.async_get(device_b.id).config_entries_subentries.get(
        root_entry.entry_id, ()
    )
    assert sub_a.subentry_id in owners_b
    assert root_entry.subentries[sub_a.subentry_id].data[CONF_DEVICE_GROUP_ID] == (
        "group-b"
    )


async def test_subentry_reconfigure_cross_subentry_bundle_rejected_on_single_owner(
    hass: HomeAssistant,
) -> None:
    """[design #5] Bundling onto a device owned by a DIFFERENT subentry is
    rejected on a single-owner runtime: the form re-shows with
    device_mapping_conflict, no subentry data change, no ownership change,
    and both entity rows intact."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    sub_b = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.b", device_group_id="group-b"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    device_b = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_b.subentry_id,
        identifiers={(DOMAIN, "group-b")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )
    entity_b = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.b_power",
        device_id=device_b.id,
        subentry_id=sub_b.subentry_id,
    )
    original_data = dict(root_entry.subentries[sub_a.subentry_id].data)

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with _patch_capabilities(_capabilities_single_owner()):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_TARGET_DEVICE_ID: device_b.id,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "device_mapping_conflict"}
    target_marker, _target_validator = _schema_field(
        result2["data_schema"], CONF_TARGET_DEVICE_ID
    )
    assert target_marker.description == {"suggested_value": device_a.id}

    assert root_entry.subentries[sub_a.subentry_id].data == original_data
    assert entity_registry.async_get(entity_a.entity_id).device_id == device_a.id
    assert entity_registry.async_get(entity_b.entity_id).device_id == device_b.id
    owners_a = device_registry.async_get(device_a.id).config_entries_subentries.get(
        root_entry.entry_id, ()
    )
    assert sub_a.subentry_id in owners_a
    owners_b = device_registry.async_get(device_b.id).config_entries_subentries.get(
        root_entry.entry_id, ()
    )
    assert sub_b.subentry_id in owners_b
    assert sub_a.subentry_id not in owners_b


async def test_subentry_reconfigure_cross_subentry_bundle_moves_entity_on_union(
    hass: HomeAssistant,
) -> None:
    """[design #6] On the installed union runtime, bundling onto another
    subentry's device is an explicit ordered move (add link, move entity, drop
    old link); the other subentry's entity row is preserved."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    sub_b = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.b", device_group_id="group-b"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    device_b = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_b.subentry_id,
        identifiers={(DOMAIN, "group-b")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )
    entity_b = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.b_power",
        device_id=device_b.id,
        subentry_id=sub_b.subentry_id,
    )

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_TARGET_DEVICE_ID: device_b.id,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"
    assert entity_registry.async_get(entity_a.entity_id).device_id == device_b.id
    other = entity_registry.async_get(entity_b.entity_id)
    assert other.entity_id == entity_b.entity_id
    assert other.unique_id == entity_b.unique_id
    assert other.device_id == device_b.id
    owners_b = device_registry.async_get(device_b.id).config_entries_subentries.get(
        root_entry.entry_id, ()
    )
    assert sub_a.subentry_id in owners_b
    assert sub_b.subentry_id in owners_b
    # The ordered move drops sub_a's link from the old device; the union
    # runtime then removes the orphaned, empty device shell.
    assert device_registry.async_get(device_a.id) is None
    updated = root_entry.subentries[sub_a.subentry_id].data
    assert updated[CONF_DEVICE_GROUP_ID] == "group-b"
    assert CONF_TARGET_DEVICE_ID not in updated
    assert CONF_CREATE_NEW_DEVICE not in updated


async def test_subentry_reconfigure_claims_unowned_target_on_union(
    hass: HomeAssistant,
) -> None:
    """[design #6] A target owned by no Abstractor subentry (here: by a
    different config entry) is claimed for this subentry and the entity moves
    onto it."""
    root_entry = _root_entry(hass)
    other_entry = MockConfigEntry(domain="other_domain", data={})
    other_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    target = device_registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={(DOMAIN, "claimed-group"), ("other_domain", "foreign")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_TARGET_DEVICE_ID: target.id,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert entity_registry.async_get(entity_a.entity_id).device_id == target.id
    owners = device_registry.async_get(target.id).config_entries_subentries.get(
        root_entry.entry_id, ()
    )
    assert sub_a.subentry_id in owners
    assert root_entry.subentries[sub_a.subentry_id].data[CONF_DEVICE_GROUP_ID] == (
        "claimed-group"
    )


async def test_subentry_reconfigure_claims_unowned_target_on_single_owner(
    hass: HomeAssistant,
) -> None:
    """[design #4] On the single-owner model the claim uses the singular
    new_config_* transfer kwargs."""
    root_entry = _root_entry(hass)
    other_entry = MockConfigEntry(domain="other_domain", data={})
    other_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    target = device_registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={(DOMAIN, "claimed-group"), ("other_domain", "foreign")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with (
        _patch_capabilities(_capabilities_single_owner()),
        patch.object(device_registry, "async_update_device") as mock_update,
    ):
        mock_update.return_value = None
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_TARGET_DEVICE_ID: target.id,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    mock_update.assert_called_once_with(
        target.id,
        new_config_entry_id=root_entry.entry_id,
        new_config_subentry_id=sub_a.subentry_id,
    )
    assert entity_registry.async_get(entity_a.entity_id).device_id == target.id


async def test_subentry_reconfigure_mapping_keeps_legacy_unique_id(
    hass: HomeAssistant,
) -> None:
    """[design #8] Moving a sensor with a legacy unique id keeps the id in the
    subentry data and keeps the entity row keyed on it."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass,
        root_entry,
        source_entity_id="sensor.a",
        device_group_id="group-a",
        legacy_unique_id="fridge_power_template",
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    target = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-b")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="fridge_power_template",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_TARGET_DEVICE_ID: target.id,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    updated = root_entry.subentries[sub_a.subentry_id].data
    assert updated[CONF_LEGACY_UNIQUE_ID] == "fridge_power_template"
    assert (
        entity_registry.async_get_entity_id("sensor", DOMAIN, "fridge_power_template")
        == entity_a.entity_id
    )
    assert entity_registry.async_get(entity_a.entity_id).device_id == target.id


async def test_subentry_reconfigure_unknown_target_rejected_zero_mutation(
    hass: HomeAssistant,
) -> None:
    """[design #9] A target device id that does not resolve in the registry
    fails closed with the conflict error and no mutation."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )
    original_data = dict(root_entry.subentries[sub_a.subentry_id].data)

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_TARGET_DEVICE_ID: "nonexistent-device-id",
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "device_mapping_conflict"}
    assert root_entry.subentries[sub_a.subentry_id].data == original_data
    assert entity_registry.async_get(entity_a.entity_id).device_id == device_a.id


async def test_subentry_reconfigure_target_without_domain_identifier_rejected(
    hass: HomeAssistant,
) -> None:
    """[design #9] A device that resolves but carries no DOMAIN identifier is
    rejected with the conflict error and zero mutation."""
    root_entry = _root_entry(hass)
    other_entry = MockConfigEntry(domain="other_domain", data={})
    other_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    foreign = device_registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={("other_domain", "not-abstractor")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )
    original_data = dict(root_entry.subentries[sub_a.subentry_id].data)

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_TARGET_DEVICE_ID: foreign.id,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "device_mapping_conflict"}
    assert root_entry.subentries[sub_a.subentry_id].data == original_data
    assert entity_registry.async_get(entity_a.entity_id).device_id == device_a.id


async def test_subentry_reconfigure_rejected_when_entity_registry_lacks_device_id(
    hass: HomeAssistant,
) -> None:
    """[design #9] A runtime whose entity registry cannot reparent rows fails
    closed with the conflict error before any mutation."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )
    original_data = dict(root_entry.subentries[sub_a.subentry_id].data)

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with _patch_capabilities(
        _capabilities_single_owner(entity_update_has_device_id=False)
    ):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_CREATE_NEW_DEVICE: True,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "device_mapping_conflict"}
    assert root_entry.subentries[sub_a.subentry_id].data == original_data
    assert entity_registry.async_get(entity_a.entity_id).device_id == device_a.id


async def test_subentry_reconfigure_detach_without_entity_row_is_noop(
    hass: HomeAssistant,
) -> None:
    """[design #3] Detaching a subentry whose entity row was never created is
    a no-op: the own device is created and the data is persisted ungrouped."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="shared-group"
    )

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_CREATE_NEW_DEVICE: True,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    own_device = device_registry.async_get_device({(DOMAIN, sub_a.subentry_id)})
    assert own_device is not None
    assert CONF_DEVICE_GROUP_ID not in root_entry.subentries[sub_a.subentry_id].data


async def test_subentry_reconfigure_detach_entity_without_device_is_noop(
    hass: HomeAssistant,
) -> None:
    """[design #3] Detaching a sensor whose entity row has no device yet still
    moves the row onto the fresh own device."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="shared-group"
    )
    device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        identifiers={(DOMAIN, "shared-group")},
    )
    entity_a = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "abstractor_sensor.a_power",
        config_entry=root_entry,
        config_subentry_id=sub_a.subentry_id,
    )
    assert entity_a.device_id is None

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.a",
            CONF_CREATE_NEW_DEVICE: True,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    own_device = device_registry.async_get_device({(DOMAIN, sub_a.subentry_id)})
    assert entity_registry.async_get(entity_a.entity_id).device_id == own_device.id


async def test_subentry_reconfigure_detach_with_missing_old_device_is_noop(
    hass: HomeAssistant,
) -> None:
    """[design #3] If the old device cannot be resolved after the move, the
    detach still succeeds (defensive branch)."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    grouped = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        identifiers={(DOMAIN, "shared-group")},
    )
    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="shared-group"
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=grouped.id,
        subentry_id=sub_a.subentry_id,
    )

    original_get = device_registry.async_get

    def _selective_get(device_id: str) -> Any:
        if device_id == grouped.id:
            return None
        return original_get(device_id)

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with patch.object(device_registry, "async_get", side_effect=_selective_get):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_CREATE_NEW_DEVICE: True,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    own_device = device_registry.async_get_device({(DOMAIN, sub_a.subentry_id)})
    assert entity_registry.async_get(entity_a.entity_id).device_id == own_device.id


async def test_subentry_reconfigure_move_with_missing_old_device_drops_nothing(
    hass: HomeAssistant,
) -> None:
    """[design #6] If the old device cannot be resolved when dropping the old
    link, the move still completes (defensive branch)."""
    root_entry = _root_entry(hass)
    other_entry = MockConfigEntry(domain="other_domain", data={})
    other_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    target = device_registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={(DOMAIN, "claimed-group"), ("other_domain", "foreign")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )

    original_get = device_registry.async_get

    def _selective_get(device_id: str) -> Any:
        if device_id == device_a.id:
            return None
        return original_get(device_id)

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with patch.object(device_registry, "async_get", side_effect=_selective_get):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_TARGET_DEVICE_ID: target.id,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert entity_registry.async_get(entity_a.entity_id).device_id == target.id
    assert root_entry.subentries[sub_a.subentry_id].data[CONF_DEVICE_GROUP_ID] == (
        "claimed-group"
    )


async def test_subentry_reconfigure_detach_registry_error_conflicts(
    hass: HomeAssistant,
) -> None:
    """[design] A registry exception during a detach is logged and fails
    closed: the form re-shows with the conflict error, data unchanged."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="shared-group"
    )
    original_data = dict(root_entry.subentries[sub_a.subentry_id].data)

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with patch.object(
        device_registry,
        "async_get_or_create",
        side_effect=RuntimeError("simulated failure"),
    ):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_CREATE_NEW_DEVICE: True,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "device_mapping_conflict"}
    assert root_entry.subentries[sub_a.subentry_id].data == original_data


async def test_subentry_reconfigure_move_error_conflicts(
    hass: HomeAssistant,
) -> None:
    """[design] A registry exception while moving the entity is logged and
    fails closed: conflict error, subentry data unchanged."""
    root_entry = _root_entry(hass)
    other_entry = MockConfigEntry(domain="other_domain", data={})
    other_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    target = device_registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={(DOMAIN, "claimed-group"), ("other_domain", "foreign")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )
    original_data = dict(root_entry.subentries[sub_a.subentry_id].data)

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with patch.object(
        entity_registry,
        "async_update_entity",
        side_effect=RuntimeError("simulated failure"),
    ):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_TARGET_DEVICE_ID: target.id,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "device_mapping_conflict"}
    assert root_entry.subentries[sub_a.subentry_id].data == original_data
    assert entity_registry.async_get(entity_a.entity_id).device_id == device_a.id


async def test_subentry_reconfigure_union_without_add_kwargs_conflicts(
    hass: HomeAssistant,
) -> None:
    """[design] _add_owner_link fails closed when the union add kwargs are
    absent from the detected API."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    sub_b = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.b", device_group_id="group-b"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    device_b = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_b.subentry_id,
        identifiers={(DOMAIN, "group-b")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )
    original_data = dict(root_entry.subentries[sub_a.subentry_id].data)

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with _patch_capabilities(
        _capabilities_union(add_config_entry_id=None, add_config_subentry_id=None)
    ):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_TARGET_DEVICE_ID: device_b.id,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "device_mapping_conflict"}
    assert root_entry.subentries[sub_a.subentry_id].data == original_data
    assert entity_registry.async_get(entity_a.entity_id).device_id == device_a.id


async def test_subentry_reconfigure_single_owner_without_new_config_kwargs_conflicts(
    hass: HomeAssistant,
) -> None:
    """[design] _add_owner_link fails closed when the single-owner
    new_config_* kwargs are absent from the detected API."""
    root_entry = _root_entry(hass)
    other_entry = MockConfigEntry(domain="other_domain", data={})
    other_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="group-a"
    )
    device_a = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=sub_a.subentry_id,
        identifiers={(DOMAIN, "group-a")},
    )
    target = device_registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={(DOMAIN, "claimed-group"), ("other_domain", "foreign")},
    )
    entity_a = _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_a.id,
        subentry_id=sub_a.subentry_id,
    )
    original_data = dict(root_entry.subentries[sub_a.subentry_id].data)

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with _patch_capabilities(
        _capabilities_single_owner(
            new_config_entry_id=None, new_config_subentry_id=None
        )
    ):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_TARGET_DEVICE_ID: target.id,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "device_mapping_conflict"}
    assert root_entry.subentries[sub_a.subentry_id].data == original_data
    assert entity_registry.async_get(entity_a.entity_id).device_id == device_a.id


async def test_subentry_reconfigure_detach_without_remove_kwargs_conflicts(
    hass: HomeAssistant,
) -> None:
    """[design] _remove_owner_link fails closed when the union remove kwargs
    are absent from the detected API."""
    root_entry = _root_entry(hass)
    device_registry = dr.async_get(hass)

    sub_a = _add_sensor_subentry(
        hass, root_entry, source_entity_id="sensor.a", device_group_id="shared-group"
    )
    device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        identifiers={(DOMAIN, "shared-group")},
    )
    _register_sensor_entity(
        hass,
        root_entry,
        unique_id="abstractor_sensor.a_power",
        device_id=device_registry.async_get_device({(DOMAIN, "shared-group")}).id,
        subentry_id=sub_a.subentry_id,
    )
    original_data = dict(root_entry.subentries[sub_a.subentry_id].data)

    result = await _start_reconfigure(hass, root_entry, sub_a.subentry_id)
    with _patch_capabilities(
        _capabilities_union(remove_config_entry_id=None, remove_config_subentry_id=None)
    ):
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.a",
                CONF_CREATE_NEW_DEVICE: True,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "device_mapping_conflict"}
    assert root_entry.subentries[sub_a.subentry_id].data == original_data


def test_detect_ownership_model_union() -> None:
    """The installed runtime (2026.2.3) only exposes the union owner fields."""
    assert _detect_ownership_model(dr.DeviceEntry) == "union"


def test_detect_ownership_model_single_owner() -> None:
    """A runtime exposing the singular owner fields is single-owner."""
    with (
        patch.object(dr.DeviceEntry, "config_entry_id", None, create=True),
        patch.object(dr.DeviceEntry, "config_subentry_id", None, create=True),
    ):
        assert _detect_ownership_model(dr.DeviceEntry) == "single-owner"


def test_registry_capabilities_falls_back_to_new_config_kwargs(
    hass: HomeAssistant,
) -> None:
    """A registry API exposing only new_config_* kwargs is detected via the
    feature-detection fallback, never via a version pin."""

    def fake_update_device(
        self,
        device_id: str,
        *,
        new_config_entry_id: str | None = None,
        new_config_subentry_id: str | None = None,
    ) -> None:
        return None

    fake_update_device.__signature__ = inspect.Signature(
        parameters=[
            inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("device_id", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter(
                "new_config_entry_id",
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
            ),
            inspect.Parameter(
                "new_config_subentry_id",
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
            ),
        ]
    )
    _registry_capabilities.cache_clear()
    try:
        with patch.object(dr.DeviceRegistry, "async_update_device", fake_update_device):
            caps = _registry_capabilities(hass)
        assert caps.add_config_entry_id == "new_config_entry_id"
        assert caps.add_config_subentry_id == "new_config_subentry_id"
        assert caps.remove_config_entry_id == "new_config_entry_id"
        assert caps.remove_config_subentry_id == "new_config_subentry_id"
        assert caps.new_config_entry_id == "new_config_entry_id"
        assert caps.new_config_subentry_id == "new_config_subentry_id"
    finally:
        _registry_capabilities.cache_clear()


def test_sensor_unique_id_legacy_wins() -> None:
    """[design #8] A legacy unique id always wins over the derived id."""
    data = {
        CONF_LEGACY_UNIQUE_ID: "old_unique_id_123",
        CONF_SOURCE_ENTITY_ID: "sensor.a",
        CONF_DEVICE_TYPE: "power",
    }
    assert _sensor_unique_id(data) == "old_unique_id_123"


def test_sensor_unique_id_single_source() -> None:
    """A single source keeps the MVP-era id format."""
    data = {CONF_SOURCE_ENTITY_ID: "sensor.a", CONF_DEVICE_TYPE: "power"}
    assert _sensor_unique_id(data) == "abstractor_sensor.a_power"


def test_sensor_unique_id_multi_source_sorted() -> None:
    """Multiple sources use the sorted multi-source id format."""
    data = {
        CONF_SOURCE_ENTITY_IDS: ["sensor.b", "sensor.a"],
        CONF_DEVICE_TYPE: "power",
    }
    assert _sensor_unique_id(data) == "abstractor_power_sensor.a_sensor.b"


def test_sensor_unique_id_filters_empty_sources() -> None:
    """Empty source entries are filtered before deriving the id."""
    data = {
        CONF_SOURCE_ENTITY_IDS: ["sensor.a", ""],
        CONF_DEVICE_TYPE: "power",
    }
    assert _sensor_unique_id(data) == "abstractor_sensor.a_power"
