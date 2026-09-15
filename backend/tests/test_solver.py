"""Tests for the Stage B diffusive-wave solver.

The central claim is conservation of mass, so most of this file is different
ways of trying to break it.
"""

from __future__ import annotations

import numpy as np
import pytest

from rainshield.config import LEAD_TIMES
from rainshield.hydro.solver import (
    DEPRESSION_STORAGE_MAX_M,
    DEPRESSION_STORAGE_MIN_M,
    FLOOD_DEPTH_SCALE_M,
    MANNING_PAVED,
    MANNING_VEGETATED,
    inundated_fraction,
    parameter_field,
    solve,
)
from rainshield.hydro.terrain import drainage_terrain
from rainshield.regions import get_region

REGIONS = ("mumbai", "coromandel")
#: Anything above this is a bug, not floating-point noise.
CLOSURE_TOLERANCE = 1e-9


def _rain(region_id: str, mm_hr: float) -> dict[int, np.ndarray]:
    shape = get_region(region_id).geometry.shape
    return {lead: np.full(shape, mm_hr, dtype=np.float32) for lead in LEAD_TIMES}


def _susceptibility(region_id: str, value: float = 0.5) -> np.ndarray:
    return np.full(get_region(region_id).geometry.shape, value, dtype=np.float32)


def _soil(region_id: str, value: float = 0.3) -> np.ndarray:
    return np.full(get_region(region_id).geometry.shape, value, dtype=np.float32)


# --------------------------------------------------------------------------
# Mass conservation — the whole point
# --------------------------------------------------------------------------


@pytest.mark.parametrize("region_id", REGIONS)
@pytest.mark.parametrize("intensity", [5.0, 40.0, 120.0])
def test_mass_closes_across_regions_and_intensities(region_id, intensity):
    result = solve(
        _susceptibility(region_id),
        _rain(region_id, intensity),
        _soil(region_id),
        region_id=region_id,
        tide_override_m=2.0,
    )
    assert result.mass.closure_error < CLOSURE_TOLERANCE


@pytest.mark.parametrize("tide", [0.0, 2.0, 5.0])
def test_mass_closes_at_every_tide(tide):
    result = solve(
        _susceptibility("mumbai"),
        _rain("mumbai", 60.0),
        _soil("mumbai"),
        region_id="mumbai",
        tide_override_m=tide,
    )
    assert result.mass.closure_error < CLOSURE_TOLERANCE


def test_every_drop_is_accounted_for():
    """Rain in equals everything out plus what is still standing."""
    result = solve(
        _susceptibility("mumbai"),
        _rain("mumbai", 80.0),
        _soil("mumbai"),
        region_id="mumbai",
        tide_override_m=2.0,
    )
    mass = result.mass
    accounted = (
        mass.infiltration
        + mass.drained
        + mass.pumped
        + mass.to_sea
        + mass.off_domain
        + mass.final_storage
    )
    assert accounted == pytest.approx(mass.rainfall, rel=1e-9)


def test_storage_matches_the_depth_field():
    """The tallied storage must equal the water actually on the grid."""
    result = solve(
        _susceptibility("mumbai"),
        _rain("mumbai", 50.0),
        _soil("mumbai"),
        region_id="mumbai",
        tide_override_m=2.0,
    )
    terrain = drainage_terrain("mumbai")
    on_grid = float((result.depth[max(LEAD_TIMES)] * terrain.cell_area_m2).sum())
    assert on_grid == pytest.approx(result.mass.final_storage, rel=1e-5)


def test_no_rain_creates_no_water():
    result = solve(
        _susceptibility("mumbai"),
        _rain("mumbai", 0.0),
        _soil("mumbai"),
        region_id="mumbai",
    )
    assert result.mass.rainfall == 0.0
    for lead in LEAD_TIMES:
        assert result.depth[lead].max() == 0.0


# --------------------------------------------------------------------------
# Physical behaviour
# --------------------------------------------------------------------------


