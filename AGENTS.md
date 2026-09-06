# AbstrHActor

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

- Core features: device discovery, sensor polling, config flow - Device Bundling: subentry-based sensor creation, legacy-entry migration - Sensor types: power, energy, water - Non-functional: async performance, memory safety, HA core compliance



<!-- agent-meta:managed-begin -->
> **ROUTING:**

 Opencode->AGENTS.md |
 Gemini->AGENTS.md
> **ENTRY:** `orchestrator`-Agent (für alle Dev-Tasks).
`agent-meta v0.101.0-beta.5` | DoD: `rapid-prototyping` | REQ-Trace: `false`


## Regeln

# A2A Anti-Re-Delegation Gates

1. Limit depth to 10, no self-handoff.
2. Short payload: `payload.t` max 300 Zeichen.
3. No Re-Delegation (payload starts with "Du bist...").
4. Singleton Orchestrator: NUR der `main_chat` darf den `orchestrator` spawnen.
5. Execution-Trace-Isolation: Worker-Output muss strukturiert sein (STATUS, RESULT, ARTIFACTS). Keine rohen Logs propagieren.

## Bekannte Grenzen

- **Tiefenlimit (Punkt 1) ist modellbasiert, keine technische Barriere.** Eine passende Implementierung existiert (`validate_envelope(max_depth=...)` in `scripts/lib/delegation_syntax.py`), wird aber im aktiven Delegationspfad nirgends aufgerufen. Die Regel verlässt sich auf Modell-Gehorsam, nicht auf Enforcement.
- **Singleton-Orchestrator (Punkt 4) wird nur über eine Selbstdeklaration der Agenten-Identität gestützt** (`#agent-meta:agent=<name>` in `.claude/hooks/orchestrator-guard.sh`), die im Hook-Quelltext selbst als "soft, self-reported convention, not a security boundary" dokumentiert ist. Jeder Agent kann sich technisch als privilegiert deklarieren. **Das ist eine bewusste Design-Grenze, kein behebbarer Bug:** kein Provider liefert im PreToolUse-Payload eine echte Agenten-Identität, der Hook kann die Behauptung also nicht verifizieren. Der Guard ist ein Konventions-Schutz gegen Versehen, kein Schutz gegen einen Agenten, der die Regel bewusst umgeht. Wer eine harte Grenze braucht, muss Git-Mutationen außerhalb des Agenten-Systems absichern (Branch-Protection, Pre-Receive-Hooks, Review-Pflicht) — zerstörerische Operationen (`push --force`, `reset --hard`, `clean -fd`, `branch -D`) bleiben deshalb ausdrücklich zustimmungspflichtig durch den Nutzer.
- **Große Ergebnisse gehören in Dateien, nicht in den Return-Channel.** Der synchrone Tool-Result-Kanal hat ein undokumentiertes Größenlimit; überlange Antworten können ohne Fehlersignal beschnitten zurückkommen (agent-meta #514). Read-only-Rollen ohne `Write` (`Plan`, `Explore`, `code-reviewer`) sind davon strukturell betroffen. Daher: Artefakte ab ~1000 Zeilen (Pläne, Konzepte, Reviews) immer von einer schreibfähigen Rolle in eine Datei schreiben lassen und nur den Pfad zurückgeben. Empfangene Ergebnisse auf Vollständigkeit prüfen (fehlender Kopf/erste Abschnitte = Truncation), nicht blind weiterverarbeiten.



# Branch-Guard

Verwende Feature-Branches (`feat/`, `fix/`, `chore/`). Keine Code-Änderungen direkt auf `main` oder `master`.

## Guard-Terminologie: Convention Boundary vs. Security Boundary

Guards im System (Orchestrator-Guard, DoD-Push-Check, etc.) werden inkonsistent als
"Konventions-Tool" und als "security boundary" bezeichnet — beide Aussagen sind korrekt,
aber gegen unterschiedliche Bedrohungsmodelle:

- **Convention boundary**: fail-closed gegen AKZIDENTIELLEN Missbrauch (Tippfehler,
  vergessene Bestätigungen, naive Automatisierung). Nicht darauf ausgelegt, einen
  gezielten Bypass-Versuch zu widerstehen (siehe Lücken unten, z.B. #592).
- **Security boundary**: fail-closed gegen einen DELIBERATEN Umgehungsversuch.

Diese Definition ist die zentrale Referenz — Hook-Header und andere Doku sollen sie
verlinken (`.claude/rules/branch-guard.md#guard-terminologie-convention-boundary-vs-security-boundary`)
statt sie ad hoc zu wiederholen.

`orchestrator-guard.sh` ist primär eine **convention boundary** (siehe Lücken unten),
mit einzelnen **security-boundary**-Eigenschaften für spezifische Fälle (z.B. das
Destructive-Gate aus #516, das auch bei gültigem `git`-Sentinel blockt). `dod-push-check.sh`
ist als **security boundary** gegen fehlendes/kaputtes `python3` fail-closed (#595).

## Bekannte Grenzen

Die technische Durchsetzung (`orchestrator-guard.sh`) erkennt Git-Mutationen über eine tokenisierte Analyse des Bash-Befehls (gemeinsamer Tokenizer für Destructive- und Mutation-Gate, Issue #551), kein vollständiger Shell-Parser. Bekannte Lücken:

1. `eval "git commit ..."` wird nicht erkannt.
2. Direkte Schreibzugriffe auf `.git/` werden nicht geprüft.
3. Andere Git-Tools (`hub`, `gh repo ...`) sind nicht erfasst.
4. Command-Substitution und Indirektion (`$(...)`, Backticks, `xargs`, `eval`) können eine Git-Mutation am Tokenizer vorbeischleusen, weil der Hook den Befehl weder ausführt noch die Shell vollständig parst (Issue #592). Ein echter Shell-Interpreter wäre unverhältnismäßig für ein Konventions-Tool.

Bewusster Trade-off, kein Bug (siehe Kommentar-Header in `.claude/hooks/orchestrator-guard.sh`) — nur relevant für Nutzer, die sich vollständig auf den Schutz statt auf die Konvention verlassen.



# Commit-Konventionen

Verwende Conventional Commits (feat, fix, chore).
Beschreibungssprache: `English`
Max 72 Zeichen in erster Zeile. Imperativ.
Format: `<type>: <beschreibung>` (Bsp: `feat: ...`)



# Definition of Done (DoD)

Pflicht: Code komplett, Konventionen & Conv. Commits eingehalten, keine Regressions.
Tests: Test vorhanden & grün



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

Beim Start prüfen: existiert `.gemini/pending-tasks.md bzw. .opencode/pending-tasks.md`?
Falls ja und enthält `- [ ]`: User fragen ob delegiert werden soll.
Nach Erledigung: löschen. Datei nicht committen.



# MCP Hard Prohibitions

> Kurzfassung der harten Tool-Verbote aktiver MCP-Server. Vollständige Tool-Listen und
> Hinweise: siehe `.claude/skills/mcp-<server>/SKILL.md` (`use-lazy-rules.md`).

- **reqogniloom:** `workspace.close`, `workspace.reactivate`, `workspace.delete`, `permissions.set_rule`, `permissions.list`, `permissions.revoke`, `permissions.check`, `admin.backup_create`, `admin.backup_list`, `admin.restore`, `audit.query`, `audit.ai_review`, `events.dlq_list`, `events.dlq_replay`, `user.create`, `user.assign_role`, `user.list`, `user.deactivate` — absolut verboten.



# No Worktree Isolation

**Anti-Pattern:** Niemals das Argument `isolation: "worktree"` beim Spawnen von Subagenten verwenden.
**Grund:** Agenten schreiben dann ihren Output in den internen Ordner `.claude/worktrees/agent-<id>/` anstatt in das eigentliche Projektverzeichnis. Das führt zu fehlgeleiteten Dateien und Datenverlust in der eigentlichen Codebase.

Alle Agenten müssen direkt im Projektverzeichnis arbeiten (Isolation deaktivieren oder weglassen). Der `.claude/` Ordner (sowie `.gemini/`, `.continue/`, `.mammouth/` etc.) ist strikt als Infrastruktur-Ordner zu betrachten und darf nicht für Arbeitskopien missbraucht werden.



# Python Conventions

PEP8 einhalten. Type Hints (typing) verwenden. Docstrings für Klassen/Methoden schreiben.



# Session-Abschluss

Delegate Session-Zusammenfassung an `documenter` am Ende großer Features, um CODEBASE_OVERVIEW.md aktuell zu halten.



# Submodule-Schutzkonzept

Regeln für den Umgang mit allen Git-Submodulen (`.agent-meta/`, `external/*/`, und alle weiteren in `.gitmodules`):

- **Keine direkten Änderungen in Submodul-Verzeichnissen:** Dateien in `.agent-meta/`, `external/*/` und allen anderen Submodul-Pfaden dürfen in Konsumenten-Repositories niemals direkt editiert oder committet werden. Submodule sind separate Repositories mit eigenem Lifecycle (Build, Push, Deploy, Version-Tags). Änderungen MÜSSEN im Submodul-Repo selbst durchgeführt, committet und gepusht werden — danach aktualisiert das Parent-Repo die Pinned-Commit-Referenz.
- **Keine Mutation von `.gitmodules` / Git Staging:** `.gitmodules` darf nicht automatisch modifiziert werden und Submodule dürfen nicht automatisch via `git add` gestaged werden.
- **Kein Source-Code-Scaffolding in Konsumenten-Projekten:** In Konsumenten-Projekten wird kein Anwendungscode generiert/gerüstet; verwaltet werden ausschließlich `.meta-config/project.yaml` und die Managed Blocks.
- **Framework-Änderungen nur im agent-meta Repo:** Änderungen am agent-meta Framework müssen auf Feature-Branches im agent-meta Repository selbst durchgeführt werden.



# Lazy-Loaded Rules

> Nicht immer geladen — bei Bedarf per `Read` öffnen: `.claude/skills/<skill>/SKILL.md`.

| Skill | Wann |
|---|---|
| sync-interface | sync.py, Templates/Rules ändern |
| admin-ui | Admin-Server/UI betreiben (Lifecycle, Token, Ports) |
| architecture | Templates/Overrides/Placeholder ändern |
| conventions | Vor Commits in agents/, config/, scripts/lib |
| submodule-protection | .agent-meta/, external/, .gitmodules |
| a2a-delegation-gates | A2A-Delegation an Subagenten |
| python-conventions | Python-Code |
| issue-lifecycle | GitHub-Issue |
| lifecycle-tasks | Session-Start, pending-tasks.md vorhanden |
| session-conclusion | Feature-Abschluss |
| provider-agnostic | agents/1-generic editieren |
| mcp-reqogniloom | ReqogniLoom-MCP-Tools |
| mcp-honcho | Honcho-MCP-Memory-Tools |
| mcp-playwright | Playwright-MCP-Browser-Tools |
| mcp-viz-logger | viz-logger Event-Logging |
| tool-graphify | Architektur-/Datei-Fragen mit graphify |

Harte MCP-Tool-Verbote: siehe `mcp-guardrails.md` (always-on).



# Main-Chat Mode
Main Chat ist Router + Worker. Kein Orchestrator-Subagent. Du bist der Orchestrator!

## Intent Routing
> Parallel ist rein informativ — kein Runtime-Enforcement, nur CI-Konsistenzcheck bei required/recommended-Tier-Abdeckung.

**Tiers** (nicht gelistet = optional): recommended: `bug-feature-analyzer`, `code-reviewer`, `documenter`, `planner`, `requirements`, `tester`, `validator` | required: `developer`, `feedback`, `git`, `log-analyzer`, `orchestrator`

| Intent / Keywords | Agent | Tier | Parallel |
|-------------------|-------|------|----------|
| Dokumentation, README, Docs, Doku | → Pipeline: `docs-update` | pipeline | no |
| Feature implementieren, Feature bauen, neues Feature, Funktion bauen, Feature Lifecycle, komplexes Feature, Feature Pipeline | → Pipeline: `feature-lifecycle` | pipeline | no |
| Bug fixen, Bug beheben, Triage, schneller Fix, Hotfix | → Pipeline: `quick-fix` | pipeline | no |


Volle Stage-Details (Agent/Modus je Stage, Loop/Fallback/Approval-Gate) einer gematchten Pipeline bei Bedarf: `Read {{PIPELINE_DETAILS_DIR}}/<pipeline-name>.md`.

## A2A Delegation


## Plan Delegation
Plan vorhanden (`plan-*.md` oder Knowledge-Wiki Plan-Seite) -> Pipeline `feature-lifecycle` mit `payload.plan_ref`, statt neuen Lifecycle blind zu starten.

## Git Delegation
Git Mutationen (commit, push, add etc) -> `git` Agent. Read-only (status, log) im Main Chat ok.
Ausnahme auf User-Wunsch erlaubt.

Native Extensions (Skills/Hooks) erlaubt, ignorieren nicht Branch-Guard/DoD.




# MCP: reqogniloom

> ReqogniLoom requirements-engineering platform — requirements, architecture, tests, traceability and AI-assisted derivation

---

## Erlaubte Tools

- `requirement.get`
- `requirement.query`
- `requirement.create`
- `requirement.update`
- `requirement.decompose`
- `requirement.validate`
- `requirement.derive`
- `requirement.check_consistency`
- `needs.read`
- `needs.create`
- `needs.update`
- `needs.get_traces`
- `needs.derive_requirements`
- `architecture.get`
- `architecture.query`
- `architecture.create`
- `architecture.update`
- `architecture.link`
- `architecture.decompose`
- `architecture.decompose_commit`
- `test.get`
- `test.query`
- `test.create`
- `test.update`
- `test.link`
- `test.run_create`
- `test.run_get`
- `test.run_report_results`
- `test.derive_from_requirement`
- `traceability.query`
- `traceability.suggest_links`
- `artifact.search`
- `artifact.get_tree`
- `workspace.get_context`
- `adr.read`
- `adr.create`
- `adr.update`
- `adr.delete`
- `risk.read`
- `risk.create`
- `risk.update`
- `risk.delete`
- `issue.read`
- `issue.create`
- `issue.update`
- `issue.delete`
- `glossary.read`
- `glossary.create`
- `glossary.update`
- `glossary.delete`
- `prompt_template.get`
- `ai_derivation.derive_requirements_from_need`
- `ai_derivation.suggest_architecture_for_requirement`
- `ai_derivation.decompose_requirement_next_level`

## Verbotene Tools (ABSOLUT — keine Ausnahmen)

- `workspace.close`
- `workspace.reactivate`
- `workspace.delete`
- `permissions.set_rule`
- `permissions.list`
- `permissions.revoke`
- `permissions.check`
- `admin.backup_create`
- `admin.backup_list`
- `admin.restore`
- `audit.query`
- `audit.ai_review`
- `events.dlq_list`
- `events.dlq_replay`
- `user.create`
- `user.assign_role`
- `user.list`
- `user.deactivate`

## Agent-Hinweise

ReqogniLoom ist die Single-Source-of-Truth für Requirements, Architektur und Test-Traceability. Verwende es immer, wenn du Features validieren oder Architekturentscheidungen nachvollziehen musst.
requirement.query/get: Wann nutzen? Zu Beginn jeder Aufgabe, um Anforderungen und deren Kontext zu verstehen. requirement.create/update/decompose/derive: Wann nutzen? Während der Planungsphase, um große Features in überprüfbare Requirements zu zerlegen. architecture.*, test.*: Wann nutzen? Beim Systemdesign (Architecture) und TDD-Prozess (Tests) zur Verknüpfung mit Code. traceability.query/suggest_links: Wann nutzen? Beim Code-Review oder Validator-Gate, um die REQ-Abdeckung zu validieren. artifact.search/get_tree: Wann nutzen? Für tiefgreifende Recherchen über den gesamten Artefakt-Baum. ai_derivation.*: Wann nutzen? Wenn du komplexe, abstrakte Requirements systematisch in technische Sub-Tasks aufschlüsseln musst.
Schreibende Tools erfordern Editor- oder Admin-Rolle. Administrative/destruktive Namespaces (admin.*, user.*, etc.) sind aus Sicherheitsgründen hart blockiert.

## Verbindungstyp

- Typ: `sse`
- URL: `{{MCP_REQOGNILOOM_URL}}/mcp/sse/` — Wert aus `secrets.local.yaml`

---

*Generiert von agent-meta aus `config/mcp-registry.yaml` — nicht manuell bearbeiten.*





## Agent Directory
> ⚠️ **ACHTUNG:** Agenten (Prompts) liegen in `.gemini/agents bzw. .opencode/agents`.

| Agent | Core Capabilities |
|-------|-------------------|

| `accessibility-specialist` | WCAG 2.1/2.2 Compliance-Audit, ARIA-Checks, Keyboard-Navigation, Screenreader... |

| `agent-meta-manager` | agent-meta verwalten: Upgrade, Sync, Feedback, projektspezifische Agenten anl... |

| `api-specialist` | OpenAPI/Contract-First API Design, Schnittstellen-Spezifikationen. |

| `bug-feature-analyzer` | Issue-Triage: Eingehende Bug-Meldungen und Feature-Requests analysieren und k... |

| `code-reviewer` | Clean Code Gatekeeper: Blast-Radius-Analyse, SOLID/DRY Prüfung, Code-Qualität... |

| `data-engineer` | ETL/ELT-Pipelines, Schema-Migration (Datenebene), Data-Quality-Checks, Lineag... |

| `database-engineer` | Relationales Schema-Design, Datenbank-Migrationen, Query-Optimierung und Inde... |

| `dependency-auditor` | Supply-Chain-Hygiene: SBOM-Analyse, Lizenz-Kompatibilität, Version-Drift und ... |

| `developer` | Feature-Implementierung und Bugfixes |

| `devops-engineer` | CI/CD, Infrastructure as Code, Kubernetes, Observability. |

| `docker` | Dev-Stack verwalten, Test-Stack starten, Binary-Management, Dockerfiles erste... |

| `documenter` | CODEBASE_OVERVIEW, ARCHITECTURE, README, Erkenntnisse pflegen |

| `e2e-tester` | E2E-Tests, visuelle Regression und Accessibility-Audits via Playwright |

| `explorer` | Read-only Codebase-Recherche, Dependency- und Impact-Mapping, Datei- und Symb... |

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

| `performance-optimizer` | Big-O Bottleneck-Identifikation und datengetriebene Performance-Optimierung. |

| `planner` | Umsetzungsplanung |

| `release` | Versioning, Changelog, Build-Artifact, GitHub Release erstellen |

| `requirements` | Anforderungen aufnehmen, REQ-IDs vergeben, REQUIREMENTS.md pflegen |

| `senior-developer` | Komplexe Features, Architektur-Entscheidungen, schwierige Bugs, Cross-Cutting... |

| `technical-writer` | Externe entwickler- und nutzergerichtete Doku: API-Referenzen, Getting-Starte... |

| `tester` | TDD, Test-Suite ausführen, Testabdeckung sichern |

| `ui-ux-designer` | UI-Spezifikationen, Mockups und Design-Systeme erstellen. |

| `validator` | Code gegen REQs prüfen, DoD-Checkliste, Traceability-Audit |


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

## Eigene Notizen

Hier kannst du eigene, projektspezifische Notizen eintragen. Dieser Bereich wird von `agent-meta` nicht überschrieben!

<!-- agent-meta:bootstrap-begin -->

## Agent Bootstrap — Session-Start Pflicht

Gemini/Antigravity benötigt eine einmalige Agent-Registrierung pro Session.
**Führe folgende Schritte zu Beginn JEDER Session aus:**

1. Lies alle Agenten-Dateien aus `.gemini/agents/`:
   - `accessibility-specialist.md` → registriere als `accessibility-specialist`
   - `agent-meta-manager.md` → registriere als `agent-meta-manager`
   - `api-specialist.md` → registriere als `api-specialist`
   - `bug-feature-analyzer.md` → registriere als `bug-feature-analyzer`
   - `change-manager.md` → registriere als `change-manager`
   - `code-reviewer.md` → registriere als `code-reviewer`
   - `data-engineer.md` → registriere als `data-engineer`
   - `database-engineer.md` → registriere als `database-engineer`
   - `dependency-auditor.md` → registriere als `dependency-auditor`
   - `developer.md` → registriere als `developer`
   - `devops-engineer.md` → registriere als `devops-engineer`
   - `docker.md` → registriere als `docker`
   - `documenter.md` → registriere als `documenter`
   - `e2e-tester.md` → registriere als `e2e-tester`
   - `explorer.md` → registriere als `explorer`
   - `feedback.md` → registriere als `feedback`
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
   - `performance-optimizer.md` → registriere als `performance-optimizer`
   - `planner.md` → registriere als `planner`
   - `quality-auditor.md` → registriere als `quality-auditor`
   - `release.md` → registriere als `release`
   - `requirements-architect.md` → registriere als `requirements-architect`
   - `requirements.md` → registriere als `requirements`
   - `risk-analyst.md` → registriere als `risk-analyst`
   - `senior-developer.md` → registriere als `senior-developer`
   - `technical-writer.md` → registriere als `technical-writer`
   - `test-engineer.md` → registriere als `test-engineer`
   - `tester.md` → registriere als `tester`
   - `ui-ux-designer.md` → registriere als `ui-ux-designer`
   - `validator.md` → registriere als `validator`

2. Registriere jeden Agenten via define_subagent API-Call:
   ```
   define_subagent(name="accessibility-specialist", ...)
   define_subagent(name="agent-meta-manager", ...)
   define_subagent(name="api-specialist", ...)
   define_subagent(name="bug-feature-analyzer", ...)
   define_subagent(name="change-manager", ...)
   define_subagent(name="code-reviewer", ...)
   define_subagent(name="data-engineer", ...)
   define_subagent(name="database-engineer", ...)
   define_subagent(name="dependency-auditor", ...)
   define_subagent(name="developer", ...)
   define_subagent(name="devops-engineer", ...)
   define_subagent(name="docker", ...)
   define_subagent(name="documenter", ...)
   define_subagent(name="e2e-tester", ...)
   define_subagent(name="explorer", ...)
   define_subagent(name="feedback", ...)
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
   define_subagent(name="performance-optimizer", ...)
   define_subagent(name="planner", ...)
   define_subagent(name="quality-auditor", ...)
   define_subagent(name="release", ...)
   define_subagent(name="requirements-architect", ...)
   define_subagent(name="requirements", ...)
   define_subagent(name="risk-analyst", ...)
   define_subagent(name="senior-developer", ...)
   define_subagent(name="technical-writer", ...)
   define_subagent(name="test-engineer", ...)
   define_subagent(name="tester", ...)
   define_subagent(name="ui-ux-designer", ...)
   define_subagent(name="validator", ...)
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

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
