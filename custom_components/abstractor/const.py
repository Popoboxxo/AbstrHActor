"""Constants for the Abstractor integration."""
from typing import Final

DOMAIN: Final = "abstractor"
CONFIG_ENTRY_VERSION: Final = 1
CONF_DEVICE_TYPE: Final = "device_type"
CONF_SOURCE_ENTITY_ID: Final = "source_entity_id"
CONF_SOURCE_ENTITY_IDS: Final = "source_entity_ids"
CONF_SPIKE_FILTER: Final = "spike_filter"
CONF_INVERT: Final = "invert"
CONF_FALLBACK_ZERO: Final = "fallback_zero"
CONF_LEGACY_UNIQUE_ID: Final = "legacy_unique_id"
CONF_FALLBACK_SOURCE_ENTITY_ID: Final = "fallback_source_entity_id"
CONF_FALLBACK_CONDITION_ENTITY_ID: Final = "fallback_condition_entity_id"
CONF_FALLBACK_CONDITION_STATE: Final = "fallback_condition_state"
CONF_NET_SUBTRACT_ENTITY_ID: Final = "net_subtract_entity_id"

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
