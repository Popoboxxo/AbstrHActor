# Requirements Specification: Abstractor (Energy Abstraction Layer)

## 1. Einleitung & Zielsetzung
Das Projekt **Abstractor** ist eine Home Assistant Custom Integration. Ihr primäres Ziel ist es, physische Hardware-Sensoren (wie z.B. Smart Plugs, Zähler) über eine Software-Abstraktionsebene von den konsumierenden Automatisierungen, Dashboards und Utility Metern zu entkoppeln.
Dadurch wird ein nahtloser Hardware-Tausch bei Defekten möglich, ohne dass Logiken angepasst werden müssen. Gleichzeitig schützt die Abstraktionsebene Langzeitstatistiken vor Hardware-Fehlern (wie unerwarteten Null-Werten).

## 2. Core Features (REQ-CORE)

- **REQ-CORE-001 (Geräte-Entkopplung):** Die Integration MUSS physische Hardware-Entitäten logisch abstrahieren. Wenn eine Hardware ausfällt oder getauscht wird, kann der abstrahierte Sensor auf ein neues Quell-Gerät umkonfiguriert werden, ohne dass sich die `entity_id` oder `unique_id` des abstrahierten Sensors für den Nutzer ändert.
- **REQ-CORE-002 (Config Flow):** Die Konfiguration und das Zuordnen von Geräten (Discovery, Hinzufügen, Ändern) MUSS über die Home Assistant UI (Config Flow) erfolgen, um fehleranfälliges YAML-Boilerplate zu ersetzen.
- **REQ-CORE-003 (Historien-Kontinuität):** Bei der Migration bestehender YAML-Template-Sensoren MÜSSEN deren bestehende `unique_id`-Werte übernommen werden können, damit die Home Assistant Recorder/Long-Term-Statistics nicht abreißen.
- **REQ-CORE-004 (Aggregations-Unterstützung):** Die Integration MUSS es erlauben, mehrere physische Geräte (z.B. mehrere Steckdosen einer Leiste) logisch zu einem einzigen summierten Abstractor-Gerät zusammenzufassen.
- **REQ-CORE-005 (Werte-Transformation):** Die Integration MUSS einfache Transformationen von Quell-Werten unterstützen (z.B. Invertierung von Leistungs-Sensoren mittels `Wert * -1` oder Berechnung von Netto-Flüssen wie `Laden - Entladen`).
- **REQ-CORE-006 (Geräte-Clustering / HA Device Registry):** Abstrahierte Sensoren dürfen nicht als lose Helfer-Entitäten (Orphans) in Home Assistant angelegt werden. Die Integration MUSS über die `device_info` Property sicherstellen, dass zusammengehörige abstrakte Sensoren (z.B. Power, Energy und Voltage eines abstrakten "Kühlschranks") als ein gemeinsames, logisches "Device" in der HA Geräte-Registry gruppiert werden. Das Cluster (Name, Hersteller, Modell) muss im Config Flow anpassbar sein.
- **REQ-CORE-007 (Rekonfiguration / Options Flow):** Um Hardware reibungslos zu tauschen, MUSS es möglich sein, bestehende abstrahierte Geräte über die Benutzeroberfläche (Options Flow) nachträglich neu zu konfigurieren (z.B. Austausch der Quell-Entity-ID), ohne das abstrakte Gerät löschen und neu anlegen zu müssen.

## 3. Fehler- & Schwankungskompensation (REQ-COMP)

- **REQ-COMP-001 (Spike-Filter für Energy):** Die Integration MUSS einen monotonen Wachstums-Wächter ("Spike-Filter") für Energie-Sensoren implementieren. Fällt der Quell-Wert durch einen Geräte-Fehler auf 0 oder einen Wert kleiner als der zuletzt gültige Stand, darf dieser Drop nicht an den abstrahierten Sensor durchgereicht werden.
- **REQ-COMP-002 (Verfügbarkeits-Logik / Availability):** Ist die Quelle `unavailable` oder `unknown`, muss die Integration dies intelligent handhaben, ohne CPU-Spikes zu verursachen (wie es oft bei ungefilterten Jinja-Templates passiert).
- **REQ-COMP-003 (Power Fallback):** Power-Sensoren (aktuelle Leistung in Watt) MÜSSEN sich auf 0 (statt `unavailable`) setzen, wenn die Quelle temporär keine Daten liefert, sofern nicht explizit anders konfiguriert.
- **REQ-COMP-004 (Bedingter Sensor-Fallback):** Es MUSS möglich sein, bei Ausfall oder Nullwert eines Primärsensors auf einen alternativen Hardware-Sensor zurückzugreifen. Dieser Fallback muss an Bedingungen geknüpft werden können (z.B. "Nutze Sensor B, aber nur, wenn Ladevorgang in Sensor C = 0 ist").
- **REQ-COMP-005 (Konfigurierbare Pipeline & Pass-Through):** Alle Filter-Mechanismen MÜSSEN als generische, erweiterbare Pipeline-Module konzipiert sein. Es MUSS zwingend möglich sein, die Pipeline pro Sensor komplett zu deaktivieren, sodass Werte als reiner Pass-Through 1:1 ohne jegliche Modifikation durchgereicht werden.

