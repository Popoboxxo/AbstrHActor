# Umsetzungsplan Phase UI-1 (Management-UI Vertrauen + Backend) AbstrHActor

**Basismcommit:** `919a17d`
**Scope:** Read-only-UI + minimales Schreib-GerÃ¼st; keine Domain-Erweiterung (WS-C bleibt out-of-scope)
**PrimÃ¤res DoD:** Artikulate Kriterien in Â§1
**Voraussetzung:** gelesene Review `docs/system-review-2026-10.md`

---

## 1. Goal (observable user outcome)

1. Der Sidebar-Panel flackert bei unrelated state-Ã„nderungen nicht mehr.
2. Ein Nutzer sieht sofort, welche Sensoren ungesund sind (`ok/warn/bad/idle`) und warum (spike rejections, fallbacks, stale, unavailable samples).
3. Identity (logical name, object_id, unique_id) ist primÃ¤r sichtbar; Hardware-source-IDs sind collapsed.
4. Die UI arbeitet mit HA auth (Admin-Status fÃ¼r Edit-Mode vorbereitet) und mit einer Backend-Read-API.
5. Pure Selektoren und Render-Kontrakt sind mit Unit-Tests und Playwright-E2E abgedeckt.

## 2. Non-Goals (explizit)

- Keine DomÃ¤nen-Erweiterung (light/switch/cover) â€“ WS-C bleibt bei Phase 3.
- Kein YAML-takeover-Script und keine Migrate-Tab-FunktionalitÃ¤t beyond read-only Preview.
- Kein Edit-Mode-Schreibfluss (nur Token-Endpunkt + disabled UI als vorbereitete FlÃ¤che) in Phase 1.
- Kein BuildStep/Lit-EinfÃ¼hrung (bleibt pending, siehe Entscheidung Gr. 1).

## 3. Deliverables (Dateien)

| Datei | Neue/Ã„nderung | Inhalt |
|---|---|---|
| `custom_components/abstractor/websocket.py` | neu | Websocket-Register + alle Handler |
| `custom_components/abstractor/const.py` | Ã¤ndern | WS-cmd-Namen, Health-Keys |
| `custom_components/abstractor/coordinator.py` | Ã¤ndern | Meta API (schon geplant in Plan WS-B); falls noch nicht, implementieren Lesepfad |
| `custom_components/abstractor/config_flow.py` | Ã¤ndern | Helfer `_normalize_subentry_data`, `_build_new_subentry_data`, `_validate_device_mapping` modulimportabel |
| `custom_components/abstractor/frontend.py` | Ã¤ndern | Websocket-Routen bei Setup registrieren; Panel-JS wiring |
| `custom_components/abstractor/www/abstractor-panel.js` | umbauen | Shell + Store + Selektoren + Tabs + Rendering |
| `custom_components/abstractor/www/abstractor-store.js` | neu | Store + subscriable slice |
| `custom_components/abstractor/www/abstractor-selectors.js` | neu | Pure selector functions (exportable) |
| `custom_components/abstractor/www/abstractor-drawer.js` | neu | Drawer + focus trap |
| `tests/test_websocket.py` | neu | Admincheck, redaction, health payload, token |
| `tests/test_frontend.py` | erweitern | Registration / Websocket gating |
| `tests/frontend/*` | neu | Node-Unit-Tests der Selektoren (ohne Build, no browser) |
| `tests/playwright/panel-phase1.spec.js` | neu | E2E (HA e2e stack; optional) |

## 4. Backend Worker-Blices (in Reihenfolge)

### B0 â€“ Extraktions-Schritt (pure refactor)
- Config-Flow-Helfer werden importierbar (`config_flow.py` â†’ `_normalize_subentry_data`, `_build_new_subentry_data`, `_validate_device_mapping`).
- Lint/typecheck Existing tests must remain green.

### B1 â€“ Coordinator Meta (nur Read)
- `meta: dict[str, SubentryMeta]` bereits als Datenklasse definieren (frozen slots).
- BefÃ¼llen in `coordinator._async_update_data` mit: `last_event`, `event_at`, `spike_rejections`, `fallbacks`, `unavailable_samples`, `source_states`, `stale`.
- Nicht persistieren (runtime only).

### B2 â€“ Websocket read Command: `abstractor/subentries`
- Auth: any authenticated user (panel access inheritiert).
- Returns: array of `{subentry_id, title, unique_id, identity: {logical_name, object_id, device_name}, type_key, health, data, meta}`.
- Meta redaction: `source_states` nur gezielt exportieren; reuse `diagnostics.py` Redaction.
- Health Berechnung (`selector healthDot` als pure function + Backend-Value fÃ¼rs UI): ok/warn/bad/idle.
- Error shape: `{code: "not_allowed"}` / `"internal_error"`.

