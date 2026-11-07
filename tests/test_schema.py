"""Tests for the shared schema builders (WS-1: one field table, two builders).

The config flow renders what ``build_subentry_form_schema``/``build_options_form_schema``
produce; the websocket validates payloads with ``build_subentry_validator``/
``build_options_validator``. Both consume the same ``_*_SPEC`` field tables, so
these tests pin the CONTRACT of that table (field visibility, required-ness,
defaults, clearing, bounds) rather than the form rendering itself.
"""

import pytest
import voluptuous as vol

from custom_components.abstractor import schema as shared
from custom_components.abstractor.const import (
    CONF_AGGREGATION,
    CONF_DEVICE_TYPE,
    CONF_LEGACY_UNIQUE_ID,
    CONF_SPIKE_FILTER,
)
from custom_components.abstractor.specs import SPEC_REGISTRY


def _field_names(form_schema) -> set[str]:
    """Return the persisted/visible key names of a built form schema."""
    names: set[str] = set()
    for key in form_schema.schema:
        names.add(getattr(key, "schema", key))
    return names


def test_numeric_fields_follow_the_spec_registry() -> None:
    """Numeric-only pipeline fields appear exactly for numeric specs."""
    for spec in SPEC_REGISTRY.all():
        fields = _field_names(shared.build_subentry_form_schema(spec.type_key))
        assert (CONF_AGGREGATION in fields) is spec.numeric
        assert (CONF_SPIKE_FILTER in fields) is spec.numeric


def test_reconfigure_requires_device_type() -> None:
    """The reconfigure form pins the type as a required select."""
    required = [
        key.schema
        for key in shared.build_subentry_form_schema("power", reconfigure=True).schema
        if isinstance(key, vol.Required)
    ]
    assert CONF_DEVICE_TYPE in required


def test_pinned_legacy_unique_id_stays_hidden_in_form() -> None:
    """Create offers the id (explicit typed-in identity at setup); reconfigure
    hides it once pinned — clearing it would orphan the entity + history."""
    create_fields = _field_names(shared.build_subentry_form_schema("power"))
    reconfigure_pinned = _field_names(
        shared.build_subentry_form_schema("power", reconfigure=True, legacy_unique_id_pinned=True)
    )
    assert CONF_LEGACY_UNIQUE_ID in create_fields
    assert CONF_LEGACY_UNIQUE_ID not in reconfigure_pinned


def test_subentry_validator_rejects_bad_payloads() -> None:
    """The strict table (UF-03) rejects bad values, unknown keys, bad ids."""
    validator = shared.build_subentry_validator("power")
    bad_payloads = [
        {"aggregation": "banana"},
        {"invert": "yes"},
        {"source_entity_ids": ["bogus-without-domain"]},
        {"bogus_key": 1},
        {"device_type": "not_a_type"},
    ]
    for payload in bad_payloads:
        with pytest.raises(vol.error.Error):
            validator(payload)


def test_subentry_validator_accepts_panel_clearing_shape() -> None:
    """Panel payloads set optional entity fields to null to clear them."""
    validator = shared.build_subentry_validator("power")
    result = validator(
        {
            "device_type": "power",
            "source_entity_id": "sensor.a",
            "net_subtract_entity_id": None,
            "fallback_source_entity_id": None,
            "invert": True,
            "aggregation": "max",
        }
    )
    assert result["net_subtract_entity_id"] is None
    assert result["invert"] is True
    assert result["aggregation"] == "max"


def test_update_validator_pins_legacy_unique_id() -> None:
    """An update payload can neither change nor clear the pinned identity."""
    validator = shared.build_subentry_validator("power", allow_legacy_unique_id=False)
    with pytest.raises(vol.error.Error):
        validator({"legacy_unique_id": "anything"})


def test_options_validator_bounds_and_unknown_keys() -> None:
    """Stored-shape options keep their bounds; unknown keys are rejected."""
    options_validator = shared.build_options_validator()
    assert options_validator({"poll_interval": "45"}) == {"poll_interval": 45}
    for bad in [{"poll_interval": 0}, {"poll_interval": 999999}, {"bogus": "x"}]:
        with pytest.raises(vol.error.Error):
            options_validator(bad)
