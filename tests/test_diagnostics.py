"""Test Abstractor diagnostics."""

from unittest.mock import Mock

from custom_components.abstractor.const import DOMAIN
from custom_components.abstractor.diagnostics import async_get_config_entry_diagnostics


async def test_config_entry_diagnostics_uses_shared_coordinator(hass) -> None:
    """Diagnostics should read the coordinator, not entry data."""
    entry = Mock()
    entry.entry_id = "entry-1"
    entry.as_dict.return_value = {"entry_id": entry.entry_id}
    coordinator = Mock(data={entry.entry_id: 12.0}, pipelines={})
    hass.data[DOMAIN] = {"coordinator": coordinator, entry.entry_id: entry.data}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["coordinator_data"] == {entry.entry_id: 12.0}
    assert result["pipeline_config"] == {}
