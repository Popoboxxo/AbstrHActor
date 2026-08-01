"""Constants for the Abstractor integration."""
from typing import Final

DOMAIN: Final = "abstractor"
CONF_DEVICE_TYPE: Final = "device_type"
CONF_SOURCE_ENTITY_ID: Final = "source_entity_id"

# Storage
STORAGE_KEY: Final = f"{DOMAIN}.storage"
STORAGE_VERSION: Final = 1

# Sensor Types
TYPE_POWER = "power"
TYPE_ENERGY = "energy"
TYPE_WATER = "water"

SENSOR_TYPES = [
    TYPE_POWER,
    TYPE_ENERGY,
    TYPE_WATER,
]
