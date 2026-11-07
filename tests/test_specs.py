"""Tests for specs.py."""

from custom_components.abstractor.specs import SPEC_REGISTRY, FailContract


def test_shipping_types_enabled() -> None:
    enabled = {s.type_key for s in SPEC_REGISTRY.enabled()}
    assert {"power", "energy", "water"} <= enabled


def test_actuator_types_enabled() -> None:
    enabled = {s.type_key for s in SPEC_REGISTRY.enabled()}
    assert {"switch_state", "light_state", "cover_position"} <= enabled


def test_riemann_integration_spec_is_roadmap_only() -> None:
    """Decision D-1 (plan §6.1): declared but explicitly NOT enabled — it
    depends on the external ``riemann_left`` integration and needs a REQ-SENS-003
    re-review against HA Core's own Riemann support before shipping."""
    spec = SPEC_REGISTRY.get("riemann_energy")
    assert spec.enabled is False
    assert spec.integration == "riemann_left"
    assert "riemann_energy" not in {s.type_key for s in SPEC_REGISTRY.enabled()}


def test_unknown_spec_raises() -> None:
    import pytest

    with pytest.raises(KeyError):
        SPEC_REGISTRY.get("does_not_exist")


def test_fail_contracts() -> None:
    assert SPEC_REGISTRY.get("power").fail_contract is FailContract.SOFT_ZERO
    assert SPEC_REGISTRY.get("energy").fail_contract is FailContract.FAIL_CLOSED


def test_monotonic_defaults() -> None:
    assert SPEC_REGISTRY.get("energy").monotonic_default is True
    assert SPEC_REGISTRY.get("power").monotonic_default is False


def test_device_classes() -> None:
    assert SPEC_REGISTRY.get("water").device_class == "water"
    assert SPEC_REGISTRY.get("door_contact").device_class == "door"
    assert SPEC_REGISTRY.get("motion").device_class == "motion"
    assert SPEC_REGISTRY.get("smoke").device_class == "smoke"
