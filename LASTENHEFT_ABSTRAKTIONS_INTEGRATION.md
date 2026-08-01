# Lastenheft: Energy Abstraction Layer als Custom-Integration

**Status:** Entwurf / Ideation — kein REQ-ID vergeben  
**Repo/Branch:** HomeAssistant, `docs/ha-audit-eos-abstraktion`  
**Betroffene Ist-Artefakte:** `packages/abstraction/energy_power.yaml`, `packages/abstraction/battery_power_energy.yaml`, `packages/abstraction/ace1500_power_energy.yaml`

---

## 1. Ausgangslage & Motivation

### 1.1 Ist-Zustand

Die Energy Abstraction Layer entkoppelt physische Hardware-Entitäten (Tasmota-, Shelly-, Zigbee2MQTT-Plugs, Matter-Steckdosenleisten, Zendure-Speicher) von Dashboards, Utility Metern und Automatisierungen. Umsetzung erfolgt vollständig deklarativ in YAML mittels Home-Assistant-Template-Plattform, Jinja2-Ausdrücken und YAML-Ankern.

### 1.2 Umfang (Ist, quantifiziert)

In `packages/abstraction/energy_power.yaml` allein:

- **57** Energy-Template-Sensoren (kWh, `device_class: energy`, `state_class: total_increasing`)
- **58** Power-Template-Sensoren (W, `device_class: power`, `state_class: measurement`)
- **115** Template-Sensoren gesamt, plus 1 Trigger-Sensor und 1 Integration-Sensor → **117** in dieser Datei
- **13** Utility Meter (Suffix `_energy_count`)
- **94** Vorkommen des Spike-Filter-Patterns zur Absicherung monoton steigender Energiezähler
- **130** statisch vergebene `unique_id`-Werte (History-kritisch)

Weitere Abstraktionsdateien mit gleichem Migrationsbedarf: `battery_power_energy.yaml` (Hyper2000), `ace1500_power_energy.yaml` (Zendure ACE 1500, 3 weitere Utility Meter), `water_consumption.yaml` (Wasser-Abstraktionsmuster).

### 1.3 Wartungsaufwand & Fehleranfälligkeit (Ist)

- **Boilerplate:** Pro Gerät wird ein Sechs-Zeilen-Jinja2-Block redundant repliziert — 94 Vorkommen desselben Musters ohne Wiederverwendbarkeit über Anker.
- **Kein Compile-Time-Schutz:** Jinja2-Templates werden erst zur Laufzeit ausgewertet; Tippfehler in Entity-IDs oder Filterlogik fallen erst im Betrieb auf.
- **Manuelles Onboarding:** Jedes neue Gerät erfordert Copy-Paste inkl. manueller UUID-Vergabe, YAML-Anker-Pflege und Utility-Meter-Anpassung — laut Changelog-Historie ein fehleranfälliger manueller Vorgang.
- **Volatilität durch Restarts:** Neue Packages erfordern Full-Restart statt Quick-Reload.
- **Fehlende Testbarkeit:** Jinja2-Templates lassen sich nicht isoliert unit-testen.
- **CPU-Spikes historisch belegt:** Laut Changelog V2.9 verursachten `unavailable`-Sensoren ohne Guard nachweislich CPU-Spikes — ein Klassenproblem, das Python robuster lösen würde.

**Audit-Befund (2026-07-29):** Der durchgeführte Codebase-Audit (siehe `docs/AUDIT_HA_2026-07-29.md`) belegt diese Fehleranfälligkeit durch konkrete Funde:
- **A2-01:** `| int` ohne Default auf Hardware-Sensoren erzeugt Error-Loops bei `unavailable` (CPU-Spike-Klassiker).
- **A2-05:** Utility Meter direkt auf Hardware-Entitäten statt abstrahierter Sensoren — Bruchrisiko bei Gerätetausch.
- **A1-06:** Nach Zendure-Migration nicht mehr existierende Entity-Referenzen in Templates — die Abstraktion ist mit der Hardware nicht synchron.

Diese Befunde unterstreichen, dass eine strukturelle Lösung (Python-Integration statt Jinja2-Boilerplate) nötig ist.

---

## 2. Kontext & bisherige Vorarbeit

### 2.1 HA-Core Feature-Request (bereits gestellt)

Der Projektverantwortliche (GitHub-Handle "Popoboxxo") hat das Konzept der nativen Abstraktionsebene bereits als **Feature-Request an Home Assistant Core** eingereicht:

