"""Unit tests for the HA-free naming/identity resolver (REQ-NAME-002..004)."""
from __future__ import annotations

from custom_components.abstractor.naming import (
    effective_logical_name,
    render_device_template,
    resolve_device_name,
    resolve_entity_name,
    resolve_object_id,
    slugify,
)
from custom_components.abstractor.specs import SPEC_REGISTRY


class _StubTemplate:
    def __init__(self, device=None, entity=None, object_id=None):
        self._device = device
        self._entity = entity or {}
        self._object = object_id

    def device_name(self, device_type):
        return self._device

    def entity_name(self, type_key):
        return self._entity.get(type_key)

    def object_id(self, type_key):
        return self._object


def test_slugify_normalises_free_text() -> None:
    assert slugify("Kitchen Fridge Energy") == "kitchen_fridge_energy"
    assert slugify("  Über-Sensor!! ") == "ber_sensor"
    assert slugify("a---b___c") == "a_b_c"


def test_render_device_template_matches_legacy() -> None:
    assert render_device_template("Abstract {device_type}", "power") == "Abstract Power"
    assert (
        render_device_template("Abstract {device_type}", "door_contact")
        == "Abstract Door_contact"
    )


def test_effective_logical_name_own_wins() -> None:
    data = {"logical_name": "Fridge", "device_group_id": "g1"}
    siblings = [{"device_group_id": "g1", "logical_name": "Other"}]
    assert effective_logical_name(data, siblings) == "Fridge"


def test_effective_logical_name_inherits_from_group() -> None:
    data = {"device_group_id": "g1"}
    siblings = [
        {"device_group_id": "g2", "logical_name": "Nope"},
        {"device_group_id": "g1", "logical_name": "Shared"},
    ]
    assert effective_logical_name(data, siblings) == "Shared"


def test_effective_logical_name_none_without_group() -> None:
    assert effective_logical_name({}, []) is None
    assert effective_logical_name({"device_group_id": "g1"}, []) is None


def test_resolve_device_name_precedence() -> None:
    spec = SPEC_REGISTRY.get("power")
    # logical_name beats everything
    assert (
        resolve_device_name(
            {"device_name": "X {device_type}"}, "power", "Fridge"
        )
        == "Fridge"
    )
    # template beats the root option
    assert (
        resolve_device_name(
            {"device_name": "X {device_type}"},
            "power",
            None,
            _StubTemplate(device="T power"),
        )
        == "T power"
    )
    # root option beats default
    assert (
        resolve_device_name({"device_name": "Fridge {device_type}"}, "power", None)
        == "Fridge Power"
    )
    # default fallback
    assert resolve_device_name({}, "power", None) == "Abstract Power"
    assert spec is not None


def test_resolve_entity_name_override_and_template() -> None:
    spec = SPEC_REGISTRY.get("power")
    assert resolve_entity_name({"entity_name": "Power now"}, spec) == "Power now"
    assert (
        resolve_entity_name({}, spec, _StubTemplate(entity={"power": "Leistung"}))
        == "Leistung"
    )
    assert resolve_entity_name({}, spec) is None


def test_resolve_object_id_slugifies_and_supports_template() -> None:
    spec = SPEC_REGISTRY.get("energy")
    assert resolve_object_id({"object_id": "Kitchen Fridge"}, spec) == "kitchen_fridge"
    assert resolve_object_id({}, spec, _StubTemplate(object_id="from_tpl")) == "from_tpl"
    assert resolve_object_id({}, spec) is None
    assert resolve_object_id({"object_id": "  "}, spec) is None
