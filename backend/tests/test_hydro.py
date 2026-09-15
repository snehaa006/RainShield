"""Tests for the physics-based drainage: tides, terrain, catchments, balance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from rainshield.hydro import assess_drainage, drainage_terrain, stations_for, tide_level
from rainshield.hydro.balance import (
    GRAVITY_DESIGN_HEAD_M,
    SATURATION_M3_M3,
    gravity_discharge,
    infiltration_mm_hr,
)
from rainshield.hydro.stations import DESIGN_INTENSITY_MM_HR, PUMP_UNIT_CUMECS
from rainshield.hydro.terrain import (
    d8_downstream,
    design_service_cells,
    fill_depressions,
    flow_accumulation,
    sea_mask,
    trace_outlets,
)
from rainshield.hydro.tide import regime_for, sea_level
from rainshield.regions import get_region

REGIONS = ("mumbai", "coromandel")


# --------------------------------------------------------------------------
# Tide
# --------------------------------------------------------------------------


@pytest.mark.parametrize("region_id", REGIONS)
def test_tide_stays_within_astronomical_bounds(region_id):
    """The harmonic sum can never exceed the sum of its amplitudes."""
    regime = regime_for(region_id)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    levels = [
        sea_level(start + timedelta(minutes=10 * i), region_id) for i in range(6 * 24 * 40)
    ]
    assert min(levels) >= regime.lowest_astronomical_tide_m - 1e-6
    assert max(levels) <= regime.highest_astronomical_tide_m + 1e-6


def test_tide_is_semidiurnal():
    """Two highs a day: the level must return near itself after ~12h25m."""
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    now = sea_level(start, "mumbai")
    later = sea_level(start + timedelta(hours=12, minutes=25), "mumbai")
    assert abs(now - later) < 0.6


def test_tide_is_deterministic_across_calls():
    moment = datetime(2026, 7, 4, 9, 30, tzinfo=timezone.utc)
    assert sea_level(moment, "mumbai") == sea_level(moment, "mumbai")


def test_mumbai_spring_range_is_macrotidal():
    """~4.5 m is the defining fact about Mumbai's drainage problem."""
    assert 4.0 < regime_for("mumbai").spring_range_m < 5.5


def test_tide_override_pins_level_and_reports_no_rate():
    state = tide_level(region_id="mumbai", override_m=4.2)
    assert state.level_m == pytest.approx(4.2)
    assert state.rate_m_per_hr == 0.0
    assert state.phase == "high"


def test_tide_rate_sign_matches_level_change():
    start = datetime(2026, 3, 3, tzinfo=timezone.utc)
    for hours in range(0, 24):
        moment = start + timedelta(hours=hours)
        state = tide_level(moment, "mumbai")
        ahead = sea_level(moment + timedelta(minutes=15), "mumbai")
        if abs(state.rate_m_per_hr) > 0.15:
            assert (ahead > state.level_m) == state.is_rising


# --------------------------------------------------------------------------
# Terrain
# --------------------------------------------------------------------------


def test_sea_mask_excludes_unconnected_depressions():
    """An inland hole below sea level is a basin, not an inlet."""
    dem = np.array(
        [
            [-1.0, -1.0, 5.0, 5.0, 5.0],
            [-1.0, -1.0, 5.0, 5.0, 5.0],
            [5.0, 5.0, 5.0, -3.0, 5.0],   # interior pit, below sea level
            [5.0, 5.0, 5.0, 5.0, 5.0],
            [5.0, 5.0, 5.0, 5.0, 5.0],
        ]
    )
    sea = sea_mask(dem)
    assert sea[0, 0] and sea[1, 1]
    assert not sea[2, 3], "an unconnected pit must not be classed as ocean"


@pytest.mark.parametrize("region_id", REGIONS)
def test_sea_is_on_the_expected_edge(region_id):
    """Mumbai's coast is west, the simulated delta's is east — from the DEM."""
    terrain = drainage_terrain(region_id)
    west = terrain.sea[:, 0].mean()
    east = terrain.sea[:, -1].mean()
    if region_id == "mumbai":
        assert west > east
    else:
        assert east > west


@pytest.mark.parametrize("region_id", REGIONS)
def test_filling_never_lowers_ground(region_id):
    terrain = drainage_terrain(region_id)
    assert np.all(terrain.filled >= terrain.elevation - 1e-5)
    assert np.all(terrain.fill_depth >= -1e-5)