@pytest.mark.parametrize("region_id", REGIONS)
def test_depth_is_never_negative_and_never_on_the_sea(region_id):
    result = solve(
        _susceptibility(region_id),
        _rain(region_id, 90.0),
        _soil(region_id),
        region_id=region_id,
    )
    terrain = drainage_terrain(region_id)
    for lead in LEAD_TIMES:
        depth = result.depth[lead]
        assert depth.min() >= 0.0
        assert depth[terrain.sea].max() == 0.0


def test_water_accumulates_downhill():
    """The fault the heuristic has: rain on a slope must arrive below it."""
    result = solve(
        _susceptibility("mumbai"),
        _rain("mumbai", 60.0),
        _soil("mumbai"),
        region_id="mumbai",
        tide_override_m=2.0,
    )
    terrain = drainage_terrain("mumbai")
    depth = result.depth[max(LEAD_TIMES)]
    elevation = terrain.elevation
    low = terrain.land & (elevation < 5.0)
    high = terrain.land & (elevation > 50.0)

    assert depth[low].mean() > depth[high].mean()
    correlation = np.corrcoef(elevation[terrain.land], depth[terrain.land])[0, 1]
    assert correlation < 0, "deeper water must sit on lower ground"


def test_high_tide_keeps_water_on_the_land():
    """A shut gate has to show up as water that did not leave."""
    low = solve(
        _susceptibility("mumbai"), _rain("mumbai", 60.0), _soil("mumbai"),
        region_id="mumbai", tide_override_m=0.5,
    )
    high = solve(
        _susceptibility("mumbai"), _rain("mumbai", 60.0), _soil("mumbai"),
        region_id="mumbai", tide_override_m=5.0,
    )
    assert high.mass.to_sea < low.mass.to_sea
    assert high.mass.final_storage > low.mass.final_storage
    assert high.depth[max(LEAD_TIMES)].max() >= low.depth[max(LEAD_TIMES)].max()


def test_more_rain_means_more_water():
    depths = []
    for intensity in (10.0, 30.0, 60.0, 100.0):
        result = solve(
            _susceptibility("mumbai"), _rain("mumbai", intensity), _soil("mumbai"),
            region_id="mumbai", tide_override_m=2.0,
        )
        depths.append(result.mass.final_storage)
    assert depths == sorted(depths)


def test_depth_grows_with_lead_time_under_steady_rain():
    result = solve(
        _susceptibility("mumbai"), _rain("mumbai", 50.0), _soil("mumbai"),
        region_id="mumbai", tide_override_m=2.0,
    )
    means = [float(result.depth[lead].mean()) for lead in sorted(LEAD_TIMES)]
    assert means == sorted(means), "a single trajectory must not go backwards"


def test_pumping_removes_water():
    wet = _rain("mumbai", 120.0)
    on = solve(
        _susceptibility("mumbai"), wet, _soil("mumbai"),
        region_id="mumbai", tide_override_m=5.0, pump_availability=1.0,
    )
    off = solve(
        _susceptibility("mumbai"), wet, _soil("mumbai"),
        region_id="mumbai", tide_override_m=5.0, pump_availability=0.0,
    )
    assert on.mass.pumped > 0.0
    assert off.mass.pumped == 0.0
    assert on.mass.final_storage < off.mass.final_storage
    assert on.mass.closure_error < CLOSURE_TOLERANCE
    assert off.mass.closure_error < CLOSURE_TOLERANCE


def test_onset_is_computed_not_correlated():
    """Onset must be a time the solve passed through, not a formula."""
    result = solve(
        _susceptibility("mumbai"), _rain("mumbai", 100.0), _soil("mumbai"),
        region_id="mumbai", tide_override_m=4.0,
    )
    onset = result.onset_minutes
    flooded = np.isfinite(onset)
    assert flooded.any()
    assert onset[flooded].min() >= 0.0
    assert onset[flooded].max() <= max(LEAD_TIMES)
    # A cell that never got wet must have no onset time.
    assert np.all(np.isnan(onset[result.peak_depth < 0.10]))


def test_peak_depth_bounds_every_snapshot():
    result = solve(
        _susceptibility("mumbai"), _rain("mumbai", 70.0), _soil("mumbai"),
        region_id="mumbai", tide_override_m=2.0,
    )
    for lead in LEAD_TIMES:
        assert np.all(result.depth[lead] <= result.peak_depth + 1e-9)


