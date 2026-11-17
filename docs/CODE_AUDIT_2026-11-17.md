# Code Audit — AbstrHActor v1.5.0

**Datum:** 2026-11-17  
**Scope:** HEAD `4827396`, Tag `v1.5.0`, Branch `main`  
**Methode:** Drei parallele Read-only-Audits (`code-reviewer`, `tester`, `validator`) plus lokale Verifikation der HIGH-Befunde durch den Main-Chat.  
**Gesamturteil:** **CHANGES_REQUESTED** — keine HACS-Gate-Blocker, aber **zwei echte Race-Conditions** in der neuen v1.5.0-Koordinator-Logik.

> **Nachtrag (2026-11-17, v1.5.1):** Die Blocker **H1**, **H2** sowie **M1**, **M3**, **M6** und der Default-Pfad **M2** wurden behoben; die Testlücken **T1–T4** sind mit Regressionstests geschlossen. 328 Python- und 48 Frontend-Tests grün, Ruff auf allen geänderten Dateien clean. Fix-Release: **v1.5.1**. Die übrigen Medium/Low-Findings bleiben dokumentiert und sind nicht Teil dieses Hotfixes.

| Agent | Aufgabe | Status | Ergebnis |
|---|---|---|---|
| `code-reviewer` | Vollständiges Code-Audit | done | `CHANGES_REQUESTED` — 2 High, 7 Medium, 7 Low |
| `tester` | Testabdeckung & Testqualität | done | 322 Tests grün, 91 % Coverage, 4 High-Lücken |
| `validator` | DoD, Konventionen, Release-Hygiene | done | `APPROVED_WITH_NOTES` — keine Blocker |

---

## 1. Executive Summary

