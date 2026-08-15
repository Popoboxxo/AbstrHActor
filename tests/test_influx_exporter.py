"""Test the InfluxDB exporter (REQ-DATA-002)."""

from unittest.mock import AsyncMock, Mock, patch

from custom_components.abstractor.const import (
    CONF_INFLUX_BUCKET,
    CONF_INFLUX_HOST,
    CONF_INFLUX_ORG,
    CONF_INFLUX_TOKEN,
)
from custom_components.abstractor.influx_exporter import (
    InfluxExporter,
    create_influx_exporter,
)


def _session(status: int = 204):
    response = Mock(status=status)
    response.text = AsyncMock(return_value="")
    cm = Mock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)
    session = Mock()
    session.post = Mock(return_value=cm)
    return session, session.post


async def test_async_push_writes_line_protocol_to_influx() -> None:
    """A successful push posts a line-protocol body to the v2 write endpoint."""
    session, post = _session(status=204)
    exporter = InfluxExporter(session, "http://influx.local:8086", "tok", "org", "bucket")

    await exporter.async_push("sensor.power", 12.5)

    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == "http://influx.local:8086/api/v2/write"
    assert kwargs["data"] == "abstractor,entity_id=sensor.power value=12.5"
    assert kwargs["headers"]["Authorization"] == "Token tok"


async def test_async_push_swallows_http_error_status() -> None:
    """A non-2xx response must not raise into the coordinator update loop."""
    session, _post = _session(status=500)
    exporter = InfluxExporter(session, "http://influx.local:8086", "tok", "org", "bucket")

    await exporter.async_push("sensor.power", 1.0)  # must not raise


def _patch_clientsession(session: Mock):
    """Patch the real module-level aiohttp_client helper the factory uses."""
    return patch(
        "custom_components.abstractor.influx_exporter.aiohttp_client.async_get_clientsession",
        return_value=session,
    )


def test_create_influx_exporter_returns_instance_with_credentials() -> None:
    """[REQ-DATA-002] Host+token set -> an exporter bound to those options."""
    session = Mock()
    with _patch_clientsession(session) as mock_clientsession:
        hass = Mock()
        exporter = create_influx_exporter(
            hass,
            {
                CONF_INFLUX_HOST: "http://influx.local:8086/",
                CONF_INFLUX_TOKEN: "tok-123",
                CONF_INFLUX_ORG: "energy",
                CONF_INFLUX_BUCKET: "abstractor",
            },
        )

        assert isinstance(exporter, InfluxExporter)
        assert exporter._host == "http://influx.local:8086"  # trailing slash stripped
        assert exporter._token == "tok-123"
        assert exporter._org == "energy"
        assert exporter._bucket == "abstractor"
        mock_clientsession.assert_called_once_with(hass)


def test_create_influx_exporter_returns_none_without_host() -> None:
    """[REQ-DATA-002] Missing host -> None, no session is obtained."""
    session = Mock()
    with _patch_clientsession(session) as mock_clientsession:
        hass = Mock()
        exporter = create_influx_exporter(
            hass,
            {
                CONF_INFLUX_TOKEN: "tok-123",
                CONF_INFLUX_ORG: "energy",
                CONF_INFLUX_BUCKET: "abstractor",
            },
        )

        assert exporter is None
        mock_clientsession.assert_not_called()


def test_create_influx_exporter_returns_none_without_token() -> None:
    """[REQ-DATA-002] Missing token -> None, no session is obtained."""
    session = Mock()
    with _patch_clientsession(session) as mock_clientsession:
        hass = Mock()
        exporter = create_influx_exporter(
            hass,
            {
                CONF_INFLUX_HOST: "http://influx.local:8086",
                CONF_INFLUX_ORG: "energy",
                CONF_INFLUX_BUCKET: "abstractor",
            },
        )

        assert exporter is None
        mock_clientsession.assert_not_called()


def test_create_influx_exporter_returns_none_for_blank_credentials() -> None:
    """[REQ-DATA-002] Whitespace-only host/token count as missing."""
    session = Mock()
    with _patch_clientsession(session) as mock_clientsession:
        hass = Mock()
        exporter = create_influx_exporter(
            hass,
            {
                CONF_INFLUX_HOST: "   ",
                CONF_INFLUX_TOKEN: "",
                CONF_INFLUX_ORG: "energy",
                CONF_INFLUX_BUCKET: "abstractor",
            },
        )

        assert exporter is None
        mock_clientsession.assert_not_called()
