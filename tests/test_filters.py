"""Test Abstractor filter behavior."""

from custom_components.abstractor.filters import AbstractorFilterPipeline


def test_spike_filter_keeps_last_value() -> None:
    """A configured monotonic filter rejects counter drops."""
    pipeline = AbstractorFilterPipeline({"spike_filter": True})

    assert pipeline.process("10") == 10.0
    assert pipeline.process("0") == 10.0


def test_filter_rejects_non_finite_values() -> None:
    """NaN and infinity must not become entity states."""
    pipeline = AbstractorFilterPipeline({})

    assert pipeline.process("nan") is None
    assert pipeline.process("inf") is None


def test_unavailable_fallback_zero() -> None:
    """Unavailable values can be explicitly converted to zero."""
    pipeline = AbstractorFilterPipeline({"fallback_zero": True})

    assert pipeline.process("unavailable") == 0.0


def test_power_sources_are_aggregated_and_fail_soft() -> None:
    """Power aggregation ignores unavailable sources and sums valid ones."""
    pipeline = AbstractorFilterPipeline({"device_type": "power"})

    assert pipeline.process_sources(["2", "unavailable", "3"]) == 5.0


def test_energy_sources_fail_closed() -> None:
    """An unavailable energy source must not feed a utility meter."""
    pipeline = AbstractorFilterPipeline({"device_type": "energy"})

    assert pipeline.process_sources(["2", "unavailable"]) is None


def test_inverted_source_is_aggregated() -> None:
    """Configured inversion applies before aggregation."""
    pipeline = AbstractorFilterPipeline({"device_type": "power", "invert": True})

    assert pipeline.process_sources(["2", "3"]) == -5.0


def test_filter_exposes_diagnostic_event() -> None:
    """Rejected spikes are available to the coordinator diagnostic hook."""
    pipeline = AbstractorFilterPipeline({"device_type": "energy", "spike_filter": True})

    pipeline.process("10")
    assert pipeline.process("0") == 10.0
    assert pipeline.last_event == "spike rejected"


def test_net_subtract_computes_charge_minus_discharge() -> None:
    """REQ-CORE-005: net flow subtracts a second source from the aggregate."""
    pipeline = AbstractorFilterPipeline({"device_type": "power"})

    result = pipeline.process_sources(["10"], net_subtract_raw="3")

    assert result == 7.0


def test_net_subtract_ignores_unavailable_subtrahend() -> None:
    """An unavailable subtract source must not corrupt the primary value."""
    pipeline = AbstractorFilterPipeline({"device_type": "power"})

    result = pipeline.process_sources(["10"], net_subtract_raw="unavailable")

    assert result == 10.0


def test_fallback_source_used_when_primary_unavailable_and_condition_met() -> None:
    """REQ-COMP-004: conditional fallback to an alternate hardware source."""
    pipeline = AbstractorFilterPipeline({"device_type": "energy"})

    result = pipeline.process_sources(
        ["unavailable"], fallback_raw="99", fallback_condition_met=True
    )

    assert result == 99.0
    assert pipeline.last_event == "fallback source used"


def test_fallback_source_ignored_when_condition_not_met() -> None:
    """The fallback must stay inactive until its condition is satisfied."""
    pipeline = AbstractorFilterPipeline({"device_type": "energy"})

    result = pipeline.process_sources(
        ["unavailable"], fallback_raw="99", fallback_condition_met=False
    )

    assert result is None
