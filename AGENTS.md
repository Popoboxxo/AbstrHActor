# AbstrHActor

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



<!-- agent-meta:managed-begin -->
> **ROUTING:**

 Opencode->AGENTS.md |

> **ENTRY:** `orchestrator`-Agent (für alle Dev-Tasks).
`agent-meta v0.90.1` | DoD: `rapid-prototyping` | REQ-Trace: `false`

## Agent Directory
> ⚠️ **ACHTUNG:** Agenten (Prompts) liegen in `.gemini/agents bzw. .opencode/agents`.

| Agent | Core Capabilities |
|-------|-------------------|

| `agent-meta-manager` | agent-meta verwalten: Upgrade, Sync, Feedback, projektspezifische Agenten anl... |

| `bug-feature-analyzer` | Issue-Triage: Eingehende Bug-Meldungen und Feature-Requests analysieren und k... |

| `code-reviewer` | Clean Code Gatekeeper: Blast-Radius-Analyse, SOLID/DRY Prüfung, Code-Qualität... |

| `developer` | Feature-Implementierung und Bugfixes |

| `docker` | Dev-Stack verwalten, Test-Stack starten, Binary-Management, Dockerfiles erste... |

| `documenter` | CODEBASE_OVERVIEW, ARCHITECTURE, README, Erkenntnisse pflegen |

| `e2e-tester` | E2E-Tests, visuelle Regression und Accessibility-Audits via Playwright |

| `explorer` | Read-only Codebase-Recherche, Dependency- und Impact-Mapping, Datei- und Symb... |

| `feature` | Feature-Lifecycle-Subagent: Branch → REQ → TDD → Dev → Validate → PR |

| `feedback` | Projekt-Feedback standardisieren: Bugs, Features, Verbesserungen als GitHub I... |

| `git` | Commits, Branches, Tags, Push/Pull und alle Git-Operationen |

| `ideation` | Neue Ideen explorieren, Vision schärfen, Übergabe an requirements |

| `intern-developer` | [EASTER EGG / GAG] Der übereifrige Praktikant |

| `junior-developer` | Triviale Code-Änderungen (≤2 Dateien, kein Architektur-Impact) |

| `knowledge-curator` | Strategische Knowledge-Engine-Steuerung: Schema-Evolution, Wiki-Strukturierun... |

| `knowledge-gardener` | Kleinteilige Wiki-Pflege: Links reparieren, Tags harmonisieren, Frontmatter e... |