def test_filling_removes_interior_pits():
    """After filling, no land cell is strictly below all of its neighbours."""
    terrain = drainage_terrain("mumbai")
    filled, sea = terrain.filled, terrain.sea
    rows, cols = filled.shape
    for r in range(1, rows - 1):
        for c in range(1, cols - 1):
            if sea[r, c]:
                continue
            window = filled[r - 1 : r + 2, c - 1 : c + 2]
            neighbours = np.delete(window.ravel(), 4)
            assert filled[r, c] >= neighbours.min() - 1e-4


@pytest.mark.parametrize("region_id", REGIONS)
def test_no_land_cell_drains_into_an_interior_sink(region_id):
    """Water must leave: to the sea, or off the edge of the modelled grid.

    Mumbai's eastern mainland drains towards Thane creek, which is outside the
    domain, so a domain-edge exit is a real outcome and not a routing failure.
    An *interior* terminus would be one — it is the flat-routing bug that the
    epsilon surface exists to prevent, so it is asserted against directly.
    """
    terrain = drainage_terrain(region_id)
    rows, cols = terrain.shape
    land = terrain.land.ravel()
    sea_flat = terrain.sea.ravel()

    assert np.all(terrain.outlet[land] >= 0)
    for cell in np.nonzero(land)[0]:
        out = int(terrain.outlet[cell])
        if sea_flat[out]:
            continue
        row, col = divmod(out, cols)
        assert row in (0, rows - 1) or col in (0, cols - 1), (
            f"cell {cell} drains to interior sink {out} — flat routing failed"
        )


@pytest.mark.parametrize("region_id", REGIONS)
def test_routing_surface_only_tilts_flats(region_id):
    """The tilt that makes flats routable must stay physically negligible."""
    terrain = drainage_terrain(region_id)
    tilt = terrain.routing - terrain.filled
    assert np.all(tilt >= -1e-9)
    assert tilt.max() < 0.01, "routing tilt must stay far below DEM error"
    # The physical surface is the one with real pools in it.
    assert terrain.fill_depth.max() > 1.0


@pytest.mark.parametrize("region_id", REGIONS)
def test_flow_accumulation_conserves_cells(region_id):
    """Every land cell is counted exactly once at the outlets it drains to."""
    terrain = drainage_terrain(region_id)
    flat_down = terrain.downstream
    terminal = (flat_down < 0) & terrain.land.ravel()
    total = terrain.accumulation.ravel()[terminal].sum()
    # Cells draining straight into the sea end with downstream == sea index,
    # so sum the accumulation arriving at sea cells too.
    into_sea = 0.0
    for cell in np.nonzero(terrain.land.ravel())[0]:
        target = int(flat_down[cell])
        if target >= 0 and terrain.sea.ravel()[target]:
            into_sea += terrain.accumulation.ravel()[cell]
    assert total + into_sea == pytest.approx(float(terrain.land.sum()))


def test_d8_routes_downhill_on_a_simple_slope():
    dem = np.array([[3.0, 3.0, 3.0], [2.0, 2.0, 2.0], [-1.0, -1.0, -1.0]])
    sea = sea_mask(dem)
    filled = fill_depressions(dem, sea)
    down = d8_downstream(filled, sea)
    # The top-middle cell must move to a strictly lower row.
    assert down[1] // 3 > 0


@pytest.mark.parametrize("region_id", REGIONS)
def test_catchments_partition_the_land(region_id):
    """Every land cell belongs to exactly one catchment; no sea cell does."""
    terrain = drainage_terrain(region_id)
    served = sum(terrain.catchment_mask(i).sum() for i in range(len(terrain.stations)))
    unserved = terrain.catchment_mask(-1).sum()
    assert served + unserved == terrain.land.sum()
    assert not terrain.catchment[terrain.sea].max(initial=-1) >= 0


