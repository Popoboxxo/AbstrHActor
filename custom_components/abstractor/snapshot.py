"""Versioned export/import snapshot handling."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

SNAPSHOT_FORMAT = "abstractor.snapshot"
SNAPSHOT_VERSION = 1


def build_snapshot(entries: Mapping[str, Any], values: Mapping[str, Any]) -> dict[str, Any]:
    """Build a JSON-safe snapshot without copying HA registry identity fields."""
    return {
        "format": SNAPSHOT_FORMAT,
        "version": SNAPSHOT_VERSION,
        "entries": [
            {
                "entry_id": entry_id,
                "data": dict(entry.data),
                "options": dict(entry.options),
                "title": entry.title,
                "unique_id": entry.unique_id,
                "version": entry.version,
            }
            for entry_id, entry in entries.items()
        ],
        "values": dict(values),
    }


def validate_snapshot(payload: Any) -> dict[str, Any]:
    """Validate an import payload and return it unchanged.

    Validation is intentionally limited to the portable configuration shape.
    HA config-entry IDs and unique IDs are informational during import because
    recreating them would not preserve entity-registry or recorder history.
    """
    if not isinstance(payload, dict):
        raise vol.Invalid("snapshot must be an object")
    if payload.get("format") != SNAPSHOT_FORMAT:
        raise vol.Invalid("unsupported snapshot format")
    if payload.get("version") != SNAPSHOT_VERSION:
        raise vol.Invalid("unsupported snapshot version")
    if not isinstance(payload.get("entries"), list):
        raise vol.Invalid("entries must be a list")
    if not isinstance(payload.get("values"), dict):
        raise vol.Invalid("values must be an object")
    for entry in payload["entries"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("data"), dict):
            raise vol.Invalid("each entry must contain a data object")
        if not isinstance(entry.get("options", {}), dict):
            raise vol.Invalid("entry options must be an object")
    return payload
