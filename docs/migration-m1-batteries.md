# M1 Migration: Zendure-Batterien (.local YAML → Abstractor)

**Status:** mapping final, migration tooling in `scripts/migrate_local_yaml.py`
**Scope:** `.local/battery_power_energy.yaml` (Hyper2000 EG/OG), `.local/ace1500_power_energy.yaml` (ACE 1500)
**Ziel:** Recorder-Historie bleibt erhalten — jede YAML-`unique_id` wird als `legacy_unique_id` der Subentry übernommen (REQ-CORE-003).

## 1. Mapping-Regeln

| YAML-Konstrukt | Abstractor-Subentry |
|---|---|
| `state: states(source)` (1:1-Passthrough) | `source_entity_id`, Pipeline-Passthrough (default) |
| `*power_inverse_logic` (`val * -1`) | `invert: true` |
| `*energy_logic` (kWh, total_increasing) | `device_type: energy` + `spike_filter: true` (monotoner Wächter ersetzt `has_value`-Availability) |
| Utility Meter (`source: <template-sensor>`) | **bleibt** HA-Utility-Meter; Quelle nach Migration auf den abstrahierten Sensor umstellen (`sensor.abstract_*`) |
| Riemann-`integration`-Sensor (ACE 1500 Batterie Ausgang Energie Raw) | **bleibt** (REQ-SENS-003 ist Zukunft); Quelle auf abstrahierten Ausgang-Sensor umstellen |
| Geräte-Gruppierung pro Batterie | `device_group_id` pro Batterie (Hyper2000_EG / Hyper2000_OG / ACE_1500) |

## 2. Subentry-Definitionen

### Hyper2000 EG (`device_group_id: hyper2000_eg`)

| YAML-Template (entity) | unique_id | Subentry |
|---|---|---|
| Hyper2000 EG Aktuelle Leistung | `ce963e07-64aa-4871-8c73-96edb8d284fe` | power, source `sensor.shelly_plug_hyper2000_eg_power` |
| Hyper2000 EG Gesamtverbrauch | `2a7f2d8d-c4e1-43ca-8a8d-3679a69473f8` | energy, source `sensor.shelly_plug_hyper2000_eg_consumed_energy`, spike_filter |
| Hyper2000 EG Energieeinspeisung | `1b674347-0e19-492c-a6c8-b0877d777c96` | energy, source `sensor.shelly_plug_hyper2000_eg_returned_energy`, spike_filter |
| Hyper2000 EG Aktuelle Leistung (Invertiert) | `b2704134-63c1-4a21-a89f-77e6bcb02cf3` | power, source `sensor.shelly_plug_hyper2000_eg_power`, invert |

Utility-Meter `hyper2000_eg_*_count`: bleiben, Quelle → abstrahierte Energie-Sensoren.

### Hyper2000 OG (`device_group_id: hyper2000_og`)

| YAML-Template | unique_id | Subentry |
|---|---|---|
| Hyper2000 OG Aktuelle Leistung | `2ed029a3-ef87-4a1d-8ee6-ee1d24e3ce35` | power, source `sensor.solarbatterie_shelly_plug_switch_0_power` |
| Hyper2000 OG Gesamtverbrauch | `387eabc3-620e-4023-be10-c9b75a34be29` | energy, source `sensor.solarbatterie_shelly_plug_consumed_energy`, spike_filter |
| Hyper2000 OG Energieeinspeisung | `0f420cc6-3131-4fad-98d4-5c1196b52571` | energy, source `sensor.solarbatterie_shelly_plug_returned_energy`, spike_filter |
| Hyper2000 OG Aktuelle Leistung (Invertiert) | `5ab57dcd-b093-4170-8034-820d2e90a86d` | power, source `sensor.solarbatterie_shelly_plug_switch_0_power`, invert |

### ACE 1500 (`device_group_id: ace_1500`)

