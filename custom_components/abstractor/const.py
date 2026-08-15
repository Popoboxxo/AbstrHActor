"""Constants for the Abstractor integration."""
from typing import Any, Final

DOMAIN: Final = "abstractor"
CONFIG_ENTRY_VERSION: Final = 1
# Identity of the singleton parent entry that every sensor subentry hangs off.
# Both the config flow and the legacy-entry reconciliation key on this exact
# value, so it must not be spelled out as a literal in either of them.
ROOT_UNIQUE_ID: Final = "abstractor_root"
ROOT_ENTRY_TITLE: Final = "Abstractor"
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
CONF_DEVICE_GROUP_ID: Final = "device_group_id"
CONF_TARGET_DEVICE_ID: Final = "target_device_id"
CONF_CREATE_NEW_DEVICE: Final = "create_new_device"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_INFLUX_HOST: Final = "influx_host"
CONF_INFLUX_TOKEN: Final = "influx_token"
CONF_INFLUX_ORG: Final = "influx_org"
CONF_INFLUX_BUCKET: Final = "influx_bucket"
CONF_DEVICE_NAME: Final = "device_name"
CONF_DEVICE_MANUFACTURER: Final = "device_manufacturer"
CONF_DEVICE_MODEL: Final = "device_model"
SUBENTRY_TYPE_SENSOR: Final = "sensor"

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

DEFAULT_POLL_INTERVAL: Final = 30
POLL_INTERVAL_PRESETS: Final = (2, 5, 30)
POLL_INTERVAL_MIN: Final = 1
POLL_INTERVAL_MAX: Final = 3600
DEFAULT_DEVICE_NAME: Final = "Abstract {device_type}"
DEFAULT_DEVICE_MANUFACTURER: Final = "Abstractor"
DEFAULT_DEVICE_MODEL: Final = "Abstract sensor"
DEFAULT_OPTIONS: Final[dict[str, Any]] = {
    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
    CONF_DEVICE_NAME: DEFAULT_DEVICE_NAME,
    CONF_DEVICE_MANUFACTURER: DEFAULT_DEVICE_MANUFACTURER,
    CONF_DEVICE_MODEL: DEFAULT_DEVICE_MODEL,
}
