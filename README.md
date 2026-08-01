# AbstrHActor

The `abstractor` custom integration creates stable, hardware-independent
power, energy, and water sensors from one or more existing Home Assistant
entities. Configure it through **Settings > Devices & services**; options can
be changed without editing YAML.

Power sources fail soft to `0 W` when unavailable. Energy and water sources
fail closed to `unavailable`, and optional monotonic filtering rejects counter
drops. Multiple sources are summed, with optional inversion and fallback
behavior per config entry. Existing HA Utility Meter entities remain the
recommended consumer of abstracted energy sensors.

The integration persists a versioned support snapshot in HA storage and exposes
`abstractor.export_data` and `abstractor.import_data`. Import validates and
stores that snapshot but deliberately does not recreate config entries
automatically. Home Assistant does not provide a safe public API for recreating
an entry while preserving its registry identity and recorder history.

See `docs/REQUIREMENTS_COVERAGE.md` for the full FA/NFA audit.

Existing YAML entities are not automatically migrated. A custom integration
cannot safely claim an existing YAML entity's registry identity or history
without explicit, installation-specific registry migration. Configure new
entries with the intended stable IDs and migrate consumers deliberately.
