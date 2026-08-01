"""InfluxDB Exporter for Abstractor."""
import logging

_LOGGER = logging.getLogger(__name__)

class InfluxExporter:
    """Exports data to InfluxDB."""
    def __init__(self, host: str, token: str, org: str, bucket: str):
        self.host = host
        self.token = token
        self.org = org
        self.bucket = bucket
        _LOGGER.info("InfluxExporter initialized for %s", bucket)

    async def async_push(self, entity_id: str, value: float) -> None:
        """Push a value to InfluxDB asynchronously."""
        _LOGGER.debug("Pushing %s=%s to InfluxDB", entity_id, value)
