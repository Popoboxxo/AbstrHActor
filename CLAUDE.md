# AbstrHActor

> Projektbeschreibung für Claude-Agenten. Diese Datei ist die **einzige Quelle**
> für projektspezifischen Kontext — Agenten lesen sie, statt eigenen Kontext zu haben.
>
> Generiert von agent-meta v0.95.0 — `2026-08-12`
>
> **Längenempfehlung:** 200–500 Zeilen optimal. Über 500 Zeilen → Detailwissen in
> `docs/ARCHITECTURE.md`, `docs/API.md` o.ä. auslagern und manuell verlinken.
> Agent-spezifisches Wissen → `.claude/3-project/<rolle>-ext.md` (Extension).
>
> **CLAUDE.md Hierarchie (Claude Code lädt in dieser Reihenfolge):**
> 1. `~/.claude/CLAUDE.md` — global, alle Projekte (~50 Zeilen max, persönliche Präferenzen)
> 2. `<projekt>/CLAUDE.md` — diese Datei, projektspezifisch (von agent-meta verwaltet)
> 3. `<ordner>/CLAUDE.md` — optional in Unterordnern (z.B. `src/backend/CLAUDE.md`)

---

## Eigene Notizen

Hier kannst du eigene, projektspezifische Notizen eintragen. Dieser Bereich wird von `agent-meta` nicht überschrieben!

---

## Projekt

**Name:** AbstrHActor
**Präfix:** Absrct
**Plattform:** Home Assistant
**Beschreibung:** A Home Assistant integration that abstracts physical devices (sensors, actuators) behind a unified interface. Implements hardware/software decoupling so that the concrete sensor hardware (e.g., Zendure, Shelly, Tasmota) can be swapped without changing automation logic, dashboards, or utility meters.


## Tech-Stack

- **Runtime:** Python 3.12+
- **Sprache:** Python
- **Key-Dependencies:** - homeassistant >= 2025.1 - aiohttp (HA internal) - pyserial (for serial/UART sensors) - paho-mqtt (for MQTT sensor bridge)


## Architektur

```
# Root — HACS requirements hacs.json              # HACS manifest (name, homeassistant version, etc.) custom_components/abstractor/
  __init__.py          # async_setup_entry, async_unload_entry
  manifest.json        # HA manifest (domain, version, requirements, iot_class)
  const.py             # DOMAIN, CONF_*, SENSOR_TYPES enum
  config_flow.py       # ConfigFlow with unique ID, discovery steps
  strings.json         # Config flow translations (i18n)
  icons.json           # Entity icon translations (mdi icons)
  sensor.py            # Sensor platform — CoordinatorEntity + EntityDescription
  binary_sensor.py     # Binary sensor platform
  switch.py            # Switch/actuator platform
  coordinator.py       # DataUpdateCoordinator — central polling
  device.py            # Abstract device representation
  brand/
    icon.png           # Brand icon for HACS UI (256x256)
    logo.png           # Brand logo (optional)
  bridge/
    __init__.py        # AbstractBridge protocol
    serial_bridge.py   # Serial/UART bridge implementation
    mqtt_bridge.py     # MQTT bridge implementation
    http_bridge.py     # HTTP/REST bridge implementation
  sensor_types/
    __init__.py        # SensorType enum + EntityDescription registry
    temperature.py     # Temperature sensor implementation
    humidity.py        # Humidity sensor implementation
    pressure.py        # Pressure sensor implementation
    power.py           # Power/energy sensor implementation
    water.py           # Water flow/consumption sensor implementation
  repository/
    __init__.py        # Device registry (Repository pattern)
    device_registry.py # In-memory device registry + discovery
  tests/
    __init__.py
    test_config_flow.py# Config flow tests (required: 100% coverage)
    test_sensor.py     # Sensor unit tests
    test_bridge.py     # Bridge implementation tests
    test_device.py     # Device abstraction tests
    conftest.py        # Pytest fixtures (mock HA, mock bridges)
docs/
  ARCHITECTURE.md      # High-level architecture docs
  SENSOR_TYPES.md      # Supported sensor types and their interfaces
requirements.txt       # PyPI dependencies requirements_test.txt  # Test dependencies (pytest, pytest-asyncio, pytest-cov) .github/
  workflows/
    validate.yaml      # HACS Action + Hassfest validation on push/PR

```

**Entry-Point:**
```
custom_components/abstractor/__init__.py
```

**Besondere Patterns:**
- **Bridge Pattern**: Separates hardware communication (serial, MQTT, HTTP)
  from the sensor abstraction. Each bridge implementation translates between
  raw hardware protocols and a unified `AbstractSensor` interface.
- **Strategy Pattern**: Each sensor type (temperature, power, water, etc.)
  implements a common `AbstractSensor` base class, allowing polymorphic
  sensor access from automations and dashboards.
- **Repository Pattern**: A central `DeviceRegistry` manages all discovered
  devices, handles deduplication, and provides lookup by device ID, type,
  or location.
- **Adapter Pattern (HA native)**: Leverages Home Assistant's own entity
  registry to expose abstract sensors as first-class HA entities with
  proper device_class, state_class, and unit_of_measurement.
