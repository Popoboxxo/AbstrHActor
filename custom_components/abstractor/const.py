"""Constants for the Abstractor integration."""
from typing import Final

DOMAIN: Final = "abstractor"
CONF_DEVICE_TYPE: Final = "device_type"
CONF_SOURCE_ENTITY_ID: Final = "source_entity_id"
CONF_SOURCE_ENTITY_IDS: Final = "source_entity_ids"
CONF_SPIKE_FILTER: Final = "spike_filter"
CONF_INVERT: Final = "invert"
CONF_FALLBACK_ZERO: Final = "fallback_zero"

# Storage
STORAGE_KEY: Final = f"{DOMAIN}.storage"
STORAGE_VERSION: Final = 1
SERVICE_EXPORT_DATA: Final = "export_data"
SERVICE_IMPORT_DATA: Final = "import_data"

# Sensor Types
TYPE_POWER = "power"
TYPE_ENERGY = "energy"
TYPE_WATER = "water"

SENSOR_TYPES = [
    TYPE_POWER,
    TYPE_ENERGY,
    TYPE_WATER,
]
