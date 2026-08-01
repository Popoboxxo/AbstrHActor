"""Test the Abstractor config flow."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.abstractor.const import (
    CONF_DEVICE_TYPE,
    CONF_SOURCE_ENTITY_ID,
    DOMAIN,
)


async def test_form(hass: HomeAssistant) -> None:
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] is None

    with patch(
        "custom_components.abstractor.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_DEVICE_TYPE: "power",
                CONF_SOURCE_ENTITY_ID: "sensor.test_power",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["title"] == "Abstract power"
    assert result2["data"] == {
        CONF_DEVICE_TYPE: "power",
        CONF_SOURCE_ENTITY_ID: "sensor.test_power",
    }
    assert len(mock_setup_entry.mock_calls) == 1
