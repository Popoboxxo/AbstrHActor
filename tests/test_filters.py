"""Test Abstractor filter behavior."""

import pytest

from custom_components.abstractor.const import (
    AGGREGATION_FIRST_AVAILABLE,
    AGGREGATION_MAX,
    AGGREGATION_MIN,
    CONF_AGGREGATION,
)
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


def test_pipeline_seeds_last_valid_state_from_constructor() -> None:
    """A pipeline built with a known prior value rejects an immediate spike
    on its very FIRST process() call — proving the seed takes effect before
    any value has flowed through this pipeline instance."""
    pipeline = AbstractorFilterPipeline(
        {"spike_filter": True}, initial_last_valid_state=100.0
    )

    result = pipeline.process("40")

    assert result == 100.0
    assert pipeline.last_event == "spike rejected"


def test_pipeline_without_seed_defaults_to_none() -> None:
    """No initial_last_valid_state given -> starts at None as before
    (backward-compatible default, matches every existing call site)."""
    pipeline = AbstractorFilterPipeline({"spike_filter": True})

    assert pipeline._last_valid_state is None


def test_max_aggregation_takes_highest_parsed_value() -> None:
    """B2: max picks the active channel across the successfully parsed sources."""
    pipeline = AbstractorFilterPipeline(
        {"device_type": "power", CONF_AGGREGATION: AGGREGATION_MAX}
    )

    assert pipeline.process_sources(["2", "unavailable", "5"]) == 5.0


def test_min_aggregation_takes_lowest_parsed_value() -> None:
    """B2: min picks the smallest of the successfully parsed sources."""
    pipeline = AbstractorFilterPipeline(
        {"device_type": "power", CONF_AGGREGATION: AGGREGATION_MIN}
    )

    assert pipeline.process_sources(["2", "unavailable", "5"]) == 2.0


def test_first_available_uses_first_parsed_source_in_order() -> None:
    """B2: first_available keeps the first source (in configured source order)
    that delivered a parseable value."""
    pipeline = AbstractorFilterPipeline(
        {"device_type": "power", CONF_AGGREGATION: AGGREGATION_FIRST_AVAILABLE}
    )

    assert pipeline.process_sources(["unavailable", "3", "5"]) == 3.0


def test_max_aggregation_tolerates_partial_failure_for_energy() -> None:
    """B2: unlike sum, max/min/first_available aggregate the parsed remainder —
    one failed energy source must not fail the whole aggregate closed."""
    pipeline = AbstractorFilterPipeline(
        {"device_type": "energy", CONF_AGGREGATION: AGGREGATION_MAX}
    )

    assert pipeline.process_sources(["2", "unavailable"]) == 2.0


def test_invert_applies_before_max_aggregation() -> None:
    """B2: inversion runs per source before the mode picks its value."""
    pipeline = AbstractorFilterPipeline(
        {"device_type": "power", "invert": True, CONF_AGGREGATION: AGGREGATION_MAX}
    )

    assert pipeline.process_sources(["2", "5"]) == -2.0


def test_net_subtract_applies_after_max_aggregation() -> None:
    """B2: net-subtract (REQ-CORE-005) still runs after a non-sum aggregate."""
    pipeline = AbstractorFilterPipeline(
        {"device_type": "power", CONF_AGGREGATION: AGGREGATION_MAX}
    )

    result = pipeline.process_sources(["10", "4"], net_subtract_raw="3")

    assert result == 7.0


@pytest.mark.parametrize(
    ("mode", "device_type", "expected"),
    [
        (AGGREGATION_MAX, "power", 0.0),
        (AGGREGATION_MIN, "power", 0.0),
        (AGGREGATION_FIRST_AVAILABLE, "power", 0.0),
        (AGGREGATION_MAX, "energy", None),
        (AGGREGATION_MIN, "water", None),
        (AGGREGATION_FIRST_AVAILABLE, "energy", None),
    ],
)
def test_aggregation_all_sources_failed_keeps_device_type_contract(
    mode: str, device_type: str, expected: float | None
) -> None:
    """B2: when NO source parses, each mode falls back to the unchanged
    device-type contract: power fails soft to 0.0, energy/water fail closed
    to None (which also leaves the REQ-COMP-004 fallback a chance to fire)."""
    pipeline = AbstractorFilterPipeline(
        {"device_type": device_type, CONF_AGGREGATION: mode}
    )

    assert pipeline.process_sources(["unavailable", "unknown"]) == expected


def test_aggregation_unknown_mode_falls_back_to_sum() -> None:
    """A hand-edited or invalid mode never crashes the pipeline; it sums."""
    pipeline = AbstractorFilterPipeline(
        {"device_type": "power", CONF_AGGREGATION: "median"}
    )

    assert pipeline.process_sources(["2", "3"]) == 5.0


def test_fallback_on_zero_uses_fallback_when_primary_is_zero() -> None:
    """M1/ACE 1500: with fallback_on_zero the fallback source fires when the
    aggregate is exactly 0 (power fail-soft would otherwise mask it forever),
    replicating the template idiom 'primary == 0 -> fallback'."""
    pipeline = AbstractorFilterPipeline(
        {"device_type": "power", "fallback_on_zero": True}
    )

    result = pipeline.process_sources(
        ["0"], fallback_raw="125", fallback_condition_met=True
    )

    assert result == 125.0
    assert pipeline.last_event == "fallback source used"


def test_fallback_on_zero_fires_when_primary_unavailable() -> None:
    """A dead primary becomes fail-soft 0 for power, which the zero trigger
    treats exactly like a real 0 — the YAML template does the same
    (states(...)|float(0) then the fallback branch)."""
    pipeline = AbstractorFilterPipeline(
        {"device_type": "power", "fallback_on_zero": True}
    )

    result = pipeline.process_sources(
        ["unavailable"], fallback_raw="125", fallback_condition_met=True
    )

    assert result == 125.0


def test_fallback_not_fired_on_zero_without_flag() -> None:
    """Without fallback_on_zero the historical contract holds: power's
    fail-soft 0 stands, the fallback only fires for unavailable (None)."""
    pipeline = AbstractorFilterPipeline({"device_type": "power"})

    result = pipeline.process_sources(
        ["0"], fallback_raw="125", fallback_condition_met=True
    )

    assert result == 0.0


def test_fallback_on_zero_still_requires_condition_and_value() -> None:
    """The zero trigger never bypasses the REQ-COMP-004 condition, and a
    fallback source that itself has no value leaves the 0 standing."""
    pipeline = AbstractorFilterPipeline(
        {"device_type": "power", "fallback_on_zero": True}
    )

    assert (
        pipeline.process_sources(["0"], fallback_raw="125", fallback_condition_met=False)
        == 0.0
    )
    assert (
        pipeline.process_sources(["0"], fallback_raw="unavailable", fallback_condition_met=True)
        == 0.0
    )
