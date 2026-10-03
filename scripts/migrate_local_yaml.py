"""Dev-only generator: .local battery YAML abstraction layer -> Abstractor snapshot.

Parses the hand-written template/utility_meter packages for the Zendure
batteries (Hyper2000 EG/OG, ACE 1500) and emits a snapshot JSON document that
`abstractor.import_data` accepts, so the sensors are restored as subentries
with their YAML `unique_id` pinned as `legacy_unique_id` (REQ-CORE-003:
recorder history keeps counting).

PyYAML is deliberately NOT used (not a project dependency): the parser is a
line-based extractor for the exact subset these files use (`- name:` /
`unique_id:` / `variables.source:` / `source:` entries plus block comments).
It is not a general YAML parser.

Usage (repo root):
    python scripts/migrate_local_yaml.py [--check] [--out PATH] \
        [--battery-yaml PATH] [--ace-yaml PATH]

--check validates the emitted snapshot against the integration's own
`validate_snapshot` and cross-checks that every template found in the YAML is
covered exactly once by the migration map (and vice versa).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from custom_components.abstractor.const import (  # noqa: E402
    CONF_DEVICE_GROUP_ID,
    CONF_DEVICE_TYPE,
    CONF_FALLBACK_CONDITION_ENTITY_ID,
    CONF_FALLBACK_CONDITION_STATE,
    CONF_FALLBACK_ON_ZERO,
    CONF_FALLBACK_SOURCE_ENTITY_ID,
    CONF_INVERT,
    CONF_LEGACY_UNIQUE_ID,
    CONF_NET_SUBTRACT_ENTITY_ID,
    CONF_SOURCE_ENTITY_ID,
    CONF_SPIKE_FILTER,
    TYPE_ENERGY,
    TYPE_POWER,
)
from custom_components.abstractor.snapshot import (  # noqa: E402
    SNAPSHOT_FORMAT,
    SNAPSHOT_VERSION,
    validate_snapshot,
)

DEFAULT_BATTERY_YAML = _REPO_ROOT / ".local" / "battery_power_energy.yaml"
DEFAULT_ACE_YAML = _REPO_ROOT / ".local" / "ace1500_power_energy.yaml"

_NAME_RE = re.compile(r'^\s*- name: "?(?P<name>[^"\n]+?)"?\s*$')
_UNIQUE_ID_RE = re.compile(r'^\s*unique_id: "?(?P<uid>[^"\n]+?)"?\s*$')

# Migration map: one entry per abstractor subentry. `template` names the YAML
# template whose identity (unique_id) and title this subentry takes over;
# remaining keys are the subentry `data` fields. See
# docs/migration-m1-batteries.md for the full mapping and semantic notes.
MIGRATION_MAP: list[dict[str, Any]] = [
    # --- Hyper2000 EG ---
    {
        "template": "Hyper2000 EG Aktuelle Leistung",
        "device_group_id": "hyper2000_eg",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.shelly_plug_hyper2000_eg_power",
        },
    },
    {
        "template": "Hyper2000 EG Gesamtverbrauch",
        "device_group_id": "hyper2000_eg",
        "data": {
            CONF_DEVICE_TYPE: TYPE_ENERGY,
            CONF_SOURCE_ENTITY_ID: "sensor.shelly_plug_hyper2000_eg_consumed_energy",
            CONF_SPIKE_FILTER: True,
        },
    },
    {
        "template": "Hyper2000 EG Energieeinspeisung",
        "device_group_id": "hyper2000_eg",
        "data": {
            CONF_DEVICE_TYPE: TYPE_ENERGY,
            CONF_SOURCE_ENTITY_ID: "sensor.shelly_plug_hyper2000_eg_returned_energy",
            CONF_SPIKE_FILTER: True,
        },
    },
    {
        "template": "Hyper2000 EG Aktuelle Leistung (Invertiert)",
        "device_group_id": "hyper2000_eg",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.shelly_plug_hyper2000_eg_power",
            CONF_INVERT: True,
        },
    },
    # --- Hyper2000 OG ---
    {
        "template": "Hyper2000 OG Aktuelle Leistung",
        "device_group_id": "hyper2000_og",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.solarbatterie_shelly_plug_switch_0_power",
        },
    },
    {
        "template": "Hyper2000 OG Gesamtverbrauch",
        "device_group_id": "hyper2000_og",
        "data": {
            CONF_DEVICE_TYPE: TYPE_ENERGY,
            CONF_SOURCE_ENTITY_ID: "sensor.solarbatterie_shelly_plug_consumed_energy",
            CONF_SPIKE_FILTER: True,
        },
    },
    {
        "template": "Hyper2000 OG Energieeinspeisung",
        "device_group_id": "hyper2000_og",
        "data": {
            CONF_DEVICE_TYPE: TYPE_ENERGY,
            CONF_SOURCE_ENTITY_ID: "sensor.solarbatterie_shelly_plug_returned_energy",
            CONF_SPIKE_FILTER: True,
        },
    },
    {
        "template": "Hyper2000 OG Aktuelle Leistung (Invertiert)",
        "device_group_id": "hyper2000_og",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.solarbatterie_shelly_plug_switch_0_power",
            CONF_INVERT: True,
        },
    },
    # --- ACE 1500 ---
    {
        "template": "ACE 1500 Shelly Aktuelle Leistung",
        "device_group_id": "ace_1500",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.shelly_plug_ace1500_leistung",
        },
    },
    {
        "template": "ACE 1500 Batterie Eingang Aktuelle Leistung",
        "device_group_id": "ace_1500",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.ace_1500_output_pack_power",
        },
    },
    {
        # YAML: primary > 0 ? primary : (fallback > 0 && charging == 0 ? fallback : 0)
        # -> fallback_on_zero replicates it (see docs/migration-m1-batteries.md §3.1)
        "template": "ACE 1500 Batterie Ausgang Aktuelle Leistung",
        "device_group_id": "ace_1500",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.ace_1500_pack_input_power",
            CONF_FALLBACK_ON_ZERO: True,
            CONF_FALLBACK_SOURCE_ENTITY_ID: "sensor.ab2000x_33073_power",
            CONF_FALLBACK_CONDITION_ENTITY_ID: "sensor.ace_1500_output_pack_power",
            CONF_FALLBACK_CONDITION_STATE: "0",
        },
    },
    {
        "template": "ACE 1500 Aktuelle AC Leistung",
        "device_group_id": "ace_1500",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.ace_1500_ac_output_power",
        },
    },
    {
        "template": "ACE 1500 Shelly Gesamtverbrauch",
        "device_group_id": "ace_1500",
        "data": {
            CONF_DEVICE_TYPE: TYPE_ENERGY,
            CONF_SOURCE_ENTITY_ID: "sensor.shelly_plug_ace1500_energie",
            CONF_SPIKE_FILTER: True,
        },
    },
    {
        "template": "ACE 1500 Gesamtverbrauch AC",
        "device_group_id": "ace_1500",
        "data": {
            CONF_DEVICE_TYPE: TYPE_ENERGY,
            CONF_SOURCE_ENTITY_ID: "sensor.ace_1500_aggr_discharge",
            CONF_SPIKE_FILTER: True,
        },
    },
    {
        "template": "ACE 1500 Shelly Aktuelle Leistung (Invertiert)",
        "device_group_id": "ace_1500",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.shelly_plug_ace1500_leistung",
            CONF_INVERT: True,
        },
    },
    {
        "template": "ACE 1500 Aktuelle Leistung AC (Invertiert)",
        "device_group_id": "ace_1500",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.ace_1500_ac_output_power",
            CONF_INVERT: True,
        },
    },
    {
        # Sources are the ABSTRACTED ace_1500 in/out sensors; reads the
        # previous poll cycle, exactly like the YAML template chain did.
        "template": "Zendure ACE 1500 Kombinierte Leistung",
        "device_group_id": "ace_1500",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.ace_1500_batterie_eingang_aktuelle_leistung",
            CONF_NET_SUBTRACT_ENTITY_ID: "sensor.ace_1500_batterie_ausgang_aktuelle_leistung",
        },
    },
    {
        "template": "Zendure ACE 1500 Kombinierte Leistung (Invertiert)",
        "device_group_id": "ace_1500",
        "data": {
            CONF_DEVICE_TYPE: TYPE_POWER,
            CONF_SOURCE_ENTITY_ID: "sensor.ace_1500_batterie_eingang_aktuelle_leistung",
            CONF_NET_SUBTRACT_ENTITY_ID: "sensor.ace_1500_batterie_ausgang_aktuelle_leistung",
            CONF_INVERT: True,
        },
    },
]


# Templates deliberately NOT migrated (see docs/migration-m1-batteries.md §3.3):
# the Ladung/Einspeisung clip splits need a clip filter abstractor does not
# have yet (positive/negative part of one Shelly reading).
NOT_MIGRATED: dict[str, str] = {
    "Batterie Ladung Shelly Plug Hyper OG": "clip split (max(0, x)) — no clip filter yet",
    "Batterie Einspeisung Ausgelesen Local Hyper OG": "clip split (min(0, x)) — no clip filter yet",
    "Batterie Einspeisung Normiert Local Hyper OG": "clip split; YAML also references a nonexistent entity (latent bug, doc §3.2)",
    "Batterie Ladung Shelly Plug Hyper EG": "clip split (max(0, x)) — no clip filter yet",
    "Batterie Einspeisung Ausgelesen Local Hyper EG": "clip split (min(0, x)) — no clip filter yet",
    "Batterie Einspeisung Normiert Local Hyper EG": "clip split — no clip filter yet",
}


def parse_templates(paths: list[Path]) -> dict[str, str]:
    """Extract ``template name -> unique_id`` from the YAML packages.

    Line-based on purpose (no PyYAML dependency): recognizes `- name:` /
    `unique_id:` pairs and ignores everything else, including YAML anchors,
    utility_meter blocks, and comments.
    """
    templates: dict[str, str] = {}
    pending_name: str | None = None
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            name_match = _NAME_RE.match(line)
            if name_match:
                pending_name = name_match.group("name")
                continue
            uid_match = _UNIQUE_ID_RE.match(line)
            if uid_match and pending_name:
                templates[pending_name] = uid_match.group("uid")
                pending_name = None
    return templates


def build_snapshot(templates: dict[str, str]) -> dict[str, Any]:
    """Build the importable snapshot from the map + parsed identities."""
    entries = []
    for item in MIGRATION_MAP:
        name = item["template"]
        if name not in templates:
            raise KeyError(f"template {name!r} not found in YAML sources")
        data = dict(item["data"])
        data[CONF_LEGACY_UNIQUE_ID] = templates[name]
        data[CONF_DEVICE_GROUP_ID] = item["device_group_id"]
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        entries.append(
            {
                "entry_id": f"abstractor_m1_{slug}",
                "data": data,
                "options": {},
                "title": name,
                "unique_id": None,
                "version": 1,
            }
        )
    return {
        "format": SNAPSHOT_FORMAT,
        "version": SNAPSHOT_VERSION,
        "entries": entries,
        "values": {},
    }


def check_snapshot(snapshot: dict[str, Any], templates: dict[str, str]) -> list[str]:
    """Validate the snapshot and the map<->YAML cross-check.

    Returns a list of problems (empty = OK).
    """
    problems: list[str] = []
    try:
        validate_snapshot(snapshot)
    except Exception as err:  # noqa: BLE001 - reported as a check problem
        problems.append(f"snapshot schema invalid: {err}")
    covered = {entry["title"] for entry in snapshot["entries"]}
    for name in templates:
        if name not in covered and name not in NOT_MIGRATED:
            problems.append(f"YAML template not covered by migration map: {name!r}")
    for entry in snapshot["entries"]:
        if entry["title"] not in templates:
            problems.append(f"map entry without YAML template: {entry['title']!r}")
    ids = [entry["data"][CONF_LEGACY_UNIQUE_ID] for entry in snapshot["entries"]]
    for uid in set(ids):
        if ids.count(uid) > 1:
            problems.append(f"legacy_unique_id used more than once: {uid}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate instead of printing")
    parser.add_argument("--out", type=Path, help="output path (default: stdout)")
    parser.add_argument("--battery-yaml", type=Path, default=DEFAULT_BATTERY_YAML)
    parser.add_argument("--ace-yaml", type=Path, default=DEFAULT_ACE_YAML)
    args = parser.parse_args(argv)

    templates = parse_templates([args.battery_yaml, args.ace_yaml])
    snapshot = build_snapshot(templates)
    payload = json.dumps(snapshot, indent=2, ensure_ascii=False)

    if args.check:
        problems = check_snapshot(snapshot, templates)
        if problems:
            for problem in problems:
                print(f"CHECK FAILED: {problem}", file=sys.stderr)
            return 1
        print(f"CHECK OK: {len(snapshot['entries'])} subentries, "
              f"{len(templates)} YAML templates covered")
        return 0

    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