### B2b â€“ Read Command: `abstractor/options` (optional, Phase 1 done via deep links fallback â€” can be Phase 1 optional)
- Phase 1 minimal: lassen wir als Deep-Link, verschieben nach Phase 2.

### B3 â€“ Websocket write Command (nur edit-mode-token, keine Mutation):
- `abstractor/mode/token {ttl}`: admin check via WS context (implementierbar? in async verifizierbare Parameter); RÃ¼ckgabe token/expires.
- Token server-side dict keyed by WS-session; nicht persistiert.
- Token expiry 15 min slide; invalid â†’ panel drops to read-only.

### B4 â€“ Setup Registration
- `frontend.py`: inject commands in `async_setup_entry`; unregister bei unload.
- Websocket cleanup bei unload.

## 5. Frontend Worker-Blices (in Reihenfolge)

### F0 - Struktur / Module-Splits
- `abstractor-selectors.js`: pure functions (`healthDot`, `pipelineSummary`, `identity`, `rowLabel`).
- `abstractor-store.js`: State-Holder mit `subscribe`, `state`, `mutate`, `invoke`.
- `abstractor-panel.js`: Shell mit subscribable update, tabs (#router), tabs keep persistence.
- `abstractor-drawer.js`: container mit focus trap (ESC, Tab cycling, `inert`).

### F1 – Datenbindung
- Replace `hass.devices/entities` traversal with store fetch via ws (`abstractor/subentries`) on connect and after HA reconnect.
- Store re-fetch on custom event triggers, 500ms debounce.
- Health rings + dot, health strip im header (gesunde/kritische Zahlen, last poll seconds).

### F2 – Tabs
- Devices (lists + filter chips All/Power/Energy/Water/Binary/Problems).
- Health (problem rows grouped by failure kind).
- Settings (deep links first, settings WS later).

### F3 – Drawers
- Sensor detail drawer: identity, sources, pipeline stages, history deep link.
- Rename/edit-mode-gate dummy drawer with edit-mode flag pre (only visible to admins).

### F4 – Accessibility + Motion
- `ha-button` replacements, reduced layout shift, keyboard order.
- ARIA live region in toast, focus trap in drawer.

### F5 – i18n + strings
- Key map from `hass.language` with `panel.*` keys; fallback to English.
- Strings move from hardcoded EN/DE into strings.json-referenced keys.

## 6. DoD (verbindlich)

- [ ] Backend unit tests green for ws commands (admincheck, redaction, shape).
- [ ] Panel registration test suite unchanged (3 ? maybe 4) for registrieren / no-op.
- [ ] UI unit tests (selectors) green with no flaky timing.
- [ ] Playwright happy-path: Tab-Switching, health display, no flicker regression via snapshot.
- [ ] Lint/typecheck clean; no circular imports in ws.py.
- [ ] Vor PR: test agains HA test image (`docker-compose.test.yml`).

## 7. Milestone / Sequence

M1 (1-2 d) – B0 + B1 (Meta + Helpers) – tests
M2 (1-2 d) – B2 `subentries` + Redaction tests
M3 (1-2 d) – B3 token + B4 wiring
M4 (2-3 d) – F0-F2 neue Panel shell + Tabs auf store
M5 (1-2 d) – F3 drawers mit accessibility baseline
M6 (1 d) – i18n + A11y budget + Playwright smoke
M7 (1 d) – E2E validation & documentation (update SYSTEM_AUDIT, README panel section)

Total: ca. 9-12 working days single dev.

## 8. Decisions we need from user before coding (with recommendations)

1. **Build toolchain** – Keep no-build (Current) oder add esbuild/Lit in later phase? Recommendation: stay no-build in Phase 1.
2. **Object_id Pflicht** – Drawer Pflicht, nativer Flow optional. Recommendation: Drawer required = yes.
3. **REQ-UTIL-001 (eigene Statistiken)** – Erst verifizieren ob `state_class`/available override die Langzeistatistik bringt; im Zweifel streichen. Recommendation: verify first = yes.
4. **Migrate tab timing** – Read-Only-Scanner früh (Phase 2), voller Transplant-Skript Phase 3+. Recommendation: früh basic scanner.
5. **Auth Websocket context**: HA macht `is_admin` im WS-Context? Validate early in B2. Note: modern HA provides `connection.async_auth` etc — we need investigate whether websocket command handlers have access to user. Lösung: WS handler executes in a connection context which has a caller user. We'll verify with test.
6. **Redaction exact shape**: match diagnostics (source_states ? redacted). Recommendation: reuse diagnostics helper.
7. **Token storage TTL**: 15 min slide vs 10 min fixed. Recommendation: 15 min, sliding, admin only.

## 9. Risk Mitigations

- R render performance: use memoization, don't rebuild DOM for non-panel state.
- R no frontend tests today: add at least selector tests to avoid regressions.
- R backend ws race: fetch on connect and on ws-reconnect; debounce.

## 10. Next actions (immediate)

- [ ] User decisions confirmieren (§8).
- [ ] B0+B1 Backend im separaten Branch `feat/ui1-backend` starten.
- [ ] Für Unit-Tests lib wire (`tests/frontend`), ohne Node test runner? use builtin `node:test`.
- [ ] Test HA image rebuild after websocket addition; e2e harness.

## 11. Abgleich: Alte UI-Anforderungen (REQ-CORE-002, GH#18, Action-Hub) — als Basis fuer Phase 1

### 11.1 Bestehende Anforderungen, die beibebehalten und in Phase 1 mitbedacht werden
- **REQ-CORE-002** (Config Flow first): Formulare/Registry-Transaktionen bleiben Config Flow + WS-geschuetzten Helpers. Das Panel ist **duenn**: Add/Edit tief-linken weiterhin in native HA-Seiten; kein zweiter Config-Engine (Action-Hub-Durchsatz).
- **Device-Mapping-Sicherheit (GH#18)**: Mapping nur als explizite Registry-Transaktion über `_validate_device_mapping` + `_normalize_subentry_data`. Write-, create- und rename-Kommandos müssen die vorhandenen Helfer nutzen; panelseitig nie "cross-subentry bundling" durchführen.
- **Export/Import Baseline** (plan-panel-action-hub): Export button nutzt supports_response; Import parst JSON client-side und setzt service; service validiert; bindend. Diese Flows bleiben in der neuen Store-/Tab-Architektur nutzbar und werden unter den Edit-Mode-Gate gestellt (Import write).
- **OptionsFlow Contract** (Geräte-Hersteller/Modell): im Settings-Tab durch `_resolve_identity` + device registry renumber scheinen. Phase 1 kann Deep-Links vorab nutzen; Settings-API (Phase 2) bindet die gleichen Helfer.
- **Panel-Gerätefilter**: bereits identifier-basiert (`id[0]==='abstractor'`). Neue WS muss weiterhin HA's identifier-Liste zurückgeben und nicht manufacturer filtern — altes Relikt des audit-ui-plans.
- **Root-Options** (poll interval, influx, debug targets) werden in Phase 1 als Deep-Link im Settings-Tab belassen, als Schreib-API Phase 2 hinzugefugt.

### 11.2 Edit-Mode-Semantik (explizit: base read-only)
- **Basis-Modus = read-only** für alle Nutzer (inklusive Admins). Keine Make-Write-Buttons verfügbar.
- **Schreibmodus wird ausschließlich per explizitem Toggle "Edit mode" aktiv**, bestätigt durch Banner + Token (serverseitig issued, 15 min TTL sliding, admin-gated). Nur wenn der Schalter aktiv und das Token valide ist, erscheinen write-facing Actions (Create/Edit/Rename/Import/Options).
- **Export** bleibt immer lesend verfügbar, ebenso reine Navigation (Open device, Open history).
- **Destructive Actions** (Import, Delete, Rename, Bulk) verlangen im Schreibmodus eine zweite inline Bestätigung.
- **Nicht-Admins** bekommen den Schalter nicht angezeigt. Standard-Config-Flow bleibt unverändert handhabbar.
- Backend-Prüfung: `abstractor/mode/token` + admin check; ungültiges Token -> panel fällt zurück zu read-only.

### 11.3 Konfliktpunkte, die im Umsetzungsplan adressiert werden
1. Der neue WS-Write-Pfad muss die Registry-Transaktionen aus dem Config Flow wiederverwenden (kein zweiter Implementationspfad — R7).
2. Panel-Replace der device/entity traversal mit ws skannier zu lazily refresh; kein flicker (F1 memoization).
3. Health-state (meta) muss aus bisherigen warn/bad flags ineingebettet werden, sodass vorhandene Tests unchanged.
4. Alle Formularfehler (z.B. device mapping conflict) serverseitig translated waehren panelseitig bounds.
5. Die Read-API als neues Surface muss redacted und 100%-coverage konform sein (diagnostics shared redaction).

### 11.4 Konkrete Konsequenzen für Phase 1
- F2 Tabs: Devices, Health, Settings; Migrate bleibt Phase 2 Scanner.
- Im Settings-Tab deep-link Export/Import/Options; Import only after edit-mode.
- Auth/Permission: read commands für alle Bürger (HA viewing permission) ok; token nur Admin.
- Baseline panel service calls (create/link etc.) remain until later WS-write commands land; create/edit buttons deep-link native flows.


## 0. Phase 0 – Build-Toolchain (neu, vor Phase 1)

- esbuild + TypeScript-optional JS-Bundling (decided: include build chain)
- `frontend/src/` ? gebündeltes `custom_components/abstractor/www/abstractor-panel.js`
- Build scripts: `npm run build:frontend`, watch-mode für Entwicklung
- Release: Build vor Hassfest/HACS, keine unchecked Source-File-Edits
- Type-Check optional (Warning-freie JS-Lint wahlfrei)
