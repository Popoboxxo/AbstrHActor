# Abstractor demo / E2E instance

A real, clickable Home Assistant instance for manual testing and as the
target for E2E UI tests, with two kinds of source entities:

- HA's built-in `demo:` platform (random-ish, not controllable)
- [hass-virtual](https://github.com/twrecked/hass-virtual) sensors defined
  in `ha_config/virtual.yaml` (stable entity_ids, values settable at
  runtime via the `virtual.set` service — this is what E2E tests drive)

## First-time setup

```bash
bash docker/setup-demo.sh                          # fetches hass-virtual (not vendored, separate upstream)
docker compose -f docker/docker-compose.demo.yml up -d
```

Open http://localhost:8123, finish onboarding (any local user/password),
then Settings → Devices & Services → Add Integration → "Abstractor".

## Files

- `docker-compose.demo.yml` — tracked in git.
- `ha_config/configuration.yaml`, `ha_config/virtual.yaml` — tracked in git
  (seed config, no secrets — see the `.gitignore` exceptions for
  `docker/ha_config/*`).
- `ha_config/custom_components/virtual/`, `ha_config/.storage/`,
  `ha_config/home-assistant_v2.db*`, `ha_config/*.log` — NOT tracked
  (generated runtime state / third-party code, contains auth tokens).

## Virtual test fixtures (`ha_config/virtual.yaml`)

| Entity | class | purpose |
|---|---|---|
| `sensor.fridge_power` | power | single-source aggregation target |
| `sensor.fridge_energy` | energy | fail-closed / spike-filter target |
| `sensor.garden_water` | water | fail-closed target |
| `sensor.battery_charge_power` / `sensor.battery_discharge_power` | power | REQ-CORE-005 net-flow subtraction |
| `sensor.fallback_power_source` | power | REQ-COMP-004 fallback source |
| `binary_sensor.fallback_condition` | — | REQ-COMP-004 fallback condition entity |

Set a value from an automation, script, or the E2E test itself:

```yaml
service: virtual.set
target:
  entity_id: sensor.fridge_power
data:
  value: 999
```

## Stopping / resetting

```bash
docker compose -f docker/docker-compose.demo.yml down
rm -rf docker/ha_config/.storage docker/ha_config/home-assistant_v2.db* docker/ha_config/home-assistant.log
```

(Full wipe: also delete `docker/ha_config/custom_components/virtual` and
re-run `setup-demo.sh`.)
