"""The region registry, the simulated terrain and the scripted storm.

The simulated region exists to exercise the Warning and Critical paths the live
region rarely reaches, so what these tests actually protect is: it stays
reproducible, it stays clearly labelled as generated, and it still climbs
through every tier.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from rainshield.config import LEAD_TIMES
from rainshield.grid import infra_proximity, static_layers, ward_assignment, wards_for
from rainshield.hazard import WhatIf, compute_hazard
from rainshield.ingest.simulated import (
    PEAK_ACCUM_MM,
    SimulatedStormProvider,
    period_minutes,
    phase_at,
    phase_label,
    projected_phase,
)
from rainshield.models.predictor import predict_susceptibility
from rainshield.regions import (
    PRIMARY_REGION_ID,
    SIMULATED_REGION_ID,
    get_region,
    region_ids,
    simulated_static_layers,
)
from rainshield.risk import composite_risk, worst_tier

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
PERIOD = period_minutes()


def at_phase(phase: float) -> datetime:
    """A moment whose cycle phase is (close to) the one asked for.

    Tests are written against phases rather than wall-clock minutes so they keep
    meaning the same thing when RAINSHIELD_SIM_PERIOD changes.
    """
    current = phase_at(EPOCH)
    delta = (phase - current) % 1.0
    return EPOCH + timedelta(minutes=delta * PERIOD)


# -- registry --------------------------------------------------------------


def test_registry_lists_the_live_region_first():
    ids = region_ids()
    assert ids[0] == PRIMARY_REGION_ID
    assert SIMULATED_REGION_ID in ids
    assert not get_region(PRIMARY_REGION_ID).simulated
    assert get_region(SIMULATED_REGION_ID).simulated


def test_unknown_region_is_rejected():
    with pytest.raises(ValueError, match="unknown region"):
        get_region("atlantis")


def test_region_defaults_to_the_primary():
    assert get_region(None).id == PRIMARY_REGION_ID


def test_both_regions_share_the_model_input_shape():
    """The trained network takes a fixed (10, 45, 39); a region that broke that
    would fail at inference rather than here."""
    shapes = {get_region(rid).geometry.shape for rid in region_ids()}
    assert shapes == {(45, 39)}


# -- generated terrain -----------------------------------------------------


def test_simulated_terrain_is_deterministic():
    first = simulated_static_layers()
    second = simulated_static_layers.__wrapped__()  # bypass the cache
    for key, values in first.items():
        assert np.array_equal(values, second[key]), key


def test_simulated_terrain_is_physically_sane():
    layers = static_layers(SIMULATED_REGION_ID)
    assert set(layers) == {"elevation", "slope", "infrastructure", "population"}
    for key, values in layers.items():
        assert values.shape == (45, 39), key
        assert np.isfinite(values).all(), key

    # A coastal delta: mostly low ground rising to a hill fringe inland.
    assert -3.0 < layers["elevation"].min() < 2.0
    assert 100.0 < layers["elevation"].max() < 400.0
    assert (layers["slope"] >= 0).all()
    assert (layers["population"] >= 0).all()
    assert layers["population"].max() > 20_000


def test_coast_is_lower_than_the_inland_fringe():
    """Row 0 is north and the sea is on the eastern edge, so the eastern
    columns must be the low ground — this is what makes the region flood."""
    elevation = static_layers(SIMULATED_REGION_ID)["elevation"]
    assert elevation[:, -13:].mean() < elevation[:, :13].mean()


def test_each_region_has_its_own_wards_and_assignment():
    primary = wards_for(PRIMARY_REGION_ID)
    simulated = wards_for(SIMULATED_REGION_ID)
    assert {w.id for w in primary}.isdisjoint({w.id for w in simulated})

    for region_id, wards in ((PRIMARY_REGION_ID, primary), (SIMULATED_REGION_ID, simulated)):
        assignment = ward_assignment(region_id)
        assert assignment.shape == (45, 39)
        assert assignment.min() >= 0
        assert assignment.max() < len(wards)
        # Every ward centroid sits inside the grid, so none should be empty.
        assert len(set(assignment.ravel().tolist())) == len(wards)


def test_static_layers_are_cached_per_region_not_shared():
    primary = static_layers(PRIMARY_REGION_ID)["elevation"]
    simulated = static_layers(SIMULATED_REGION_ID)["elevation"]
    assert not np.array_equal(primary, simulated)
    assert not np.array_equal(
        infra_proximity(PRIMARY_REGION_ID), infra_proximity(SIMULATED_REGION_ID)
    )


# -- the scripted storm ----------------------------------------------------


def test_storm_is_a_pure_function_of_time():
    provider = SimulatedStormProvider()
    first = provider.fetch(EPOCH)
    second = provider.fetch(EPOCH)
    assert np.array_equal(first.rain_rate[0], second.rain_rate[0])


def test_storm_repeats_on_its_cycle():
    provider = SimulatedStormProvider()
    first = provider.fetch(EPOCH)
    later = provider.fetch(EPOCH + timedelta(minutes=PERIOD))
    assert np.allclose(first.rain_rate[0], later.rain_rate[0], atol=1e-4)


def test_storm_observation_is_labelled_generated_but_not_degraded():
    """`simulated` and `degraded` mean different things: nothing failed here."""
    observation = SimulatedStormProvider().fetch(EPOCH)
    observation.validate()
    assert observation.simulated is True
    assert observation.degraded is False
    assert observation.region_id == SIMULATED_REGION_ID
    assert any("SIMULATED" in note for note in observation.notes)


def test_storm_covers_every_lead_time():
    observation = SimulatedStormProvider().fetch(EPOCH)
    for lead in LEAD_TIMES:
        assert observation.rain_rate[lead].shape == (45, 39)
        assert observation.rain_3h[lead].shape == (45, 39)
        assert (observation.rain_rate[lead] >= 0).all()


def test_storm_peaks_within_the_documented_ceiling():
    """The peak accumulation has to clear the 100 mm/3 hr risk trigger for the
    region to reach Critical at all, without running away past its ceiling."""
    provider = SimulatedStormProvider()
    peak = max(
        float(provider.fetch(at_phase(p / 60)).rain_3h[0].max()) for p in range(60)
    )
    assert 100.0 < peak <= PEAK_ACCUM_MM * 1.05


def test_storm_reaches_every_tier_across_one_cycle():
    provider = SimulatedStormProvider()
    tiers = set()
    for step in range(40):
        observation = provider.fetch(at_phase(step / 40))
        susceptibility = predict_susceptibility(observation, 0, SIMULATED_REGION_ID)
        hazard = compute_hazard(
            susceptibility,
            observation.rain_rate[0],
            observation.rain_3h[0],
            observation.soil_moisture,
            0,
            WhatIf(),
            SIMULATED_REGION_ID,
        )
        risk, _ = composite_risk(hazard, SIMULATED_REGION_ID)
        tiers.add(worst_tier(risk))
    assert {"NORMAL", "WATCH", "WARNING", "CRITICAL"} <= tiers


def test_soil_wetness_lags_the_rainfall():
    """Ground stays saturated behind the storm, so the hazard decays more slowly
    than the rain does — the whole point of tracking antecedent load."""
    provider = SimulatedStormProvider()
    peak = provider.fetch(at_phase(0.46))    # the intensity peak
    after = provider.fetch(at_phase(0.80))   # storm has moved inland
    assert after.rain_rate[0].max() < peak.rain_rate[0].max()
    assert after.soil_moisture.max() >= peak.soil_moisture.max()


def test_phase_labels_span_the_cycle():
    labels = {phase_label(step / 40) for step in range(40)}
    assert len(labels) >= 4


# -- the forecast horizon --------------------------------------------------


def test_lead_projection_clamps_instead_of_wrapping():
    """Wrapping made +3 hr and +6 hr replay "now" whenever those leads were
    whole multiples of the cycle. A forecast projects the current system
    forward; it does not loop."""
    start = at_phase(0.30)
    phases = [projected_phase(start, lead) for lead in LEAD_TIMES]
    assert phases == sorted(phases)          # monotonic, never resets
    assert phases[-1] == 1.0                 # long leads say "storm has passed"
    assert all(p <= 1.0 for p in phases)


def test_long_lead_forecast_is_drier_than_the_peak():
    provider = SimulatedStormProvider()
    observation = provider.fetch(at_phase(0.40))  # storm building toward peak
    assert observation.rain_3h[360].max() < observation.rain_3h[0].max()


def test_forecast_shows_the_storm_arriving_when_it_is_offshore():
    provider = SimulatedStormProvider()
    observation = provider.fetch(at_phase(0.05))  # still offshore
    lead = int(0.35 * PERIOD)
    nearest = min(LEAD_TIMES, key=lambda candidate: abs(candidate - lead))
    assert observation.rain_3h[nearest].max() > observation.rain_3h[0].max()
