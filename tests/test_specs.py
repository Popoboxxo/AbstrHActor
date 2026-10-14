"""Tests for specs.py."""
from custom_components.abstractor.specs import SPEC_REGISTRY, FailContract


def test_shipping_types_enabled() -> None:
    enabled = {s.type_key for s in SPEC_REGISTRY.enabled()}
    assert {"power", "energy", "water"} <= enabled


def test_riemann_disabled_by_default() -> None:
    spec = SPEC_REGISTRY.get("riemann_energy")
    assert spec.enabled is False


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