**[GitHub Discussions #3402: "Native Entity Aliasing for Home Assistant — Hardware-independent logical entities for the entire smart home"](https://github.com/orgs/home-assistant/discussions/3402)**  
(Kategorie: Experimental ideas, Stand: 0 Kommentare, 3 Stimmen, unbeantwortet)

Der Core-Request schlägt vor, ein natives **Entity-Aliasing-System** direkt in HA Core zu etablieren, das Hardware-unabhängige logische Entitäten für das gesamte Smart-Home ermöglicht — konzeptionell dieselbe Idee, die dieses Lastenheft als Custom-Integration umsetzt.

### 2.2 Warum parallel eine Custom-Integration?

Der Core-Feature-Request ist derzeit **unbeantwortet und unverbindlich** — der Zeitrahmen für eine potenzielle Übernahme in HA Core ist unklar. Die Custom-Integration wird daher **unabhängig vom Core-Release-Zyklus** verfolgt, um:

1. **Schneller nutzbar zu sein:** Proof-of-Concept und rollout können im laufenden Projekt umgesetzt werden, ohne auf HA-Core-Roadmap zu warten.
2. **Selbstkontrolliert zu sein:** Wartung und Updates erfolgen im Projekt selbst, nicht an externe Abhängigkeiten gebunden.
3. **Vorkehrungen zu treffen:** Falls Core das Pattern in der Zukunft nativ übernimmt, kann die Custom-Integration als Migrationspfad dienen oder parallel bestehen.

### 2.3 Ausschließen sich nicht aus

- **HACS-Integration (kurzfristig, selbstbestimmt):** Custom-Integration zur sofortigen Problemlösung im laufenden Betrieb.
- **Core-Feature-Request (langfristig, optional):** Bleibt offen und kann jederzeit durch HA Core-Maintainer aufgegriffen werden. Falls Core das Pattern übernimmt, kann das Projekt später auf den nativen Mechanismus migrieren.

Diese Strategie reduziert Abhängigkeiten, während sie die Möglichkeit einer langfristigen Harmonisierung mit HA Core bewahrt.

---

## 3. Zielbild

Die Energy Abstraction Layer wird als eigenständige **Home-Assistant-Custom-Integration** (`custom_components/`) realisiert, die:

- abstrahierte Energy-/Power-Entitäten dynamisch aus einer Konfiguration erzeugt (statt YAML-Duplikation),
- Spike-Filter- und Verfügbarkeitslogik in Python implementiert (testbar, versionierbar, mit klaren Fehlerpfaden),
- bestehende `unique_id`-Werte und Entity-IDs verlustfrei übernimmt (History-Kontinuität),
- den YAML-Boilerplate in `packages/abstraction/` deutlich reduziert (Zielzustand: Geräte-Onboarding über Config-Flow),
- kompatibel zu Utility-Meter-Kopplung und bestehenden Konsumenten-Packages bleibt.

Die Umstellung erfolgt domänen-agnostisch: `energy_power.yaml`, `battery_power_energy.yaml`, `ace1500_power_energy.yaml` sind konzeptionell gleichartig und werden von derselben Integration bedient.

---

## 4. Funktionale Anforderungen

- **FA-01:** Die Integration MUSS über einen HA-nativen Config-Flow (UI) das Anlegen einer neuen abstrahierten Energy/Power-Geräte-Paarung ermöglichen, ohne manuelle YAML-Bearbeitung.

- **FA-02:** Die Integration MUSS bestehende abstrahierte Geräte (aktuell 57 Energy-/58 Power-Sensor-Paarungen in `energy_power.yaml`, zzgl. Hyper2000 EG/OG und ACE 1500) als Migrationsbestand einlesen bzw. importieren können, ohne dass der Nutzer sie manuell neu anlegt.

- **FA-03:** Die Integration MUSS eine dynamische Geräte-Registrierung unterstützen — neue Quell-Entitäten sollen zur Laufzeit über den Config-Flow hinzufügbar sein, analog zum aktuellen "neues Gerät = neuer YAML-Block"-Vorgang, aber ohne YAML-Edit.

- **FA-04:** Die Spike-Filter-Logik (aktuell: `this.state`-Vergleich, "Energiezähler dürfen nur steigen") MUSS als Python-Funktion implementiert werden, mit derselben fachlichen Semantik wie im Ist-Zustand.

- **FA-05:** Die Verfügbarkeitslogik (aktuell `availability: {{ has_value(...) }}`) MUSS in Python nachgebildet werden, inkl. des in V2.9 gefixten CPU-Spike-Problems bei `unavailable`/`unknown`-Quellsensoren.

- **FA-06:** Erzeugte Power-Sensoren MÜSSEN sich wie der Ist-Zustand mit `| float(0)` gegen fehlende Werte absichern (Power geht auf 0 statt `unavailable`).

- **FA-07:** Erzeugte Energy-Sensoren MÜSSEN sich analog zum Ist-Zustand bei fehlender Quelle auf `unavailable` setzen, um Utility-Meter-Verfälschung zu vermeiden.

- **FA-08:** Die Integration MUSS für jeden abstrahierten Energy-Sensor optional die Anbindung eines Utility Meters (Suffix-Konvention `_energy_count`, kein Reset, `always_available: true`) unterstützen — entweder durch Beibehaltung des bestehenden `utility_meter:`-YAML-Mechanismus als Konsument oder durch äquivalente Funktionalität innerhalb der Integration.

- **FA-09 (KRITISCH):** Die Migration bestehender `unique_id`-Werte (130 in `energy_power.yaml`, weitere in `battery_power_energy.yaml`/`ace1500_power_energy.yaml`) MUSS ohne Verlust von Recorder-/Long-Term-Statistics-History erfolgen. Neue Entities dürfen nicht unter neuen `unique_id`/`entity_id` erzeugt werden, wenn ein 1:1-Ersatz eines bestehenden Sensors gemeint ist.

- **FA-10:** Aggregations-Sensoren (Beispiel: "Haus Standby Plugs Gesamtleistung" via Trigger-Template über Entity-Pattern-Matching) MÜSSEN funktional äquivalent abbildbar sein.

- **FA-11:** Die Integration MUSS mehrere Entitäten desselben physischen Geräts zu einer Summe verrechnen können (Beispiel: Basteltisch — 4 Einzelsteckdosen + 1 Gesamt-Sensor).

- **FA-12:** Fallback-/Inverslogik einzelner Spezialfälle (Beispiel ACE 1500: Shelly-Fallback nur wenn `output_pack_power == 0`, invertierte Leistungssensoren) MUSS als konfigurierbare Option pro Gerät abbildbar sein, nicht nur als Hardcoding.

- **FA-13:** Debug-/Diagnose-Ausgaben MÜSSEN sich in das bestehende Notification-Konzept einfügen (`input_boolean.automation_debugger` → `notify.adminnotificationgroup`), sofern die Integration Fehlzustände oder Spike-Verwerfungen meldet.

---

## 5. Nicht-funktionale Anforderungen

- **NFA-01 (Performance):** Die Integration darf die bestehende CPU-Last nicht erhöhen; Ziel ist mindestens Parität zum aktuellen Trigger-Intervall (5 Minuten) bzw. eine Verbesserung durch Wegfall wiederholter Jinja2-Auswertung.

- **NFA-02 (Testbarkeit):** Die Kernlogik (Spike-Filter, Verfügbarkeit, Aggregation) MUSS unabhängig von einer laufenden HA-Instanz unit-testbar sein.

- **NFA-03 (HACS-Kompatibilität):** Die Integration SOLL den HACS-Anforderungen genügen (`custom_components/`, `manifest.json`, `config_flow: true`), um zukünftige Wartung/Verteilung zu erleichtern.

- **NFA-04 (HA-Versions-Kompatibilität):** Die Integration MUSS mit der im Projekt eingesetzten Home-Assistant-Core-Stable-Version kompatibel sein und darf keine deprecated APIs verwenden.

- **NFA-05 (Logging/Diagnostics):** Die Integration MUSS über das HA-native Logging nachvollziehbare Fehlermeldungen liefern und SOLL eine `diagnostics.py` für Support-Exporte bereitstellen.

- **NFA-06 (Rückwärtskompatibilität Konsumenten):** Bestehende Dashboards, Utility Meter und Automationen in `bsm/`, `solar/`, `mining/`, `home_appliances/`, `car/`, `report/`, `grid/`, die auf abstrahierte Sensoren verweisen, dürfen durch die Migration nicht brechen.

- **NFA-07 (Konfigurierbarkeit ohne Codeänderung):** Neue Geräte-Zuordnungen dürfen nach der Migration keine Änderungen am Python-Code erfordern (nur Config-Flow/Options).

- **NFA-08 (Wartbarkeit):** Code MUSS PEP8 und Type-Hints folgen (siehe `python-conventions.md`), mit Docstrings für Klassen/Methoden.

---

## 6. Abgrenzung / Out-of-Scope

- Umstellung von Zigbee2MQTT auf ZHA — nicht Gegenstand dieses Vorhabens.
- Änderungen an der InfluxDB-Bucket-/Measurement-Struktur — Migration betrifft nur Sensor-Erzeugung.
- Redesign der Dashboards (Mushroom/Layout-Card) — Entity-IDs bleiben stabil.
- Migration von `water_consumption.yaml` — kann als Folgeprojekt betrachtet werden.
- Neue Gerätetypen/Hardware-Anbindungen, die aktuell nicht abstrahiert sind — Scope ist Ablösung des YAML-Mechanismus.
- Public-HACS-Veröffentlichung — NFA-03 fordert nur Kompatibilität.

---

## 7. Risiken

- **Migration bestehender Utility Meter:** Utility Meter referenzieren Quell-Sensoren über `source:` per Entity-ID. Wird eine Entity-ID verändert, droht stiller Bruch der Utility-Meter-Kette.

- **Long-Term-Statistics/Recorder:** Home Assistant verknüpft Statistiken intern über `unique_id`. Eine neue Entity-Erzeugung (statt Wiederverwendung derselben `unique_id`) würde faktisch einen neuen Statistik-Strang erzeugen — bestehende Verlaufsdaten wären fragmentiert.

- **InfluxDB-Measurements:** Ändert sich der `entity_id`-String, entstehen in InfluxDB neue Zeitreihen statt Fortführung bestehender — Trendanalysen über den Migrationszeitpunkt hinweg wären gebrochen.

- **YAML/Integration-Koexistenz während Übergangsphase:** Solange nicht alle Geräte migriert sind, müssen beide Mechanismen parallel betrieben werden — Risiko doppelter Entities.

- **Config-Flow-Komplexität bei Sonderfällen:** Spezialfälle (ACE-1500-Fallback, invertierte Sensoren) lassen sich schwerer generisch im UI abbilden — Risiko einer Komplexitätsverlagerung von YAML nach Python.

- **Rollback-Strategie fehlt:** Es ist unklar, wie ein Rollback ohne erneuten History-Bruch durchführbar wäre.

- **Full-Restart-Bedarf:** Erstinstallation erfordert Full-Restart — Auswirkung auf Verfügbarkeit muss eingeplant werden.

---

## 8. Grober Migrationsplan (Phasen, ohne Zeitangaben)

1. **Proof-of-Concept:** Minimal-Integration mit Config-Flow für ein einzelnes Testgerät; Nachweis, dass `unique_id`-Wiederverwendung History-Kontinuität erhält.

2. **Kernlogik implementieren:** Python-Äquivalente für Spike-Filter, Verfügbarkeitslogik, Aggregation und Fallback-/Inverslogik, inkl. Unit-Tests.

3. **Parallelbetrieb-Fähigkeit sicherstellen:** Mechanismus, mit dem einzelne Geräte schrittweise von YAML auf die Integration umgezogen werden können.

4. **Pilotmigration Teilbestand:** Migration eines klar abgegrenzten Teilbestands (z. B. Basteltisch-Gruppe: 4 Steckdosen + Summensensor) inklusive Utility-Meter, unter Beobachtung.

5. **Validierung:** Prüfung von Recorder-Statistiken, InfluxDB-Zeitreihen und Utility-Meter-Ständen auf Kontinuität.

6. **Vollmigration verbleibender Geräte:** Schrittweise Übernahme der restlichen Geräte aus `energy_power.yaml`, `battery_power_energy.yaml`, `ace1500_power_energy.yaml`.

7. **YAML-Abbau:** Entfernen der migrierten Blöcke aus den Packages, sobald die Integration den kompletten Funktionsumfang abdeckt.

8. **Dokumentation & Übergabe:** Aktualisierung der projektinternen Regeln (`energy-abstraction.md`) auf den neuen Ziel-Mechanismus.

---

## Offene Punkte für Requirements-Phase

- Genaue technische Machbarkeit der `unique_id`-Wiederverwendung durch eine Custom-Integration (Entity-Registry-Verhalten bei Integrations-Wechsel) muss vor FA-09-Umsetzung technisch verifiziert werden.

- Entscheidung, ob Utility Meter weiterhin über HA-Core-Utility-Meter-Integration laufen (Konsument der neuen Sensoren) oder ob die Custom-Integration eigene Zähler-Entities bereitstellt.

- Entscheidung zum Umgang mit `water_consumption.yaml` (gleiches Muster, anderer Fachbereich) — eigenes Vorhaben oder gemeinsame Basis-Integration?
