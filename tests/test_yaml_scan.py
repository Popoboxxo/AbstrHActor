"""Tests for the read-only YAML template scanner (WS-3, UF-05)."""

from custom_components.abstractor.yaml_scan import scan_config_dir, scan_template_sensors


def test_scan_reports_named_template_sensors_only() -> None:
    text = (
        "template:\n"
        "  sensors:\n"
        "    - name: Hyper EG Power\n"
        "      unique_id: hyper_eg_power_tpl\n"
        "      unit_of_measurement: W\n"
        "      entity_1:\n"
        "        entity_id: sensor.hyper_power\n"
        "utility_meter:\n"
        "  source_aux:\n"
        "    - name: Meter Only\n"
        "      unique_id: meter_only\n"
    )
    rows = scan_template_sensors(text)
    assert len(rows) == 1
    assert rows[0]["unique_id"] == "hyper_eg_power_tpl"
    assert rows[0]["suggested_logical_name"] == "hyper_eg_power"
    assert rows[0]["source_entities"] == ["sensor.hyper_power"]
    assert rows[0]["history_preservable"] is True
    assert rows[0]["blockers"] == []


def test_scan_flags_missing_identity_and_duplicates() -> None:
    text = (
        "template:\n"
        "  sensors:\n"
        "    - name: No Id\n"
        "      unit_of_measurement: kWh\n"
        "    - name: Dup A\n"
        "      unique_id: shared_id\n"
        "      entity_id: sensor.a\n"
        "    - name: Dup B\n"
        "      unique_id: shared_id\n"
        "      entity_id: sensor.b\n"
    )
    rows = scan_template_sensors(text)
    assert rows[0]["unique_id"] is None
    assert any(blocker.startswith("no unique_id") for blocker in rows[0]["blockers"])
    assert rows[1]["history_preservable"] is False
    assert rows[1]["blockers"] == ["duplicate unique_id"]
    assert rows[2]["blockers"] == ["duplicate unique_id"]


def test_scan_skips_hidden_and_secret_files() -> None:
    import tempfile
    from pathlib import Path

    def _mk(tmp: Path) -> Path:
        config = tmp / "cfg"
        config.mkdir(parents=True, exist_ok=True)
        (config / "main.yaml").write_text("template:\n  sensors: []\n", encoding="utf-8")
        (config / ".hidden.yaml").write_text("template:\n  sensors: []\n", encoding="utf-8")
        (config / "secrets_bridge.yaml").write_text("template:\n  sensors: []\n", encoding="utf-8")
        sub = config / "data"
        sub.mkdir()
        (sub / "nested.yaml").write_text("template:\n  sensors: []\n", encoding="utf-8")
        return config

    with tempfile.TemporaryDirectory() as tmp:
        config = _mk(Path(tmp))
        rows, scanned = scan_config_dir(str(config))
        names = [Path(p).name for p in scanned]
        assert names == ["main.yaml"]
        assert rows == []
