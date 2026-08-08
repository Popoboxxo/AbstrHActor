"""Test the Abstractor config flow."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.abstractor.config_flow import _device_group_id_for_device
from custom_components.abstractor.const import (
    CONF_CREATE_NEW_DEVICE,
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SOURCE_ENTITY_IDS,
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


async def test_subentry_create_form_target_device_resolves_group_id(
    hass: HomeAssistant,
) -> None:
    """Picking a target device resolves to this integration's own group id."""
    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    device_reg = dr.async_get(hass)
    device = device_reg.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        identifiers={(DOMAIN, "existing-group")},
    )

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={"source": config_entries.SOURCE_USER},
    )

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "power",
            CONF_SOURCE_ENTITY_ID: "sensor.test_power",
            CONF_TARGET_DEVICE_ID: device.id,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    subentries = list(root_entry.subentries.values())
    assert len(subentries) == 1
    assert subentries[0].data[CONF_DEVICE_GROUP_ID] == "existing-group"
    assert CONF_TARGET_DEVICE_ID not in subentries[0].data


async def test_subentry_reconfigure_moves_device(hass: HomeAssistant) -> None:
    """Reconfiguring a subentry can move it onto an existing device."""
    from homeassistant.config_entries import ConfigSubentry

    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    existing_subentry = ConfigSubentry(
        data={CONF_DEVICE_TYPE: "power", CONF_SOURCE_ENTITY_ID: "sensor.a"},
        subentry_type="sensor",
        title="Abstract power",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, existing_subentry)

    device_registry = dr.async_get(hass)
    target_device = device_registry.async_get_or_create(
        config_entry_id=root_entry.entry_id,
        config_subentry_id=existing_subentry.subentry_id,
        identifiers={(DOMAIN, existing_subentry.subentry_id)},
    )

    another_subentry = ConfigSubentry(
        data={CONF_DEVICE_TYPE: "energy", CONF_SOURCE_ENTITY_ID: "sensor.b"},
        subentry_type="sensor",
        title="Abstract energy",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(root_entry, another_subentry)

    result = await hass.config_entries.subentries.async_init(
        (root_entry.entry_id, "sensor"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": another_subentry.subentry_id,
        },
    )
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_TYPE: "energy",
            CONF_SOURCE_ENTITY_ID: "sensor.b",
            CONF_TARGET_DEVICE_ID: target_device.id,
        },
    )
    await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"
    updated = root_entry.subentries[another_subentry.subentry_id]
    assert updated.data[CONF_DEVICE_GROUP_ID] == existing_subentry.subentry_id


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


async def test_subentry_reconfigure_prefills_target_device(
    hass: HomeAssistant,
) -> None:
    """The reconfigure form's device selector is pre-filled with the
    subentry's CURRENT device, resolved back from CONF_DEVICE_GROUP_ID."""
    from homeassistant.config_entries import ConfigSubentry

    root_entry = MockConfigEntry(domain=DOMAIN, unique_id="abstractor_root", data={})
    root_entry.add_to_hass(hass)

    device_reg = dr.async_get(hass)
    device = device_reg.async_get_or_create(
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
    marker = next(
        key for key in result["data_schema"].schema if key == CONF_TARGET_DEVICE_ID
    )
    assert marker.description["suggested_value"] == device.id


async def test_subentry_reconfigure_detaches_with_create_new_device(
    hass: HomeAssistant,
) -> None:
    """Reconfiguring an already-bundled sensor with CONF_CREATE_NEW_DEVICE
    checked (and no target device picked) must explicitly split it back out
    to its own device — CONF_DEVICE_GROUP_ID must be fully absent from the
    resulting data, not just falsy (regression for the round-1 fix's
    unintended side effect: it made this split impossible, per design spec
    line 23-24)."""
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
    updated = root_entry.subentries[grouped_subentry.subentry_id]
    assert CONF_DEVICE_GROUP_ID not in updated.data


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
