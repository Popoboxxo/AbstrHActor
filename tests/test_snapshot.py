"""Test snapshot format validation."""

import pytest
import voluptuous as vol

from custom_components.abstractor.snapshot import validate_snapshot


def test_snapshot_validation_accepts_versioned_payload() -> None:
    """Only the documented portable snapshot shape is accepted."""
    payload = {
        "format": "abstractor.snapshot",
        "version": 1,
        "entries": [{"data": {}, "options": {}}],
        "values": {},
    }

    assert validate_snapshot(payload) is payload


def test_snapshot_validation_rejects_legacy_shape() -> None:
    """Legacy ad-hoc exports cannot be mistaken for restorable snapshots."""
    with pytest.raises(vol.Invalid):
        validate_snapshot({"entries": {}, "values": {}})