- **DataUpdateCoordinator (HA)**: Central polling coordinator shared by all
  entities. Single `_async_update_data` call fetches all device data once,
  then dispatches to entities via CoordinatorEntity. Avoids N parallel polls.
- **EntityDescription (declarative)**: Sensor types defined as dataclass
  lists with `key`, `value_fn`, `device_class`, `state_class`, etc. No
  repetitive boilerplate per entity.
- **Config Flow with Unique ID**: Every config entry has a stable unique_id
  (serial/MAC, never IP). Supports discovery (USB, DHCP, MQTT) and reauth.
- **Spike Filter / Monotonic Guard**: Energy and water sensors include
  monotonically-increasing guards to prevent counter resets from corrupting
  utility meter totals — battle-proven from production HA deployment.
- **HACS Delivery**: GitHub releases with semantic versioning. `hacs.json`
  with min HA version. `brand/` directory with icon. GitHub Actions for
  HACS Action + Hassfest validation on every push/PR.


## Code-Konventionen

- PEP 8, Ruff formatting, type hints everywhere (PEP 604 syntax) - Google-style docstrings for all public classes/methods - Async-first: all bridge I/O uses asyncio (aiohttp, asyncio serial) - has_entity_name = True (HA mandatory for new integrations) - Entity names: only the data point (e.g., "Power usage"), never include device name - Sensor types as EntityDescription dataclass lists (declarative, no boilerplate) - DataUpdateCoordinator for central polling (never per-entity polling) - ConfigFlow with stable unique_id (serial/MAC, never IP) - No `from x import *` — explicit imports only - All sensor values validated before exposure (NaN, None, unavailable) - Logging: _LOGGER.debug for non-user-facing, _LOGGER.error for failures - Log formatting: use %s style (not f-strings) for _LOGGER calls - f-strings everywhere else (never % or str.format) - Config flow needs 100% test coverage


## Build & Development

```bash
# Build
pip install -e . && python3 -m script.hassfest --integration-path custom_components/abstractor

# Tests
pytest tests/ -v --cov=custom_components/abstractor --cov-report=term-missing

# Dev-Stack starten
# Start Home Assistant dev instance with custom component linked hass -c config/ --debug # Or via Docker with volume mount: # docker compose -f config/docker-compose.yml up -d


# Nach Änderungen neu laden
# Reload custom_component without full restart: # Option A: Core UI → Developer Tools → YAML → "Reload custom components" # Option B: HA CLI ha core restart # Option C: Docker compose docker compose -f config/docker-compose.yml restart # Option D: Touch reload flag (HA Core dev mode) touch config/.HA_RELOAD  # triggers core config reload

```

## Anforderungs-Kategorien

Kategorien für `docs/REQUIREMENTS.md`:

- Core features: device discovery, sensor polling, config flow - Bridge implementations: serial, MQTT, HTTP - Sensor types: temperature, humidity, pressure, power, water - Non-functional: async performance, memory safety, HA core compliance



## Agenten-Konfiguration

<!-- agent-meta:managed-begin -->
<!-- Dieser Block wird von sync.py bei jedem sync automatisch aktualisiert. -->
<!-- Manuelle Änderungen hier werden überschrieben. -->

> **AI ROUTING:** Claude -> CLAUDE.md | Gemini, Opencode -> AGENTS.md

Generiert von agent-meta v0.95.0 — `2026-08-12`
DoD-Preset: **rapid-prototyping** | REQ-Traceability: false | Tests: false | Codebase-Overview: false | Security-Audit: false
> **Einstiegspunkt:** Du bist im `main-chat` Modus. Du agierst direkt als Router und Worker (siehe `use-orchestrator.md`).

## Knowledge Engine

Die Knowledge Engine ist aktiviert. Domäne: **internal-docs**.

**Bundle-Pfad:** `knowledge/`
| Pfad | Zweck |
|------|-------|
| `knowledge/schema.md` | Steuerungsdokument — Konventionen, Concept Types, Workflows |
| `knowledge/sources/` | Immutable Raw Sources — LLM liest, modifiziert NIEMALS |
| `knowledge/wiki/` | OKF Knowledge Bundle — LLM-owned, strukturiertes Wiki |
| `knowledge/wiki/index.md` | Content-Katalog aller Wiki-Seiten (OKF §6) |
| `knowledge/wiki/log.md` | Chronologisches Event-Log (OKF §7) |

### Knowledge-Agenten
- **Schema-Owner:** `knowledge-curator` verwaltet `knowledge/schema.md` und Concept-Type-Konventionen

### Knowledge-Workflows
- **Ingest:** Source in `knowledge/sources/` ablegen → `knowledge-ingestor` verarbeitet → Wiki aktualisiert
- **Query:** Frage stellen → `knowledge-querier` durchsucht Index → synthetisiert Antwort
- **Lint:** `knowledge-linter` prüft Wiki-Gesundheit (Widersprüche, Orphans, OKF-Compliance)
- **Migration:** `knowledge-migrator` räumt vorhandene Inhalte auf und migriert ins OKF-Format
- **Gardening:** `knowledge-gardener` pflegt Links, Tags, Typos, Timestamps
<!-- agent-meta:managed-end -->
