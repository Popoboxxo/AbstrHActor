"""Tests for the Riemann energy integration sensor."""

from custom_components.abstractor.sensor import _integrate_energy


def test_integrate_accumulates_energy() -> None:
    # 1000 W for 1 hour = 1 kWh
    assert _integrate_energy(0.0, 1000.0, 3600.0) == 1.0
    # 500 W for 30 minutes = 0.25 kWh
    assert _integrate_energy(0.0, 500.0, 1800.0) == 0.25
    # accumulates onto an existing total
    assert _integrate_energy(1.0, 1000.0, 3600.0) == 2.0


def test_integrate_ignores_missing_power_and_nonpositive_interval() -> None:
    assert _integrate_energy(5.0, None, 3600.0) == 5.0
    assert _integrate_energy(5.0, 1000.0, 0.0) == 5.0
    assert _integrate_energy(5.0, 1000.0, -1.0) == 5.0
