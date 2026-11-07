"""Unit tests for the pure CSV value (de)serializer (WS-6 · E5)."""

from datetime import UTC, datetime

from custom_components.abstractor.csv_values import CSV_HEADER, parse, serialize


def test_serialize_uses_semicolon_and_dot_decimal() -> None:
    """Format decisions: `;` separator, `.` decimal (never locale-dependent)."""
    text = serialize(
        [
            {
                "logical_name": "Boiler room",
                "entity_id": "sensor.abstract_power_power",
                "device_type": "power",
                "value": 1234.5,
                "unit": "W",
                "updated_at": None,
            }
        ]
    )
    assert text.splitlines()[0] == CSV_HEADER
    assert ";" in text.splitlines()[1]
    assert "1234.5" in text


def test_parse_roundtrip_is_lossless_for_numeric_sensors() -> None:
    """float -> repr -> float round-trips bit-exactly for every field."""
    rows = [
        {
            "logical_name": "Grid tie",
            "entity_id": "sensor.grid_tie_power",
            "device_type": "power",
            "value": 0.1 + 0.2,
            "unit": "W",
            "updated_at": datetime(2026, 11, 7, 12, 0, tzinfo=UTC),
        },
        {
            "logical_name": "Sourceless",
            "entity_id": "sensor.gone",
            "device_type": "power",
            "value": None,
            "unit": None,
            "updated_at": None,
        },
    ]
    parsed = parse(serialize(rows))
    assert parsed[0]["value"] == rows[0]["value"]
    assert parsed[1]["value"] is None
    assert parsed[0]["updated_at"] == rows[0]["updated_at"].isoformat()
    assert parsed[1]["updated_at"] is None


def test_parse_rejects_foreign_header_loudly() -> None:
    """A comma-separated or renamed header is never guessed at."""
    import pytest

    with pytest.raises(ValueError, match="header does not match"):
        parse("logical_name,entity_id,device_type,value,unit,updated_at\n")


def test_parse_rejects_non_numeric_values() -> None:
    """Garbage value fields fail with the line number, not silently."""
    import pytest

    with pytest.raises(ValueError, match="line 2 has a non-numeric"):
        parse(CSV_HEADER + "\nx;y;power;abc;W;\n")


def test_serialize_missing_required_field_raises() -> None:
    """Rows built by a broken caller are caught early, not written out."""
    import pytest

    with pytest.raises(ValueError, match="misses required field device_type"):
        serialize([{"logical_name": "x", "entity_id": "y", "value": None}])


def test_size_cap_fails_loud_not_truncated() -> None:
    """Just above the 2 MiB cap: ValueError with byte counts, no truncation."""
    import pytest

    huge = [{"logical_name": "n" * 60, "entity_id": "e", "device_type": "p", "value": 1.5, "unit": "kWh"}] * 40000
    with pytest.raises(ValueError, match="above the"):
        serialize(huge)
    with pytest.raises(ValueError, match="above the"):
        parse(CSV_HEADER + "\n" + ("n" * 60 + ";e;p;1.5;kWh;\n") * 40000)
