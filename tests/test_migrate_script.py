"""Tests for the dev-only M1 migration generator (scripts/migrate_local_yaml.py).

Fixtures are copies of the .local/ abstraction packages so the tests do not
depend on the (untracked) production config at runtime.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from custom_components.abstractor.const import (
    CONF_FALLBACK_ON_ZERO,
    CONF_LEGACY_UNIQUE_ID,
    CONF_NET_SUBTRACT_ENTITY_ID,
)
from custom_components.abstractor.snapshot import validate_snapshot

_FIXTURES = Path(__file__).parent / "fixtures"

_spec = importlib.util.spec_from_file_location(
    "migrate_local_yaml", _REPO_ROOT / "scripts" / "migrate_local_yaml.py"
)
migrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate)


def _templates() -> dict[str, str]:
    return migrate.parse_templates(
        [_FIXTURES / "battery_power_energy.yaml", _FIXTURES / "ace1500_power_energy.yaml"]
    )


def test_parse_templates_extracts_names_and_unique_ids() -> None:
    templates = _templates()

    assert templates["Hyper2000 EG Aktuelle Leistung"] == (
        "ce963e07-64aa-4871-8c73-96edb8d284fe"
    )
    assert templates["ACE 1500 Batterie Ausgang Aktuelle Leistung"] == (
        "8bb94b14-3a14-4da1-8a55-24a676244d53"
    )
    # Utility meter unique_ids must not leak into the template map.
    assert "hyper2000_eg_energieeinspeisung_count" not in templates


def test_build_snapshot_validates_and_pins_legacy_ids() -> None:
    snapshot = migrate.build_snapshot(_templates())

    validate_snapshot(snapshot)
    by_title = {entry["title"]: entry for entry in snapshot["entries"]}
    eg_power = by_title["Hyper2000 EG Aktuelle Leistung"]
    assert eg_power["data"][CONF_LEGACY_UNIQUE_ID] == (
        "ce963e07-64aa-4871-8c73-96edb8d284fe"
    )
    assert eg_power["data"]["device_group_id"] == "hyper2000_eg"


def test_ace_discharge_carries_fallback_on_zero_config() -> None:
    snapshot = migrate.build_snapshot(_templates())

    by_title = {entry["title"]: entry for entry in snapshot["entries"]}
    discharge = by_title["ACE 1500 Batterie Ausgang Aktuelle Leistung"]
    data = discharge["data"]
    assert data[CONF_FALLBACK_ON_ZERO] is True
    assert data["fallback_source_entity_id"] == "sensor.ab2000x_33073_power"
    assert data["fallback_condition_entity_id"] == "sensor.ace_1500_output_pack_power"
    assert data["fallback_condition_state"] == "0"


def test_combined_power_uses_net_subtract_between_abstracted_sensors() -> None:
    snapshot = migrate.build_snapshot(_templates())

    by_title = {entry["title"]: entry for entry in snapshot["entries"]}
    combined = by_title["Zendure ACE 1500 Kombinierte Leistung"]
    assert combined["data"][CONF_NET_SUBTRACT_ENTITY_ID] == (
        "sensor.ace_1500_batterie_ausgang_aktuelle_leistung"
    )
    inverted = by_title["Zendure ACE 1500 Kombinierte Leistung (Invertiert)"]
    assert inverted["data"]["invert"] is True


def test_check_passes_against_fixtures() -> None:
    templates = _templates()
    snapshot = migrate.build_snapshot(templates)

    assert migrate.check_snapshot(snapshot, templates) == []


def test_check_fails_when_yaml_template_not_covered() -> None:
    templates = _templates()
    snapshot = migrate.build_snapshot(templates)
    # Simulate a YAML template the map forgot.
    templates["Zukünftiger Sensor XYZ"] = "00000000-0000-4000-8000-000000000000"

    problems = migrate.check_snapshot(snapshot, templates)

    assert any("not covered by migration map" in p for p in problems)


def test_main_check_mode_runs_against_fixtures(capsys) -> None:
    rc = migrate.main(
        [
            "--check",
            "--battery-yaml",
            str(_FIXTURES / "battery_power_energy.yaml"),
            "--ace-yaml",
            str(_FIXTURES / "ace1500_power_energy.yaml"),
        ]
    )

    assert rc == 0
    assert "CHECK OK" in capsys.readouterr().out


def test_main_prints_json_snapshot(capsys) -> None:
    rc = migrate.main(
        [
            "--battery-yaml",
            str(_FIXTURES / "battery_power_energy.yaml"),
            "--ace-yaml",
            str(_FIXTURES / "ace1500_power_energy.yaml"),
        ]
    )

    assert rc == 0
    snapshot = json.loads(capsys.readouterr().out)
    assert snapshot["format"] == "abstractor.snapshot"
    assert len(snapshot["entries"]) == len(migrate.MIGRATION_MAP)


def test_build_snapshot_rejects_unknown_template() -> None:
    with pytest.raises(KeyError):
        migrate.build_snapshot({})
