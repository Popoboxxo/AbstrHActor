"""Test the Abstractor config flow."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abstractor.config_flow import (
    AbstractorSensorSubentryFlowHandler,
    _device_group_id_for_device,
)
from custom_components.abstractor.const import (
    CONF_CREATE_NEW_DEVICE,
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
    CONF_SPIKE_FILTER,
    CONF_TARGET_DEVICE_ID,
    DOMAIN,
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
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {}
        )
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


# GH#18: CONF_TARGET_DEVICE_ID and CONF_CREATE_NEW_DEVICE have been removed
# from _schema() entirely — using either on current Home Assistant (2026.8.0)
# silently merges/moves a device between subentries and destroys the OTHER
# sensor's entity registry row. The tests below therefore no longer submit
# those fields through the form (HA's own schema validation would now reject
# them, since the schema doesn't define them at all); instead they exercise
# `_normalize`'s resolution logic directly — it stays correct and is kept as
# the seam a future, non-destructive bundling fix will reuse (see
# config_flow.py's `_normalize` docstring).
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


async def test_subentry_reconfigure_preserves_device_group_when_unset(
    hass: HomeAssistant,
) -> None:
    """Reconfiguring a bundled sensor without touching the device selector
    must NOT silently un-bundle it from its device (regression for the
    blocker where _normalize only wrote CONF_DEVICE_GROUP_ID when
    CONF_TARGET_DEVICE_ID was present in the current form submission)."""
    from homeassistant.config_entries import ConfigSubentry

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


# test_subentry_reconfigure_prefills_target_device used to live here: it
# asserted that the reconfigure form's schema contained a CONF_TARGET_DEVICE_ID
# key pre-filled with the subentry's current device. That field (and the
# pre-fill logic that fed it in async_step_reconfigure) has been removed
# entirely (GH#18, see the block comment above) — there is no longer a UI
# field for this test to assert against, so it was removed rather than
# adapted.


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


async def test_subentry_reconfigure_requires_source(hass: HomeAssistant) -> None:
    """Reconfiguring without any source entity re-shows the form with an error."""
    from homeassistant.config_entries import ConfigSubentry

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
    from homeassistant.config_entries import ConfigSubentry

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
    from homeassistant.config_entries import ConfigSubentry

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
    for submitted in ({}, {CONF_LEGACY_UNIQUE_ID: ""}, {CONF_LEGACY_UNIQUE_ID: "other"}):
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
    from homeassistant.config_entries import ConfigSubentry

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
