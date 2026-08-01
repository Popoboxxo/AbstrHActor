"""Device Registry for Abstractor."""
import logging

_LOGGER = logging.getLogger(__name__)

class DeviceRegistry:
    """Registry to manage and cluster abstract devices."""
    def __init__(self):
        self._devices = {}

    def register_device(self, unique_id: str, name: str, manufacturer: str, model: str):
        """Register a new abstract device."""
        self._devices[unique_id] = {
            "name": name,
            "manufacturer": manufacturer,
            "model": model,
        }
        _LOGGER.debug("Registered device: %s", name)

    def get_device(self, unique_id: str) -> dict | None:
        """Get a registered device by unique ID."""
        return self._devices.get(unique_id)
