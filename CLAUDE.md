# AbstrHActor

> Projektbeschreibung für Claude-Agenten. Diese Datei ist die **einzige Quelle**
> für projektspezifischen Kontext — Agenten lesen sie, statt eigenen Kontext zu haben.
>
> Generiert von agent-meta v0.101.0-beta.5 — `2026-09-05`
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
- **Key-Dependencies:** - homeassistant >= 2025.1 - aiohttp (HA internal) - voluptuous (config flow schemas)


## Architektur

```
# Root
hacs.json                  # HACS manifest (name, homeassistant version, etc.)
custom_components/abstractor/
  __init__.py          # async_setup_entry, async_unload_entry
  manifest.json        # HA manifest (domain, version, requirements, iot_class)
  const.py             # DOMAIN, CONF_*, SENSOR_TYPES enum
  config_flow.py       # ConfigFlow with unique ID, discovery steps
  coordinator.py       # DataUpdateCoordinator — central polling
  diagnostics.py       # Diagnostics support
  filters.py           # Value filters (spike filter, monotonic guard)
  frontend.py          # Frontend integration entry point
  influx_exporter.py   # InfluxDB exporter
  sensor.py            # Sensor platform — CoordinatorEntity + EntityDescription
  snapshot.py          # Snapshot support
  services.yaml        # Service definitions
  strings.json         # Config flow translations (i18n)
  icons.json           # Entity icon translations (mdi icons)
  repository/
    device_registry.py # Device registry (Repository pattern)
  brand/
    icon.png           # Brand icon for HACS UI (256x256)
    logo.png           # Brand logo (optional)
  translations/        # Translation catalogs
  www/                 # Frontend static assets
  # PLANNED / roadmap (do not exist yet):
  bridge/              # AbstractBridge protocol + serial/mqtt/http bridges
  sensor_types/        # SensorType enum + EntityDescription registry
tests/                 # 14 test files (root-level)
  __init__.py
  conftest.py          # Pytest fixtures (mock HA, mock bridges)
  test_config_flow.py  # Config flow tests (required: 100% coverage)
  test_coordinator.py
  test_diagnostics.py
  test_filters.py
  test_frontend.py
  test_influx_exporter.py
  test_lifecycle.py
  test_migration.py
  test_reconciliation.py
  test_sensor.py
  test_services.py
  test_snapshot.py
docs/
  ARCHITECTURE.md      # High-level architecture docs
  SENSOR_TYPES.md      # Supported sensor types and their interfaces
.github/
  workflows/
    validate.yaml      # HACS Action + Hassfest validation on push/PR
```

**Entry-Point:**
```
custom_components/abstractor/__init__.py
```

**Besondere Patterns:**
- **Singleton root + subentries**: one root ConfigEntry (unique_id ROOT_UNIQUE_ID)
  holds every Abstract sensor as a ConfigSubentry, created/edited through
  ConfigSubentryFlow rather than per-sensor config entries.
- **DataUpdateCoordinator (HA)**: one shared coordinator polls all subentries'
  sources every poll interval; a single _async_update_data call updates every
  sensor's cached value, avoiding N parallel polls.
- **Filter pipeline (AbstractorFilterPipeline)**: per-subentry spike filter,
  invert, fail-soft/fail-closed, net-subtract, and REQ-COMP-004 fallback-source
  logic, applied per poll in coordinator.py.
- **Stable identity via CONF_LEGACY_UNIQUE_ID**: every subentry's unique_id is
  pinned at creation (auto-generated, or explicitly set for migrated sensors)
  and never re-derived from source entity ids afterward, so a later hardware
  swap via reconfigure cannot orphan the entity or its recorder history.
- **In-memory DeviceRegistry**: a lightweight write-side device registry
  (custom_components/abstractor/repository/device_registry.py) records
  device metadata as sensors are created; HA's own device registry (via
  DeviceInfo) is the actual source of truth for entity/device grouping.
- **Config Flow with a singleton root unique_id**: the root entry uses a
  fixed unique_id (ROOT_UNIQUE_ID); there is currently no discovery step
  (USB/DHCP/MQTT) or reauth flow.
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

Generiert von agent-meta v0.101.0-beta.5 — `2026-09-05`
DoD-Preset: **rapid-prototyping** | REQ-Traceability: false | Tests: true | Codebase-Overview: false | Security-Audit: false
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

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