## 4. Utility Meter Integration (REQ-UTIL)

- **REQ-UTIL-001 (Integrierter Utility Meter):** Die Integration SOLL selbstständig in der Lage sein, Langzeit-Statistiken (Tages-, Monats-, Jahresverbrauch) bereitzustellen, vergleichbar mit den nativen Home Assistant Utility Metern.
- **REQ-UTIL-002 (Externe Utility Meter Kompatibilität):** Alternativ MUSS die Integration es erlauben, externe/bestehende Home Assistant Utility Meter anzubinden. Diese bestehenden Zähler sollen ohne Unterbrechung weiter hochzählen können, indem sie die abstrahierten Sensoren der Integration konsumieren.

## 5. Sensor Types & Bridge Implementations (REQ-SENS)

- **REQ-SENS-001 (Unterstützte Sensortypen):** Zunächst MÜSSEN Power (W), Energy (kWh) und Water (L/m³) Sensoren abstrahiert werden. Das Architektur-Konzept MUSS aber generisch genug sein, um "alle möglichen Sensor-Typen" in künftigen Iterationen leicht anbinden zu können.
- **REQ-SENS-002 (Hardware-Agnostik):** Die Integration agiert komplett agnostisch zur darunterliegenden Hardware-Anbindung (egal ob MQTT, Serial, HTTP oder ZHA).
- **REQ-SENS-003 (Riemann-Integration):** Ist hardwareseitig nur ein Leistungs-Sensor (Power in W) vorhanden, SOLL die Integration optional fähig sein, die Energie (Energy in kWh) selbstständig mittels Riemann-Integral zu berechnen (analog zur HA Core Integration `integration`).
- **REQ-SENS-004 (Generische Architektur & Extensibility):** Das System MUSS so generisch aufgebaut sein, dass neue Sensoren, Werte, Schalter oder auch Custom Components mit minimalem Aufwand eingebunden werden können. Der Abstraktionslayer soll leicht wiederverwendbar (reusable) oder über Schablonen generierbar sein.

## 6. Non-Functional Requirements (REQ-NFA)

- **REQ-NFA-001 (Performance):** Die Implementierung in Python darf keine CPU-Spikes erzeugen, was oft durch fehlerhaftes Polling in Template-Sensoren passiert.
- **REQ-NFA-002 (Testbarkeit):** Die Kernlogik (vor allem der Spike-Filter und das Zählwerk) MUSS unabhängig von HA Core unit-testbar sein.
- **REQ-NFA-003 (HA Core Compliance):** Keine Verwendung veralteter APIs; Kompatibilität mit der jeweils aktuellen Home Assistant Core Stable-Version.
- **REQ-NFA-004 (Abwärtskompatibilität & Migrationen):** Die Integration MUSS strikt abwärtskompatibel entwickelt werden. Sollten in Zukunft "Breaking Changes" unvermeidbar sein, MÜSSEN automatische Migrationsskripte bereitgestellt werden, um die Konfiguration der Nutzer ohne manuellen Eingriff zu korrigieren.
- **REQ-NFA-005 (Non-invasiv & Saubere Speicherung):** Die Integration MUSS non-invasiv in das Home Assistant Hauptsystem eingreifen und alle eigenen Konfigurationen und Zustände sauber und standardkonform speichern (z.B. in `.storage/`).
- **REQ-NFA-006 (Diagnostics & Debugging):** Die Integration MUSS die native HA Diagnostics-API (`async_get_device_diagnostics`) implementieren, damit Nutzer bei Fehlkonfigurationen (z.B. greifende Spike-Filter, fehlerhafte Quellsensoren) auf Knopfdruck ein JSON-Log zur Fehleranalyse herunterladen können.

## 7. Data Management & Resilience (REQ-DATA)

- **REQ-DATA-001 (Export/Import & Backup):** Um historischen Datenverlust bei Systemfehlern oder Hardware-Ausfällen absolut auszuschließen, MUSS das System eine Möglichkeit bieten, die Zustands- und Verbrauchsdaten (z.B. Zählerstände) im Notfall manuell zu exportieren und wieder zu importieren.
- **REQ-DATA-002 (InfluxDB Telemetry Push):** Die Integration SOLL eine optionale, dedizierte InfluxDB-Anbindung bieten. Damit können die abstrahierten Sensorwerte (nach der Filter-Pipeline) unabhängig vom HA-Recorder in einen eigenen InfluxDB-Bucket gepusht werden (für isolierte Langzeit-Analysen und maximale Datensicherheit).