# --------------------------------------------------------------------------
# The network's role
# --------------------------------------------------------------------------


def test_susceptibility_sets_storage_and_drainage_only():
    low = parameter_field(_susceptibility("mumbai", 0.0), _soil("mumbai"), "mumbai")
    high = parameter_field(_susceptibility("mumbai", 1.0), _soil("mumbai"), "mumbai")

    # More susceptible: more sub-grid storage, slower drainage.
    assert np.all(high.depression_storage > low.depression_storage)
    assert np.all(high.drain_rate < low.drain_rate)
    # Roughness is terrain, not the network's business.
    assert np.array_equal(high.manning, low.manning)
    assert np.array_equal(high.infiltration, low.infiltration)


def test_parameter_ranges_stay_within_their_bounds():
    for value in (0.0, 0.5, 1.0):
        params = parameter_field(
            _susceptibility("mumbai", value), _soil("mumbai"), "mumbai"
        )
        # float32 susceptibility, so the bounds are met to single precision.
        assert params.depression_storage.min() >= DEPRESSION_STORAGE_MIN_M - 1e-6
        assert params.depression_storage.max() <= DEPRESSION_STORAGE_MAX_M + 1e-6
        assert params.manning.min() >= min(MANNING_PAVED, MANNING_VEGETATED) - 1e-6
        assert params.manning.max() <= max(MANNING_PAVED, MANNING_VEGETATED) + 1e-6
        assert params.drain_rate.min() >= 0.0


def test_susceptibility_changes_depth_without_dictating_it():
    """The network must move the answer, but conservation must still hold."""
    flat = solve(
        _susceptibility("mumbai", 0.1), _rain("mumbai", 60.0), _soil("mumbai"),
        region_id="mumbai", tide_override_m=2.0,
    )
    pondy = solve(
        _susceptibility("mumbai", 0.9), _rain("mumbai", 60.0), _soil("mumbai"),
        region_id="mumbai", tide_override_m=2.0,
    )
    assert not np.allclose(flat.depth[360], pondy.depth[360])
    # Worse drainage keeps more water on the surface.
    assert pondy.mass.drained < flat.mass.drained
    assert pondy.mass.final_storage > flat.mass.final_storage
    for result in (flat, pondy):
        assert result.mass.closure_error < CLOSURE_TOLERANCE


# --------------------------------------------------------------------------
# Inundated fraction
# --------------------------------------------------------------------------


def test_water_inside_the_hollows_is_not_flooding():
    storage = np.full(1, 0.05)
    assert inundated_fraction(np.full(1, 0.0), storage)[0] == 0.0
    assert inundated_fraction(np.full(1, 0.05), storage)[0] == 0.0
    assert inundated_fraction(np.full(1, 0.04), storage)[0] == 0.0


def test_inundated_fraction_rises_with_depth_and_stays_bounded():
    storage = np.full(1, 0.02)
    values = [
        float(inundated_fraction(np.full(1, h), storage)[0])
        for h in (0.0, 0.05, 0.1, 0.3, 0.6, 2.0)
    ]
    assert values == sorted(values)
    assert values[-1] <= 1.0
    assert values[-1] > 0.99


def test_inundated_fraction_saturates_at_the_flood_scale():
    storage = np.zeros(1)
    one_scale = float(inundated_fraction(np.full(1, FLOOD_DEPTH_SCALE_M), storage)[0])
    assert one_scale == pytest.approx(1.0 - np.exp(-1.0), abs=1e-6)


def test_more_susceptible_ground_reads_as_less_flooded_at_equal_depth():
    """Somewhere that ponds in hollows is not sheeting over at 5 cm."""
    depth = np.full(1, 0.05)
    shallow = inundated_fraction(depth, np.full(1, DEPRESSION_STORAGE_MIN_M))[0]
    deep = inundated_fraction(depth, np.full(1, DEPRESSION_STORAGE_MAX_M))[0]
    assert shallow > deep
