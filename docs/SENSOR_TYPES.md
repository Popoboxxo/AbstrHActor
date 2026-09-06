# Supported Sensor Types

Source of truth: `custom_components/abstractor/sensor.py` (device_class/unit/state_class
assignment, `AbstractorSensor.__init__`) and `custom_components/abstractor/const.py`
(`SENSOR_TYPES`).

| `device_type` | `device_class` | `native_unit_of_measurement` | `state_class` |
|---|---|---|---|
| `power` | `SensorDeviceClass.POWER` | `W` | `SensorStateClass.MEASUREMENT` |
| `energy` | `SensorDeviceClass.ENERGY` | `kWh` | `SensorStateClass.TOTAL_INCREASING` |
| `water` | `SensorDeviceClass.WATER` | `L` | `SensorStateClass.TOTAL_INCREASING` |

Power sensors fail soft to `0` when their source is unavailable; energy and water
sensors fail closed to `unavailable` so a utility meter never counts a bad sample
(`filters.py`, keyed on `config["device_type"] == "power"`).

Adding a new type requires changes in three places: `const.py` (`SENSOR_TYPES`),
`sensor.py` (the device_class/unit/state_class if/elif chain — see ARCH-9 in
`docs/SYSTEM_AUDIT_2026-09-04.md` for the case to make this declarative instead),
and `filters.py`'s fail-soft-vs-fail-closed check (`device_type == "power"`).
