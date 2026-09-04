"""Test Abstractor diagnostics."""

from unittest.mock import Mock

from custom_components.abstractor.const import CONF_INFLUX_TOKEN, DOMAIN
from custom_components.abstractor.diagnostics import async_get_config_entry_diagnostics


async def test_config_entry_diagnostics_uses_shared_coordinator(hass) -> None:
    """Diagnostics should read the coordinator, not entry data."""
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.subentries = {}
    entry.as_dict.return_value = {"entry_id": entry.entry_id}
    coordinator = Mock(data={entry.entry_id: 12.0}, pipelines={})
    hass.data[DOMAIN] = {"coordinator": coordinator, entry.entry_id: entry.data}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["coordinator_data"] == {entry.entry_id: 12.0}
    assert result["pipeline_config"] == {}


async def test_pipeline_config_is_keyed_by_subentry_id_not_entry_id() -> None:
    """[GH regression] pipeline_config must include every subentry belonging
    to the entry, keyed by subentry_id — not filtered by entry.entry_id,
    which never matches a subentry_id except in one legacy-promotion edge
    case. Reproduces the bug: coordinator.pipelines is keyed by subentry_id
    ("subentry-a"), which is NOT entry.entry_id ("entry-1")."""
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.subentries = {"subentry-a": Mock(), "subentry-b": Mock()}
    entry.as_dict.return_value = {"entry_id": "entry-1"}
    pipeline_a = Mock(config={"device_type": "power"})
    pipeline_b = Mock(config={"device_type": "energy"})
    coordinator = Mock(
        data={}, pipelines={"subentry-a": pipeline_a, "subentry-b": pipeline_b}
    )
    hass = Mock()
    hass.data = {DOMAIN: {"coordinator": coordinator}}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["pipeline_config"] == {
        "subentry-a": {"device_type": "power"},
        "subentry-b": {"device_type": "energy"},
    }


async def test_diagnostics_masks_influx_token(hass) -> None:
    """[REQ-NFA-006] The returned dict never contains the raw Influx token;
    the field is present but masked."""
    raw_token = "super-secret-influx-token"
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.as_dict.return_value = {
        "entry_id": "entry-1",
        "options": {
            "influx_host": "http://influx.local:8086",
            CONF_INFLUX_TOKEN: raw_token,
            "influx_org": "energy",
            "influx_bucket": "abstractor",
        },
    }
    coordinator = Mock(data={}, pipelines={})
    hass.data[DOMAIN] = {"coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, entry)

    options = result["entry"]["options"]
    assert options[CONF_INFLUX_TOKEN] == "***"
    assert raw_token not in str(result)
    # The entry's own dict is deep-copied, not mutated in place.
    assert entry.as_dict.return_value["options"][CONF_INFLUX_TOKEN] == raw_token


async def test_diagnostics_leaves_options_without_token_untouched(hass) -> None:
    """[REQ-NFA-006] No token configured -> options pass through unchanged."""
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.as_dict.return_value = {
        "entry_id": "entry-1",
        "options": {"poll_interval": 30},
    }
    coordinator = Mock(data={}, pipelines={})
    hass.data[DOMAIN] = {"coordinator": coordinator}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry"]["options"] == {"poll_interval": 30}
