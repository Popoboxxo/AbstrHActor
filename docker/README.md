# Abstractor demo / E2E instances

Two separate, independent Home Assistant config directories — deliberately
NOT shared, see the "Why two directories" note below.

- `ha_config/` — for manual poking (`docker-compose.demo.yml`), persists
  across restarts, accumulates whatever you click through.
- `ha_config_e2e/` — for the E2E suite (`docker-compose.e2e.yml`), meant to
  stay disposable/reproducible. In practice it's a host bind mount, so
  `docker compose down -v` does NOT reset it — see "Stopping / resetting"
  below; skipping that step accumulates devices across runs and makes the
  suite flaky (config entries pile up, unique-count assertions fail).

Both get two kinds of source entities:

- HA's built-in `demo:` platform (random-ish, not controllable)
- [hass-virtual](https://github.com/twrecked/hass-virtual) sensors defined
  in `virtual_sensors.yaml` / `virtual_binary_sensors.yaml` (stable
  entity_ids, values settable at runtime via the `virtual.set` service —
  this is what E2E tests drive)

## First-time setup

```bash
bash docker/setup-demo.sh                          # fetches hass-virtual into ha_config/ (not vendored, separate upstream)
docker compose -f docker/docker-compose.demo.yml up -d
```

Open http://localhost:8123, finish onboarding (any local user/password),
then Settings → Devices & Services → Add Integration → "Abstractor".

For the E2E stack, see `docker-compose.e2e.yml` and `docs/E2E_TESTING.md`
at the repo root — it seeds its own `ha_config_e2e/` and onboards via
`scripts/e2e_bootstrap.py` instead of the manual flow above.

## Why two directories

`scripts/e2e_bootstrap.py` assumes a fresh-or-known instance: it creates
user `e2e` or, if that already exists, logs in as `e2e`. If the E2E stack
shared `ha_config/` with the manually-poked demo instance, a different
user (e.g. one created by hand while testing something) would already
have completed onboarding, and HA's onboarding API stops existing once
onboarding is done — breaking the bootstrap script's assumptions in a
confusing way (this happened once building the suite; keeping the two
instances apart avoids it entirely).

## Files

- `docker-compose.demo.yml`, `docker-compose.e2e.yml` (repo root) — tracked in git.
- `ha_config/configuration.yaml`, `ha_config/virtual_sensors.yaml`,
  `ha_config/virtual_binary_sensors.yaml` (and the `ha_config_e2e/`
  equivalents) — tracked in git (seed config, no secrets — see the
  `.gitignore` exceptions for `docker/ha_config/*` / `docker/ha_config_e2e/*`).
- `custom_components/virtual/`, `.storage/`, `home-assistant_v2.db*`,
  `*.log`, `known_devices.yaml` under either directory — NOT tracked
  (generated runtime state / third-party code, contains auth tokens).

## Virtual test fixtures (`virtual_sensors.yaml` / `virtual_binary_sensors.yaml`)

hass-virtual prefixes every entity_id with `virtual_`:

| Entity | class | purpose |
|---|---|---|
| `sensor.virtual_fridge_power` | power | single-source aggregation target |
| `sensor.virtual_fridge_energy` | energy | fail-closed / spike-filter target |
| `sensor.virtual_garden_water` | water | fail-closed target |
| `sensor.virtual_battery_charge_power` / `sensor.virtual_battery_discharge_power` | power | REQ-CORE-005 net-flow subtraction |
| `sensor.virtual_fallback_power_source` | power | REQ-COMP-004 fallback source |
| `binary_sensor.virtual_fallback_condition` | — | REQ-COMP-004 fallback condition entity |

Set a value from an automation, script, or the E2E test itself:

```yaml
service: virtual.set
target:
  entity_id: sensor.virtual_fridge_power
data:
  value: "999"
```

(`value` must be a string per hass-virtual's service schema, even though
it holds a number.)

## Stopping / resetting

```bash
docker compose -f docker/docker-compose.demo.yml down
rm -rf docker/ha_config/.storage docker/ha_config/home-assistant_v2.db* docker/ha_config/home-assistant.log
```

(Full wipe: also delete `docker/ha_config/custom_components/virtual` and
re-run `setup-demo.sh`.)

For the E2E stack, `docker compose -f docker-compose.e2e.yml down -v` is
**not** enough on its own — `ha_config_e2e/` is a host bind mount, which
`-v` doesn't touch. Reset its state explicitly before a run that needs a
genuinely fresh instance:

```bash
docker compose -f docker-compose.e2e.yml down -v
rm -r docker/ha_config_e2e/.storage
rm -f docker/ha_config_e2e/home-assistant.log* docker/ha_config_e2e/home-assistant_v2.db*
```
