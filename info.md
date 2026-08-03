# Abstractor

Abstractor creates **stable, hardware-independent power, energy, and water
sensors** from one or more existing Home Assistant entities. It acts as a
software abstraction layer between your physical hardware and your dashboards,
automations, and utility meters: when a device fails or is replaced, you
re-map the abstract sensor to a new source in the UI — your logic, entities,
and long-term statistics keep working unchanged.

Everything is configured through **Settings > Devices & services**. No YAML
required.

## Supported sensor types

| Type | Unit | State class | Unavailable-source behavior |
|------|------|-------------|-----------------------------|
| Power | W | Measurement | Fails soft to `0` |
| Energy | kWh | Total increasing | Fails closed to `unavailable` |
| Water | L | Total increasing | Fails closed to `unavailable` |

## Key features

- **Spike filter** — a monotonic guard rejects counter drops below the last
  valid value, so flickering smart plugs can never corrupt your utility meter
  totals.
- **Aggregation** — select multiple source entities and they are summed into
  one abstract sensor (e.g. several sockets of a power strip).
- **Inversion** — multiply values by -1 to model net flows (load minus feed-in).
- **Fallback to zero** — report `0` instead of `unavailable` when no source
  delivers a value.
- **Config Flow** — add devices and swap hardware through the UI, with stable
  unique IDs and an options flow for later reconfiguration.
- **Export / Import** — `abstractor.export_data` / `abstractor.import_data`
  persist and restore a versioned snapshot of all mappings and values.
- **Diagnostics** — native HA diagnostics download for support and debugging.
- **Clean integration** — data is stored in HA `.storage/` and all entities are
  grouped into logical devices via the HA device registry.

## Documentation & support

- [Full documentation](https://github.com/Popoboxxo/AbstrHActor)
- [Requirements specification](https://github.com/Popoboxxo/AbstrHActor/blob/main/docs/REQUIREMENTS.md)
- [Requirements coverage audit](https://github.com/Popoboxxo/AbstrHActor/blob/main/docs/REQUIREMENTS_COVERAGE.md)
- [Report an issue](https://github.com/Popoboxxo/AbstrHActor/issues)