Release-Artefakte sind konsistent (Version/Tag/CHANGELOG/manifest/hacs/Übersetzungen/Frontend-Bundle), CI und Tests sind grün. Die neue per-Sensor-Funktion hat jedoch zwei konkurrierende Zugriffsprobleme, die im schlimmsten Fall **veraltete Werte dauerhaft stehen lassen** bzw. **Zwischenfälle von Wertänderungen verlieren** — genau das Kernversprechen von v1.5.0 („sofortige Weiterleitung") wird damit unterbrochen.

**Empfehlung:** Blocker H1/H2 (und M1) als **v1.5.1** beheben, mit den von `tester` benannten Tests absichern und erneut releasen.

### Konsolidierte Findings nach Priorität

| ID | Severity | Bereich | Kurzbefund |
|---|---|---|---|
| **H1** | **HIGH** | `coordinator.py:263-279, 339-347` | Targeted Refresh kann von concurrent Full Refresh überschrieben werden |
| **H2** | **HIGH** | `coordinator.py:192-207` | Event während laufendem Refresh wird verworfen (Lost Update) |
| **M1** | **MEDIUM** | `websocket.py:506-507` | Options-Update löst zwei parallele Reloads aus |
| M2 | MEDIUM | `schema.py`, `coordinator.py:165-170` | `update_mode`-Default unterscheidet sich je Erstellungsweg |
| M3 | MEDIUM | `coordinator.py:203-207` | Exception im Targeted Refresh landet als unhandled Task |
| M4 | MEDIUM | `websocket.py:554-595` | Gruppen-Rename mutiert Subentries vor Entity-Rename (teilweise Mutation) |
| M5 | MEDIUM | `websocket.py:539-559` | Gruppen-Rename gibt allen Mitgliedern dasselbe `object_id` |
| M6 | MEDIUM | `coordinator.py:361-376` | Pass-through liest Primärquelle zweimal (Wert/Metadaten inkonsistent) |
| M7 | MEDIUM | `websocket.py:760-763, 802-805` | Void/Restore persistiert Options via Full-Reload |
| T1–T4 | HIGH (Tests) | `coordinator.py` | Attribute-Filter, Coalescing, Legacy-Fallback, Isolierung ungetestet |
| V1 | MEDIUM | `coordinator.py:386` | Ruff-Formatierung regressiert (18 Dateien, kein CI-Gate) |
| V2 | LOW | `config_flow.py:475` | 99 % statt 100 % Config-Flow-Coverage |
| V3 | LOW | `info.md`, `README.md` | Restliche „Abstractor"-Strings in Enduser-Doku |
| V4 | LOW | `docs/REQUIREMENTS_COVERAGE.md` | Veraltete GH#18-Aussage / Branch-Refs |
| V5 | LOW | `external/ReqogniLoom` | Submodule-Pointer dirty (vorbestehend, tabu) |

---

## 2. HIGH — Blocker

### H1 — Full Refresh überschreibt Targeted Refresh (Stale State)

**Evidenz (verifiziert):** `async_refresh_subentry()` publiziert innerhalb von `_get_lock()` via `async_set_updated_data(updated)`. Der Full-Pfad `_async_update_data()` berechnet ebenfalls unter dem Lock, **gibt das Dict aber zurück**; die Basisklasse `DataUpdateCoordinator._async_refresh()` ruft `async_set_updated_data(data)` erst **nach** Freigabe des Locks auf. Ein Event-Refresh, der zwischen Compute und Base-Publish landet, wird anschliessend vom älteren Full-Snapshot überschrieben.

**Impact:** Eine Quelländerung, die mit einem Reload/Startup-Refresh zusammenfällt, lässt `coordinator.data` dauerhaft veraltet — bis zum nächsten Event. Betrifft direkt das v1.5.0-Kernfeature.

**Empfehlung:** Einen gemeinsamen Publish-Point verwenden. Entweder `async_full_refresh()` ergänzen, das Compute + `async_set_updated_data` unter dem Lock ausführt (und in `__init__.py` `async_refresh()` ersetzt), oder `_async_refresh()` überschreiben und den Base-Aufruf mit demselben Lock serialisieren.

### H2 — Event während laufendem Refresh geht verloren

**Evidenz (verifiziert):** `_queue_refresh()` ignoriert weitere Trigger, solange die `subentry_id` in `_pending_refreshes` steht. Die ID wird erst im `finally` von `_async_refresh_queued()` entfernt — also **nach** `await async_refresh_subentry()`. Ein echter State-Change während des Computes wird verworfen, ohne Nachschub.

**Impact:** Bei schnell wechselnden Quellen bleibt ein älterer Wert stehen, bis ein späteres Event erneut triggert.

**Empfehlung:** Dirty-Flag-/Generation-Muster: ID unmittelbar vor dem `await` aus `_pending_refreshes` entfernen und bei zwischenzeitlich neu eingegangenem Trigger genau einen Folge-Refresh einplanen (Coalescing bleibt erhalten).

---

## 3. MEDIUM

- **M1 (verifiziert):** `async_update_entry()` feuert bereits den Update-Listener (`_async_options_updated` → `async_reload`); `websocket.py:507` plant zusätzlich explizit einen zweiten Reload. Jeder Options-Speicher baut Coordinator, Panel, Services und WS-Registrierungen doppelt auf. Fix: Zeile 507 entfernen — die anderen Options-Writer (`ws_sample_void/restore`) verlassen sich bereits auf den Listener.
- **M2:** Form-Default ist `event` (`DEFAULT_UPDATE_MODE`), WS-Validator setzt keine Defaults, `_update_mode_for()` fällt auf `polling` zurück. Ein WS-Client ohne `update_mode` erzeugt damit einen Polling-Sensor. Fix: Default beim Anlegen zentral injizieren (z. B. in `_build_new_subentry_data()`), Legacy-Fallback unverändert lassen.
- **M3:** `_async_refresh_queued()` hat nur `try/finally`, kein `except`. Fehler in `_compute_subentry()` (Filter, Influx, Notify) landen als unhandled Task; `last_update_success`/`last_exception` bleiben alt. Fix: `async_set_update_error(err)` + Debug-Log.
- **M4/M5:** Gruppen-Rename schreibt Subentry-Daten vor dem Entity-Registry-Rename und ohne Rollback; allen Mitgliedern wird dasselbe `object_id` zugewiesen (HA erzeugt `_2`, `_3`, …). Fix: Entity-Rename zuerst/transaktional, `object_id` nur am gewählten Mitglied.
- **M6:** Pass-through liest `hass.states.get()` in `raw_states` und erneut via `_read_state(primary)`. Fix: `raw_states[0]` wiederverwenden.
- **M7:** Void/Restore löst über `async_update_entry(options=…)` einen Full-Reload aus, nur um ein Boolean zu persistieren. Fix: dedizierter `Store` oder Listener für diesen Key unterdrücken.

---

## 4. LOW / Hygiene

- **V1:** `ruff format --check` schlägt fehl (u. a. `coordinator.py:386`); 18 Dateien betroffen, kein Ruff-Schritt in CI. Fix: Format laufen lassen + `ruff format --check` in `.github/workflows/validate.yaml`.
- **V2:** `config_flow.py:475` defensive None-Route ungetestet (99 % statt geforderter 100 %).
- **V3:** `info.md` und `README.md` enthalten noch Enduser-„Abstractor"-Strings (nur UI, keine Identifier).
- **V4:** `docs/REQUIREMENTS_COVERAGE.md` widerspricht `REQUIREMENTS.md` bei GH#18 (Bundling-UI), veraltete Branch-Refs.
- **V5:** `external/ReqogniLoom` ist vorbestehend dirty (Pointer `a05f6d5` vs. Checkout `9e0399b`); nicht angefasst, bewusst tabu.
- **Weitere (code-reviewer):** `services.yaml`/`strings.json` unvollständig umbenannt (L1); `diagnostics.py` gibt Verbrauchswerte unmaskiert aus (L2); `influx_exporter.py` loggt unbounded Error-Body (L3); Snapshot-Import ohne Kardinalitätsgrenzen (L4); nicht-standard Subentry-ID (L5); hohe HA-Feature-Detection-Komplexität (L6); YAML-Scan unterstützt keine `!include` (L7); WS-Reads zeigen Werte auch Non-Admins (L8 — vermutlich intentional, gegen Datenschutz-Entscheidung prüfen).

---

## 5. Test-Audit (Details)

322 Tests grün, 91 % Gesamt-Coverage; `config_flow.py` 99 %, `schema.py` 100 %, `coordinator.py` 91 %, `websocket.py` 78 %. Vier HIGH-Lücken betreffen genau die neue Logik:

| ID | Ungetestetes Verhalten | Risiko |
|---|---|---|
| T1 | Attribut-only Events unterdrücken Refresh (Changelog-Fix!) | Refresh-Storm bei Attribut-Updates |
| T2 | `_queue_refresh`-Coalescing + `finally`-Release | Duplicate Pushes / permanenter Block |
| T3 | Legacy-Mode/`_interval_for`-Fallback (kein Mode, ungültiger Wert) | Sensoren updaten gar nicht / falsch |
| T4 | Targeted Refresh isoliert andere Sensoren; Unknown/No-Source no-op | Fremde Entitäten überschrieben |

Weiterhin: Immediate Refresh neuer Subentries (M1 im Test-Audit), Trigger-Re-Registration/Exception-Pfad, neue Schema-Felder kontraktuell, WS-Row-Felder, Frontend-Prefill. E2E-Locators nutzen feste Sleeps und DOM-Reihenfolge (`.first/.last`) — Flaky-Risiko. Ein un-awaited Coroutine in `tests/test_services.py:248`.

---

## 6. Bestätigt OK

-manifest-Version `1.5.0` == Tag == HEAD; CHANGELOG-Eintrag mit MINOR-Begründung; Conventional Commits ≤ 72 Zeichen; Branch-Guard eingehalten.
- `strings.json` ↔ `translations/en.json` synchron, `de.json` vorhanden; Frontend-Artefakt rebuildet sauber.
- CI-Jobs: HACS, Hassfest, Translations-Sync, Pytest, Frontend-Sync; keine Release-Automation (dokumentiert).
- HACS-Gates 1–7 und 9–10 PASS; Gate 8 (Redaction) mit MINOR-Abstrichen (L2/L3/L8).
- `has_entity_name` auf allen Entity-Basen; keine Wildcard-Imports, keine f-String-Logs, `isfinite`-Validierung in `filters.py`.
- Submodule-Schutz und No-Worktree-Regel eingehalten; keine fremden Repos im Hauptbaum.

---

## 7. Empfohlene Reihenfolge

1. **H1 + H2** fixen (Coordinator-Publish/Coalescing) — Blocker.
2. **M1** Remove Double-Reload; **M3** Error-Bookkeeping; **M6** Doppelread.
3. **T1–T4** als REQ-getaggte Unit-Tests ergänzen, danach Coverage erneut messen.
4. **V1** Ruff-Format + CI-Gate; **V2** Config-Flow-Test; **V3/V4** Doku/Traceability.
5. Als **v1.5.1** (PATCH/Hotfix) releasen —breaking ist kein Change enthalten.

---

## Anhang — Rohartefakte

- Validator: `/var/tmp/opencode/validator-audit-v1.5.0.md`
- Tester/Reviewer: Findings inline in den Agent-Resultaten (read-only, keine Dateien geschrieben)