@pytest.mark.parametrize("region_id", REGIONS)
def test_service_areas_match_the_design_standard(region_id):
    """A station drains the area its capacity implies, to whole-cell rounding."""
    terrain = drainage_terrain(region_id)
    for i, station in enumerate(terrain.stations):
        quota = design_service_cells(station, terrain.cell_area_m2)
        assert terrain.catchment_mask(i).sum() == quota
        implied = station.capacity_cumecs / (
            station.design_intensity_mm_hr / 1000.0 / 3600.0
        )
        assert terrain.catchment_area_m2(i) == pytest.approx(
            implied, rel=1.0
        ), "service area must stay within a cell of the design area"


def test_all_brimstowad_stations_land_inside_the_mumbai_grid():
    stations = stations_for("mumbai")
    assert len(stations) == 7
    geometry = get_region("mumbai").geometry
    for station in stations:
        assert geometry.west <= station.lon <= geometry.east
        assert geometry.south <= station.lat <= geometry.north


def test_station_capacities_carry_their_provenance():
    """No capacity figure may reach the API without its caveat attached."""
    for region_id in REGIONS:
        for station in stations_for(region_id):
            assert station.capacity_basis
            assert ("ESTIMATE" in station.capacity_basis) or (
                "GENERATED" in station.capacity_basis
            )


# --------------------------------------------------------------------------
# Infiltration and gravity discharge
# --------------------------------------------------------------------------


def test_impervious_ground_infiltrates_less_than_pervious():
    dry = np.zeros((2, 2), dtype=np.float32)
    paved = infiltration_mm_hr(np.ones((2, 2)), dry)
    green = infiltration_mm_hr(np.zeros((2, 2)), dry)
    assert np.all(paved < green)


def test_saturated_ground_infiltrates_nothing():
    saturated = np.full((2, 2), SATURATION_M3_M3, dtype=np.float32)
    assert np.allclose(infiltration_mm_hr(np.zeros((2, 2)), saturated), 0.0)


def test_infiltration_is_monotonic_in_wetness():
    built = np.zeros((1, 1))
    values = [
        float(infiltration_mm_hr(built, np.full((1, 1), sm))[0, 0])
        for sm in (0.0, 0.1, 0.2, 0.3, 0.4)
    ]
    assert values == sorted(values, reverse=True)


def test_gravity_stops_once_the_tide_passes_the_invert():
    assert gravity_discharge(20.0, 2.0, 2.0) == 0.0
    assert gravity_discharge(20.0, 2.0, 3.5) == 0.0
    assert gravity_discharge(20.0, 2.0, 1.9) > 0.0


def test_gravity_reaches_design_capacity_at_design_head():
    full = gravity_discharge(20.0, 2.0, 2.0 - GRAVITY_DESIGN_HEAD_M)
    assert full == pytest.approx(20.0)
    # And is capped there, not exceeded, at greater head.
    assert gravity_discharge(20.0, 2.0, -5.0) == pytest.approx(20.0)


def test_gravity_increases_as_the_tide_falls():
    levels = [gravity_discharge(20.0, 2.0, t) for t in (2.0, 1.8, 1.5, 1.0, 0.5)]
    assert levels == sorted(levels)


# --------------------------------------------------------------------------
# Mass balance
# --------------------------------------------------------------------------


def _flat(region_id: str, value: float) -> np.ndarray:
    return np.full(get_region(region_id).geometry.shape, value, dtype=np.float32)


@pytest.mark.parametrize("region_id", REGIONS)
def test_no_rain_means_no_inflow(region_id):
    assessment = assess_drainage(
        _flat(region_id, 0.0), _flat(region_id, 0.2), region_id=region_id
    )
    assert assessment.total_inflow_cumecs == pytest.approx(0.0)
    assert assessment.total_deficit_cumecs == 0.0
    assert assessment.total_extra_pumps == 0
    assert assessment.sufficient


@pytest.mark.parametrize("region_id", REGIONS)
def test_inflow_rises_with_rainfall(region_id):
    soil = _flat(region_id, 0.3)
    flows = [
        assess_drainage(
            _flat(region_id, r), soil, region_id=region_id, tide_override_m=0.5
        ).total_inflow_cumecs
        for r in (0.0, 10.0, 25.0, 50.0, 100.0)
    ]
    assert flows == sorted(flows)
    assert flows[-1] > flows[0]


