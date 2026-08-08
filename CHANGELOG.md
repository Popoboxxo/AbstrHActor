# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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

