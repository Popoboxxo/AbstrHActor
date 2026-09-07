# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-09-07

### Added

- Options flow for configuring the polling interval, Influx exporter
  credentials and device settings directly from the UI
- Influx exporter is now activated at setup when credentials are configured
- Poll interval from the options flow is applied by the coordinator
- Device registry wired into the sensor lifecycle (devices registered from
  config options)
- Subentry-based device bundling: sensors can now be mapped onto a shared
  device from the reconfigure flow, with safe detach/re-attach handling that
  protects other devices' entity history —
  [GH#18](https://github.com/Popoboxxo/AbstrHActor/issues/18)
- Reconfigure flow for editing settings and moving a sensor to another device
- Sidebar panel action hub: export and import snapshots as JSON files
  directly from the panel, jump to a device's native Home Assistant page to
  edit it, and add a new sensor — without leaving the panel

### Fixed

- Coordinator setup no longer crashes on current Home Assistant (config-entry
  leak)
- E2E suite no longer boots HA into recovery mode
- Removed invalid `homeassistant` key from manifest.json (hassfest failure)
- Legacy unique_id is pinned through reconfigure; sensors disabled by the
  user stay disabled
- Device group is preserved when a sensor is reconfigured
- Subentry flow works on both HA 2025.3.0 and 2026.8.0
- **Migration foundation:** Four critical bugs found and fixed during the
  subentry migration (coordinator leak, entity registry corruption, state
  persistence, and unique_id stability) before this release went live
- InfluxDB host is now validated everywhere: an `http(s)://` scheme is
  required, and the scheme check is case-insensitive
- New sensors get a stable identity at creation time instead of it drifting
  on first reconfigure — [GH#19](https://github.com/Popoboxxo/AbstrHActor/issues/19)
- Spike-filter guard for energy/water sensors is restored from its persisted
  snapshot after a restart instead of resetting, preventing false utility
  meter spikes
- Diagnostics no longer mix up pipeline configuration between subentries
- A sensor with a missing device type now logs a warning and falls back
  safely instead of behaving inconsistently

### Changed

- Influx token is masked in diagnostics
- Coordinator is keyed by subentry_id instead of entry_id
- Minimum HA version raised to 2025.3.0

### Removed

- (None in this release)

## [1.0.0] — 2026-08-08

### Added

- Sidebar panel UI component for Abstractor configuration and diagnostics
- Comprehensive E2E test suite using Playwright and Docker integration
- Config flow with stable unique ID support including fallback and migration strategies
- Power, energy, and water abstract sensor types, each with device-class/unit/state-class
  mapping appropriate to that measurement
- Device registry and repository pattern for hardware abstraction
- DataUpdateCoordinator for centralized polling and entity updates
- Spike filter and monotonic guards for energy and water sensors
- Export/import snapshot services for backup and restore
- Diagnostics integration for troubleshooting
- GitHub Actions CI/CD workflow for HACS and Hassfest validation

### Fixed

- Config flow options handler read-only property setter validation
- HACS manifest keys (removed invalid `domain` and `iot_class` keys from hacs.json)
- UI translation strings for config and options flow labels
- Stable unique_id generation with fallback and migration support for existing devices
- E2E test suite Playwright locators for Home Assistant UI compatibility

### Changed

- Enhanced translation support with automatic loading and validation
- Improved E2E test resilience and Docker integration

### Removed

- (None in this release)

---

## Versioning

Versions follow [Semantic Versioning](https://semver.org/). See [RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) for detailed release workflows.

