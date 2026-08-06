"""Test the InfluxDB exporter (REQ-DATA-002)."""

from unittest.mock import AsyncMock, Mock

from custom_components.abstractor.influx_exporter import InfluxExporter


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
