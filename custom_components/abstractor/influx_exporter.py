"""InfluxDB Exporter for Abstractor (REQ-DATA-002)."""
from __future__ import annotations

import logging

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import (
    CONF_INFLUX_BUCKET,
    CONF_INFLUX_HOST,
    CONF_INFLUX_ORG,
    CONF_INFLUX_TOKEN,
)

_LOGGER = logging.getLogger(__name__)

_WRITE_PATH = "/api/v2/write"
_TIMEOUT = aiohttp.ClientTimeout(total=10)


def create_influx_exporter(
    hass: HomeAssistant, options: dict[str, object]
) -> InfluxExporter | None:
    """Create an exporter when both required credentials are configured."""
    host = str(options.get(CONF_INFLUX_HOST, "")).strip()
    token = str(options.get(CONF_INFLUX_TOKEN, "")).strip()
    if not host or not token:
        return None
    session = aiohttp_client.async_get_clientsession(hass)
    return InfluxExporter(
        session,
        host,
        token,
        str(options.get(CONF_INFLUX_ORG, "")),
        str(options.get(CONF_INFLUX_BUCKET, "")),
    )


class InfluxExporter:
    """Pushes abstracted sensor values to an InfluxDB v2 bucket via line protocol."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        token: str,
        org: str,
        bucket: str,
    ):
        self._session = session
        self._host = host.rstrip("/")
        self._token = token
        self._org = org
        self._bucket = bucket
        _LOGGER.info("InfluxExporter initialized for %s", bucket)

    async def async_push(self, entity_id: str, value: float) -> None:
        """Push a single value to InfluxDB asynchronously.

        Uses the v2 HTTP line-protocol write endpoint directly over the
        session's aiohttp client instead of a dedicated influxdb client
        dependency, so no extra package needs to be added to manifest.json.
        Network/HTTP failures are logged and swallowed: a broken Influx
        export must never break the abstracted sensor's own state update.
        """
        line = f"abstractor,entity_id={entity_id} value={value}"
        params = {"org": self._org, "bucket": self._bucket, "precision": "s"}
        headers = {
            "Authorization": f"Token {self._token}",
            "Content-Type": "text/plain; charset=utf-8",
        }
        try:
            async with self._session.post(
                f"{self._host}{_WRITE_PATH}",
                params=params,
                headers=headers,
                data=line,
                timeout=_TIMEOUT,
            ) as response:
                if response.status >= 400:
                    body = await response.text()
                    _LOGGER.warning(
                        "InfluxDB write failed (%s) for %s: %s",
                        response.status,
                        entity_id,
                        body,
                    )
                    return
        except aiohttp.ClientError as err:
            _LOGGER.warning("InfluxDB write error for %s: %s", entity_id, err)
            return
        _LOGGER.debug("Pushed %s=%s to InfluxDB", entity_id, value)