| YAML-Template | unique_id | Subentry |
|---|---|---|
| ACE 1500 Shelly Aktuelle Leistung | `7d35baef-909f-4c4c-a4a9-c5149cfd0dab` | power, source `sensor.shelly_plug_ace1500_leistung` |
| ACE 1500 Batterie Eingang Aktuelle Leistung | `30c88984-3cbb-4e47-8a9e-0cc9eed78886` | power, source `sensor.ace_1500_output_pack_power` |
| ACE 1500 Batterie Ausgang Aktuelle Leistung | `8bb94b14-3a14-4da1-8a55-24a676244d53` | power, source `sensor.ace_1500_pack_input_power`, **fallback_on_zero**, fallback_source `sensor.ab2000x_33073_power`, condition `sensor.ace_1500_output_pack_power == "0"` |
| ACE 1500 Aktuelle AC Leistung | `c221b359-720b-497d-a2d3-468ebf6ee33f` | power, source `sensor.ace_1500_ac_output_power` |
| ACE 1500 Shelly Gesamtverbrauch | `5ca440fb-3286-422c-8699-2ca9c2970821` | energy, source `sensor.shelly_plug_ace1500_energie`, spike_filter |
| ACE 1500 Gesamtverbrauch AC | `0a46f895-685b-473c-994d-5a115d84bffc` | energy, source `sensor.ace_1500_aggr_discharge`, spike_filter |
| ACE 1500 Shelly Aktuelle Leistung (Invertiert) | `3dde5eb4-53ff-4de2-b89a-5a40e0cc8ddc` | power, source `sensor.shelly_plug_ace1500_leistung`, invert |
| ACE 1500 Aktuelle Leistung AC (Invertiert) | `3dde5eb4-53ff-4de2-b89a-5a40e0cc8dde` | power, source `sensor.ace_1500_ac_output_power`, invert |
| Zendure ACE 1500 Kombinierte Leistung | `c7a6e5f3-bd36-4064-8358-25738f315170` | power, source `sensor.ace_1500_batterie_eingang_aktuelle_leistung` (abstrahiert!), net_subtract `sensor.ace_1500_batterie_ausgang_aktuelle_leistung` (abstrahiert!) |
| Zendure ACE 1500 Kombinierte Leistung (Invertiert) | `67c5a783-0bda-437a-b45b-34aa1f454e89` | wie oben + invert |

Hinweis "Kombinierte Leistung": Quellen sind die **abstrahierten** Eingangs-/Ausgangssensoren. Das liest den Vor-Poll-Zyklus (genau wie die YAML-Templates untereinander) — ein Poll Verzögerung, identisches Verhalten zur Status quo.

## 3. Semantische Befunde

1. **ACE 1500 Ausgang — Fallback-on-Zero (gelöst in diesem Branch).** YAML: `primary > 0 ? primary : (fallback > 0 && charging == 0 ? fallback : 0)`. Abstractors REQ-COMP-004-Fallback feuerte nur bei `total is None` — für Power wegen Fail-Soft-0 nie. Neuer `fallback_on_zero`-Flag (REQ-COMP-004-Erweiterung) macht die Template-Semantik expressibel. Bedingung `charging == 0` = String-Vergleich gegen HA-State `"0"` — numerisch äquivalent, da der Zendure-Sensor ganzzahlige W meldet.
2. **⚠ Latenter Bug im YAML (Hyper2000 OG):** "Batterie Einspeisung Normiert Local Hyper OG" (`26bb9711-8c08-485e-87ce-8ce5209f0573`) liest `sensor.batterie_einspeisung_ausgelesen_local` — diese Entity existiert nicht (die OG-Quelle heißt `..._ausgelesen_local_hyper_og`, EG-Variante `..._hyper_eg`). Der Sensor liefert daher dauerhaft 0. Nicht 1:1 migrieren — beim Umzug auf `invert` des OG-Ausgelesen-Sensors wird der Wert korrekt (Wertänderung gegenüber heute, Absprache mit User nötig).
3. **Nicht abbildbar — Clipping-Splits (6 Templates):** "Batterie Ladung/Einspeisung (Ausgelesen|Normiert) Hyper EG/OG" implementieren `max(0, x)` / `min(0, x)`-Clips des Shelly-Messwerts. Abstractor hat keinen Clip-Filter (B-Backlog). Die Kern-Abstraktionen (Aktuelle Leistung, Invertiert, Energie) sind migrierbar; Consumer der Clip-Sensoren vor Migration umstellen oder Clip-Filter als Folge-Feature bauen.
4. **Availability:** Die YAML-`availability`-Guards (`has_value and is_number`) entsprechen den Abstractor-Parse-Regeln (unavailable/unknown/non-numeric → reject); Energy/Water failen geschlossen statt unavailable — Utility-Meter-relevant, Verhalten in Parity-Phase prüfen (M5).

## 4. Durchführung (nach Merge)

1. `python scripts/migrate_local_yaml.py --check` (validiert Snapshot + unique_id-Vollständigkeit gegen die .local-Dateien).
2. Snapshot erzeugen, in der HA-Instanz `abstractor.import_data` aufrufen → Subentries werden identitätsgleich restored (Phase-1/B6).
3. Utility-Meter-Quellen auf die `sensor.abstract_*`-Entities umstellen; YAML-Packages deaktivieren (M5: 48 h Parity-Lauf, dann entfernen).
