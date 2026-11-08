"""Pure CSV (de)serialization for abstracted sensor values (WS-6 · E5).

Format decisions (fixed by the module, locale-independent):

- Separator: ``;`` (never ``,`` — German users paste comma decimals).
- Decimal separator on the wire: always ``.`` — float values are written
  with ``repr(float)`` and parsed back with the same rule, so a numeric
  round-trip is loss-free.
- ``None`` values are written as the empty field; parsing maps the empty
  field back to ``None``.
- ``updated_at`` is an ISO-8601 string or empty; the CSV never re-creates
  clock state, it documents it.
- Size cap: 2 MiB of UTF-8 — violated loudly (ValueError), never silently
  truncated.

The module stays free of HomeAssistant imports so it can be unit-tested
without the HA runtime (mirroring ``filters.py`` and ``yaml_scan.py``).
"""

from collections.abc import Iterable, Mapping
from typing import Any

CSV_SEPARATOR: str = ";"
CSV_HEADER_FIELDS: tuple[str, ...] = (
    "logical_name",
    "entity_id",
    "device_type",
    "value",
    "unit",
    "updated_at",
)
CSV_HEADER: str = CSV_SEPARATOR.join(CSV_HEADER_FIELDS)
CSV_MAX_BYTES: int = 2 * 1024 * 1024


def _size_guard(text: str) -> None:
    """Fail loud when the payload exceeds the documented 2 MiB cap."""
    size = len(text.encode("utf-8"))
    if size > CSV_MAX_BYTES:
        raise ValueError(
            f"CSV payload is {size} bytes, above the {CSV_MAX_BYTES} byte cap"
        )


def serialize(rows: Iterable[Mapping[str, Any]]) -> str:
    """Serialize value rows into the fixed CSV format.

    Raises:
        ValueError: If a row misses a required header field or the payload
            exceeds the 2 MiB cap.
    """
    lines = [CSV_HEADER]
    for row in rows:
        for field in CSV_HEADER_FIELDS[:-1]:  # updated_at may be empty
            if field not in row:
                raise ValueError(f"row misses required field {field}")
        value = row["value"]
        if value is None:
            value_text = ""
        elif isinstance(value, float):
            value_text = repr(value)
        elif isinstance(value, int):
            value_text = str(value)
        else:
            value_text = str(value)
        updated_at = row.get("updated_at")
        lines.append(
            CSV_SEPARATOR.join(
                (
                    str(row["logical_name"]),
                    str(row["entity_id"]),
                    str(row["device_type"]),
                    value_text,
                    str(row.get("unit") or ""),
                    updated_at.isoformat() if updated_at is not None else "",
                )
            )
        )
    text = "\n".join(lines)
    _size_guard(text)
    return text


def parse(text: str) -> list[dict[str, Any]]:
    """Parse the CSV format back into value rows.

    Raises:
        ValueError: On a missing/foreign header, malformed numeric fields,
            or when the payload exceeds the 2 MiB cap.
    """
    _size_guard(text)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != CSV_HEADER:
        raise ValueError("CSV header does not match the abstractor values format")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines[1:], start=2):
        fields = line.split(CSV_SEPARATOR)
        if len(fields) != len(CSV_HEADER_FIELDS):
            raise ValueError(
                f"line {number} has {len(fields)} fields, expected {len(CSV_HEADER_FIELDS)}"
            )
        logical_name, entity_id, device_type, value_text, unit, updated_at = fields
        if value_text == "":
            value: Any = None
        else:
            try:
                value = float(value_text)
            except ValueError:
                raise ValueError(
                    f"line {number} has a non-numeric value field"
                ) from None
        rows.append(
            {
                "logical_name": logical_name,
                "entity_id": entity_id,
                "device_type": device_type,
                "value": value,
                "unit": unit or None,
                "updated_at": updated_at or None,
            }
        )
    return rows
