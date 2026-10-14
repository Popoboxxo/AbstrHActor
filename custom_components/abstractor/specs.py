"""Declarative specification registry for Abstractor sensor types.

This module is HA-free so it can be exercised by fast unit tests (REQ-NFA-002).
It replaces the ``if/elif`` ladder previously found in ``sensor.py`` and the
``device_type == "power"`` failure-contract branches in ``filters.py``, which
now consult ``spec.fail_contract`` and keep the historical ``power`` rule only
as a fallback for unmapped legacy types.

Only the types that actually ship today are marked ``enabled=True``. The
declared but not-yet-enabled specs document the roadmap from
``docs/plan-logical-identity-and-ux.md`` section 3.1; enabling one of them is
a deliberate, reviewed change, never an accidental side effect.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FailContract(str, Enum):
    SOFT_ZERO = "soft_zero"
    FAIL_CLOSED = "fail_closed"
    PASS_THROUGH = "pass_through"


@dataclass(frozen=True, slots=True)
class AbstractSpec:
    """One logical (platform, measurement, failure) contract."""

    type_key: str
    platform: str
    device_class: str | None
    unit: str | None
    state_class: str | None
    numeric: bool
    fail_contract: FailContract
    monotonic_default: bool
    display_name: str
    command_service: str | None = None
    enabled: bool = True
    integration: str | None = None


class SpecRegistry:
    """Read-only registry of :class:`AbstractSpec` instances."""

    def __init__(self) -> None:
        self._specs: dict[str, AbstractSpec] = {}

    def register(self, spec: AbstractSpec) -> None:
        if spec.type_key in self._specs:
            raise ValueError(f"Duplicate spec type_key: {spec.type_key}")
        self._specs[spec.type_key] = spec

    def get(self, type_key: str) -> AbstractSpec:
        if type_key not in self._specs:
            raise KeyError(f"Unknown Abstractor spec: {type_key!r}")
        return self._specs[type_key]

    def try_get(self, type_key: str) -> AbstractSpec | None:
        return self._specs.get(type_key)

    def all(self) -> list[AbstractSpec]:
        return list(self._specs.values())

    def enabled(self) -> list[AbstractSpec]:
        return [s for s in self._specs.values() if s.enabled]

    def by_platform(self, platform: str) -> list[AbstractSpec]:
        return [s for s in self._specs.values() if s.platform == platform]

    def numeric_types(self) -> list[str]:
        return [s.type_key for s in self._specs.values() if s.numeric]

    def monotonic_types(self) -> list[str]:
        return [s.type_key for s in self._specs.values() if s.monotonic_default]


def _build_default_registry() -> SpecRegistry:
    reg = SpecRegistry()
    register = reg.register
    # Shipping today.
    register(AbstractSpec("power", "sensor", "power", "W", "measurement", True, FailContract.SOFT_ZERO, False, "Power"))
    register(AbstractSpec("energy", "sensor", "energy", "kWh", "total_increasing", True, FailContract.FAIL_CLOSED, True, "Energy"))
    register(AbstractSpec("water", "sensor", "energy", "L", "total_increasing", True, FailContract.FAIL_CLOSED, True, "Water"))
    # Roadmap (declared, not enabled; enabling is an explicit reviewed change).
    register(AbstractSpec("riemann_energy", "sensor", "energy", "kWh", "total_increasing", True, FailContract.FAIL_CLOSED, False, "Riemann energy", integration="riemann_left"))
    for key in ("door_contact", "motion", "smoke"):
        register(AbstractSpec(key, "binary_sensor", "door" if key == "door_contact" else None, None, None, False, FailContract.PASS_THROUGH, False, key.replace("_", " ").title(), enabled=True))
    register(AbstractSpec("switch_state", "switch", None, None, None, False, FailContract.PASS_THROUGH, False, "Switch", "turn_on"))
    register(AbstractSpec("light_state", "light", None, None, None, False, FailContract.PASS_THROUGH, False, "Light", "turn_on"))
    register(AbstractSpec("cover_position", "cover", None, "%", None, False, FailContract.PASS_THROUGH, False, "Cover position", "set_cover_position"))
    return reg


# Module-level singleton, safe to import anywhere.
SPEC_REGISTRY: SpecRegistry = _build_default_registry()
spec_for = SPEC_REGISTRY.get
ALL_SPECS = SPEC_REGISTRY.all()
ENABLED_SPECS = SPEC_REGISTRY.enabled()

