# AbstrHActor

AbstrHActor — short description.

<!-- agent-meta:managed-begin -->
> **ROUTING:**

 Opencode->AGENTS.md |

> **ENTRY:** `orchestrator`-Agent (für alle Dev-Tasks).
`agent-meta v0.89.0` | DoD: `standard` | REQ-Trace: `false`

## Projekt

**Name:** AbstrHActor
**Präfix:** Absrct
**Plattform:** {{PLATFORM}}
**Beschreibung:** {{PROJECT_DESCRIPTION}}

## Tech-Stack

- **Runtime:** {{RUNTIME}}
- **Sprache:** {{LANGUAGE}}
- **Key-Dependencies:** {{SYSTEM_DEPENDENCIES}}

## Architektur

```
{{PROJECT_STRUCTURE}}
```

**Entry-Point:**
```
{{ENTRY_POINT_PATTERN}}
```

**Besondere Patterns:**
{{KEY_PATTERNS}}

## Code-Konventionen

- TypeScript ES6+, no `any`, no `var`

## Build & Development

```bash
# Build
{{BUILD_COMMAND}}

# Tests
{{TEST_COMMAND}}

# Dev-Stack starten
{{DEV_STACK_START}}

# Nach Änderungen neu laden
{{DEV_STACK_RELOAD}}
```

## Anforderungs-Kategorien

Kategorien für `docs/REQUIREMENTS.md`:

- Core features
- Non-functional requirements

## Agent Directory
> ⚠️ **ACHTUNG:** Agenten (Prompts) liegen in `.gemini/agents bzw. .opencode/agents`.

| Agent | Core Capabilities |
|-------|-------------------|

| `agent-meta-manager` | agent-meta verwalten: Upgrade, Sync, Feedback, projektspezifische Agenten anl... |

| `bug-feature-analyzer` | Issue-Triage: Eingehende Bug-Meldungen und Feature-Requests analysieren und k... |

| `code-reviewer` | Clean Code Gatekeeper: Blast-Radius-Analyse, SOLID/DRY Prüfung, Code-Qualität... |

| `developer` | Feature-Implementierung und Bugfixes |

| `documenter` | CODEBASE_OVERVIEW, ARCHITECTURE, README, Erkenntnisse pflegen |

| `feature` | Feature-Lifecycle-Subagent: Branch → REQ → TDD → Dev → Validate → PR |

| `feedback` | Projekt-Feedback standardisieren: Bugs, Features, Verbesserungen als GitHub I... |

| `git` | Commits, Branches, Tags, Push/Pull und alle Git-Operationen |

| `log-analyzer` | System- und Applikations-Logs analysieren: Frequency-Clustering, Severity-Kla... |

| `meta-feedback` | Verbesserungsvorschläge für agent-meta als GitHub Issues einreichen |

| `orchestrator` | Einstiegspunkt für alle Entwicklungsaufgaben |

| `requirements` | Anforderungen aufnehmen, REQ-IDs vergeben, REQUIREMENTS.md pflegen |

| `tester` | TDD, Test-Suite ausführen, Testabdeckung sichern |





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


## Eigene Notizen

Hier kannst du eigene, projektspezifische Notizen eintragen. Dieser Bereich wird von `agent-meta` nicht überschrieben!

<!-- agent-meta:bootstrap-begin -->

## Agent Bootstrap — Session-Start Pflicht

Gemini/Antigravity benötigt eine einmalige Agent-Registrierung pro Session.
**Führe folgende Schritte zu Beginn JEDER Session aus:**

1. Lies alle Agenten-Dateien aus `.gemini/agents/`:
   - `agent-meta-manager.md` → registriere als `agent-meta-manager`
   - `developer.md` → registriere als `developer`
   - `documenter.md` → registriere als `documenter`
   - `git.md` → registriere als `git`
   - `log-analyzer.md` → registriere als `log-analyzer`
   - `meta-feedback.md` → registriere als `meta-feedback`
   - `orchestrator.md` → registriere als `orchestrator`

2. Registriere jeden Agenten via define_subagent API-Call:
   ```
   define_subagent(name="agent-meta-manager", ...)
   define_subagent(name="developer", ...)
   define_subagent(name="documenter", ...)
   define_subagent(name="git", ...)
   define_subagent(name="log-analyzer", ...)
   define_subagent(name="meta-feedback", ...)
   define_subagent(name="orchestrator", ...)
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