| `knowledge-indexer` | Pflegt index.md (Content-Katalog, OKF §6) und log.md (Chronologisches Event-L... |

| `knowledge-ingestor` | Sources einlesen, Key Information extrahieren, Wiki-Seiten erstellen/ aktuali... |

| `knowledge-linter` | Wiki-Gesundheitscheck: Widersprüche, Orphans, veraltete Claims, kaputte Links... |

| `knowledge-migrator` | Vorhandene Projektinhalte aufräumen und OKF-konform ins Knowledge Wiki migrieren |

| `knowledge-querier` | Fragen gegen das Knowledge Wiki beantworten |

| `log-analyzer` | System- und Applikations-Logs analysieren: Frequency-Clustering, Severity-Kla... |

| `meta-feedback` | Verbesserungsvorschläge für agent-meta als GitHub Issues einreichen |

| `orchestrator` | Einstiegspunkt für alle Entwicklungsaufgaben |

| `release` | Versioning, Changelog, Build-Artifact, GitHub Release erstellen |

| `requirements` | Anforderungen aufnehmen, REQ-IDs vergeben, REQUIREMENTS.md pflegen |

| `senior-developer` | Komplexe Features, Architektur-Entscheidungen, schwierige Bugs, Cross-Cutting... |

| `technical-writer` | Externe entwickler- und nutzergerichtete Doku: API-Referenzen, Getting-Starte... |

| `tester` | TDD, Test-Suite ausführen, Testabdeckung sichern |

| `ui-ux-designer` | UI-Spezifikationen, Mockups und Design-Systeme erstellen. |


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


## Regeln

# A2A Anti-Re-Delegation Gates

1. Limit depth to 10, no self-handoff.
2. Short payload: `payload.t` max 300 Zeichen.
3. No Re-Delegation (payload starts with "Du bist...").
4. Singleton Orchestrator: NUR der `main_chat` darf den `orchestrator` spawnen.
5. Execution-Trace-Isolation: Worker-Output muss strukturiert sein (STATUS, RESULT, ARTIFACTS). Keine rohen Logs propagieren.



# Branch-Guard

Verwende Feature-Branches (`feat/`, `fix/`, `chore/`). Keine Code-Änderungen direkt auf `main` oder `master`.



# Commit-Konventionen

Verwende Conventional Commits (feat, fix, chore).
Beschreibungssprache: `English`
Max 72 Zeichen in erster Zeile. Imperativ.

Format: `<type>: <beschreibung>` (Bsp: `feat: ...`)




# Definition of Done (DoD)

Pflicht: Code komplett, Konventionen & Conv. Commits eingehalten, keine Regressions.







# GitHub Issue Lifecycle

Issues referenzieren und am Ende mit passendem Keyword (`Fixes #123`, `Closes #123`) im PR oder Commit schließen. Kommentiere das Issue nach Fertigstellung.



# Sprachregeln

| Kontext | Sprache |
|---|---|
| User-Kommunikation | **English** |
| User-Input | **English** |
| Externe Doku | **English** |
| Interne Doku | **English** |
| Code/Commits | **English** |



# Lifecycle-Tasks

Beim Start prüfen: existiert `.opencode/pending-tasks.md`?
Falls ja und enthält `- [ ]`: User fragen ob delegiert werden soll.
Nach Erledigung: löschen. Datei nicht committen.



# No Worktree Isolation

**Anti-Pattern:** Niemals das Argument `isolation: "worktree"` beim Spawnen von Subagenten verwenden.
**Grund:** Agenten schreiben dann ihren Output in den internen Ordner `.claude/worktrees/agent-<id>/` anstatt in das eigentliche Projektverzeichnis. Das führt zu fehlgeleiteten Dateien und Datenverlust in der eigentlichen Codebase.

Alle Agenten müssen direkt im Projektverzeichnis arbeiten (Isolation deaktivieren oder weglassen). Der `.claude/` Ordner (sowie `.gemini/`, `.continue/`, `.mammouth/` etc.) ist strikt als Infrastruktur-Ordner zu betrachten und darf nicht für Arbeitskopien missbraucht werden.



# Provider-Agnostic Policy

Generische Templates in `1-generic/` müssen provider-agnostisch sein. Keine spezifischen Prompts für Claude, Gemini etc., außer als Fallback/Feature-Flag.



# Python Conventions

PEP8 einhalten. Type Hints (typing) verwenden. Docstrings für Klassen/Methoden schreiben.



# Session-Abschluss

Delegate Session-Zusammenfassung an `documenter` am Ende großer Features, um CODEBASE_OVERVIEW.md aktuell zu halten.



# Submodule-Schutzkonzept

Regeln für den Umgang mit dem `.agent-meta`-Submodul und `.gitmodules`:

- **Keine direkten Änderungen in `.agent-meta/`:** Dateien in `.agent-meta/` dürfen in Konsumenten-Repositories niemals direkt editiert oder committet werden.
- **Keine Mutation von `.gitmodules` / Git Staging:** `.gitmodules` darf nicht automatisch modifiziert werden und Submodule dürfen nicht automatisch via `git add` gestaged werden.
- **Kein Source-Code-Scaffolding in Konsumenten-Projekten:** In Konsumenten-Projekten wird kein Anwendungscode generiert/gerüstet; verwaltet werden ausschließlich `.meta-config/project.yaml` und die Managed Blocks.
- **Framework-Änderungen nur im agent-meta Repo:** Änderungen am agent-meta Framework müssen auf Feature-Branches im agent-meta Repository selbst durchgeführt werden.




# CRITICAL GATE
MAIN CHAT darf nicht selbst editieren. ALLES -> `orchestrator`. Keine Ausnahmen.




## Git Delegation
Git Mutationen (commit, push, add etc) -> `git` Agent. Read-only (status, log) im Main Chat ok.



Native Extensions (Skills/Hooks) erlaubt, ignorieren nicht Branch-Guard/DoD.





Anti-Recursion: Worker dürfen nicht an `orchestrator` zurück delegieren.


## Anti-Patterns
- **Worktree Isolation:** Niemals `isolation: "worktree"` bei Subagenten verwenden (schreibt in interne Infrastruktur-Ordner, führt zu Datenverlust).





<!-- agent-meta:managed-end -->













## MCP-Server

Folgende MCP-Server sind aktiv (`opencode.json` + `.opencode/mcp.local.json`):

| Server | Typ | Zweck |
|--------|-----|-------|
| `reqogniloom` | remote (SSE) | Requirements, Architektur, Tests, Traceability |

**ReqogniLoom:** Siehe `.opencode/instructions/reqogniloom-mcp.md` für Tool-Referenz und Usage-Hints (Allowed/Blocked Tools, Anwendungsfälle).

## Eigene Notizen

Hier kannst du eigene, projektspezifische Notizen eintragen. Dieser Bereich wird von `agent-meta` nicht überschrieben!

<!-- agent-meta:bootstrap-begin -->

## Agent Bootstrap — Session-Start Pflicht

Gemini/Antigravity benötigt eine einmalige Agent-Registrierung pro Session.
**Führe folgende Schritte zu Beginn JEDER Session aus:**

1. Lies alle Agenten-Dateien aus `.gemini/agents/`:
   - `agent-meta-manager.md` → registriere als `agent-meta-manager`
   - `change-manager.md` → registriere als `change-manager`
   - `code-reviewer.md` → registriere als `code-reviewer`
   - `developer.md` → registriere als `developer`
   - `docker.md` → registriere als `docker`
   - `documenter.md` → registriere als `documenter`
   - `e2e-tester.md` → registriere als `e2e-tester`
   - `explorer.md` → registriere als `explorer`
   - `git.md` → registriere als `git`
   - `ideation.md` → registriere als `ideation`
   - `intern-developer.md` → registriere als `intern-developer`
   - `junior-developer.md` → registriere als `junior-developer`
   - `knowledge-curator.md` → registriere als `knowledge-curator`
   - `knowledge-gardener.md` → registriere als `knowledge-gardener`
   - `knowledge-indexer.md` → registriere als `knowledge-indexer`
   - `knowledge-ingestor.md` → registriere als `knowledge-ingestor`
   - `knowledge-linter.md` → registriere als `knowledge-linter`
   - `knowledge-migrator.md` → registriere als `knowledge-migrator`
   - `knowledge-querier.md` → registriere als `knowledge-querier`
   - `log-analyzer.md` → registriere als `log-analyzer`
   - `meta-feedback.md` → registriere als `meta-feedback`
   - `orchestrator.md` → registriere als `orchestrator`
   - `quality-auditor.md` → registriere als `quality-auditor`
   - `release.md` → registriere als `release`
   - `requirements-architect.md` → registriere als `requirements-architect`
   - `risk-analyst.md` → registriere als `risk-analyst`
   - `senior-developer.md` → registriere als `senior-developer`
   - `technical-writer.md` → registriere als `technical-writer`
   - `test-engineer.md` → registriere als `test-engineer`
   - `ui-ux-designer.md` → registriere als `ui-ux-designer`

2. Registriere jeden Agenten via define_subagent API-Call:
   ```
   define_subagent(name="agent-meta-manager", ...)
   define_subagent(name="change-manager", ...)
   define_subagent(name="code-reviewer", ...)
   define_subagent(name="developer", ...)
   define_subagent(name="docker", ...)
   define_subagent(name="documenter", ...)
   define_subagent(name="e2e-tester", ...)
   define_subagent(name="explorer", ...)
   define_subagent(name="git", ...)
   define_subagent(name="ideation", ...)
   define_subagent(name="intern-developer", ...)
   define_subagent(name="junior-developer", ...)
   define_subagent(name="knowledge-curator", ...)
   define_subagent(name="knowledge-gardener", ...)
   define_subagent(name="knowledge-indexer", ...)
   define_subagent(name="knowledge-ingestor", ...)
   define_subagent(name="knowledge-linter", ...)
   define_subagent(name="knowledge-migrator", ...)
   define_subagent(name="knowledge-querier", ...)
   define_subagent(name="log-analyzer", ...)
   define_subagent(name="meta-feedback", ...)
   define_subagent(name="orchestrator", ...)
   define_subagent(name="quality-auditor", ...)
   define_subagent(name="release", ...)
   define_subagent(name="requirements-architect", ...)
   define_subagent(name="risk-analyst", ...)
   define_subagent(name="senior-developer", ...)
   define_subagent(name="technical-writer", ...)
   define_subagent(name="test-engineer", ...)
   define_subagent(name="ui-ux-designer", ...)
   ```

3. Erst danach: Bearbeite User-Anfragen (Delegation an Orchestrator etc.)

> **Ohne diese Registrierung existieren die Agenten NICHT in der Runtime**
> und der Orchestrator kann nicht delegieren.
<!-- agent-meta:bootstrap-end -->


<!-- headroom:rtk-instructions -->
# RTK (Rust Token Killer) - Token-Optimized Commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60-90% with zero behavior change. If rtk has no filter for a command,
it passes through unchanged — so it is always safe to use.

## Key Commands
```bash
# Git (59-80% savings)
rtk git status          rtk git diff            rtk git log

# Files & Search (60-75% savings)
rtk ls <path>           rtk read <file>         rtk grep <pattern>
rtk find <pattern>      rtk diff <file>

# Test (90-99% savings) — shows failures only
rtk pytest tests/       rtk cargo test          rtk test <cmd>

# Build & Lint (80-90% savings) — shows errors only
rtk tsc                 rtk lint                rtk cargo build
rtk prettier --check    rtk mypy                rtk ruff check

# Analysis (70-90% savings)
rtk err <cmd>           rtk log <file>          rtk json <file>
rtk summary <cmd>       rtk deps                rtk env

# GitHub (26-87% savings)
rtk gh pr view <n>      rtk gh run list         rtk gh issue list

# Infrastructure (85% savings)
rtk docker ps           rtk kubectl get         rtk docker logs <c>

# Package managers (70-90% savings)
rtk pip list            rtk pnpm install        rtk npm run <script>
```

## Rules
- In command chains, prefix each segment: `rtk git add . && rtk git commit -m "msg"`
- For debugging, use raw command without rtk prefix
- `rtk proxy <cmd>` runs command without filtering but tracks usage
<!-- /headroom:rtk-instructions -->