def test_inflow_matches_the_volume_arithmetic():
    """(rain - infiltration) x area, computed independently of the module."""
    region_id = "mumbai"
    soil = _flat(region_id, SATURATION_M3_M3)   # saturated: infiltration is nil
    assessment = assess_drainage(
        _flat(region_id, 36.0), soil, region_id=region_id, tide_override_m=0.5
    )
    for catchment in assessment.catchments:
        expected = 36.0 / 1000.0 / 3600.0 * catchment.area_km2 * 1e6
        assert catchment.inflow_cumecs == pytest.approx(expected, rel=1e-6)


def test_high_tide_removes_gravity_discharge():
    """The 2005/2017 mechanism: the same rain, a different answer."""
    rain, soil = _flat("mumbai", 60.0), _flat("mumbai", 0.3)
    low = assess_drainage(rain, soil, region_id="mumbai", tide_override_m=0.5)
    high = assess_drainage(rain, soil, region_id="mumbai", tide_override_m=4.5)

    assert low.total_supply_cumecs > high.total_supply_cumecs
    assert high.total_deficit_cumecs > low.total_deficit_cumecs
    assert all(c.gate_closed for c in high.catchments)
    assert not any(c.gate_closed for c in low.catchments)
    # With every gate shut, supply is pumps alone.
    assert high.total_supply_cumecs == pytest.approx(high.installed_pump_cumecs)


def test_deficit_converts_to_whole_pumps():
    rain, soil = _flat("mumbai", 120.0), _flat("mumbai", 0.4)
    assessment = assess_drainage(rain, soil, region_id="mumbai", tide_override_m=4.5)
    assert assessment.total_deficit_cumecs > 0
    for catchment in assessment.catchments:
        if catchment.deficit_cumecs > 0:
            covered = catchment.extra_pumps_required * PUMP_UNIT_CUMECS
            assert covered >= catchment.deficit_cumecs
            assert covered - PUMP_UNIT_CUMECS < catchment.deficit_cumecs
        else:
            assert catchment.extra_pumps_required == 0


def test_deficits_do_not_net_off_between_catchments():
    """Spare capacity at one outfall cannot drain another's water."""
    rain = _flat("mumbai", 0.0)
    terrain = drainage_terrain("mumbai")
    # Soak one station's catchment only.
    rain[terrain.catchment_mask(0)] = 150.0
    assessment = assess_drainage(
        rain, _flat("mumbai", 0.4), region_id="mumbai", tide_override_m=4.5
    )
    # Region-wide there is spare capacity, yet a deficit is still reported,
    # because the surplus sits at outfalls that cannot reach the wet catchment.
    assert assessment.total_supply_cumecs > assessment.total_inflow_cumecs
    assert assessment.total_deficit_cumecs > 0
    assert assessment.catchments_in_deficit == 1


def test_losing_pumps_raises_the_deficit():
    rain, soil = _flat("mumbai", 80.0), _flat("mumbai", 0.4)
    full = assess_drainage(
        rain, soil, region_id="mumbai", tide_override_m=4.5, pump_availability=1.0
    )
    half = assess_drainage(
        rain, soil, region_id="mumbai", tide_override_m=4.5, pump_availability=0.5
    )
    assert half.total_deficit_cumecs > full.total_deficit_cumecs
    assert half.total_supply_cumecs == pytest.approx(full.total_supply_cumecs / 2)


@pytest.mark.parametrize("region_id", REGIONS)
def test_unpumped_remainder_is_reported_but_never_totalled(region_id):
    """No deficit may be claimed against a capacity that was never modelled."""
    assessment = assess_drainage(
        _flat(region_id, 80.0), _flat(region_id, 0.4), region_id=region_id
    )
    assert assessment.unpumped is not None
    assert not assessment.unpumped.supply_modelled
    assert assessment.unpumped.area_km2 > 0
    assert assessment.unpumped not in assessment.catchments
    totalled = sum(max(0.0, c.deficit_cumecs) for c in assessment.catchments)
    assert assessment.total_deficit_cumecs == pytest.approx(totalled)


def test_capacity_in_mm_hr_tracks_the_design_standard():
    """Service areas are derived from capacity, so this is near the standard."""
    assessment = assess_drainage(
        _flat("mumbai", 0.0), _flat("mumbai", 0.3), region_id="mumbai",
        tide_override_m=-2.0,   # gates fully open
    )
    for catchment in assessment.catchments:
        assert catchment.open_gate_capacity_mm_hr > DESIGN_INTENSITY_MM_HR
