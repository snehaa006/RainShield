"""Stage A: catchment mass balance and the pumping-capacity question.

This is the arithmetic that answers the question directly:

    inflow  = (rainfall - infiltration) x catchment area          [m3/s]
    supply  = tide-gated gravity outfall + installed pump capacity [m3/s]
    deficit = inflow - supply
    required = deficit expressed as N more pumps of PUMP_UNIT_CUMECS

No PDE and no state — one pass per catchment per lead time. It is deliberately
additive: nothing here feeds back into `hazard.py`, so the probabilities,
depths and risk scores on the rest of the board are untouched by it.

Two things make the answer non-trivial, and both are the point:

**Infiltration is not a constant.** A cell's loss rate depends on how much of
it is paved and how wet the ground already is. Mumbai's built-up core sheds
almost everything that falls on it; the periurban fringe absorbs a real
fraction. Antecedent soil moisture closes that gap as a storm proceeds, which
is why the third hour of a monsoon spell produces far more runoff than the
first.

**Gravity discharge is not a constant either.** Once sea level rises above an
outfall invert the flap gate shuts and gravity discharge stops entirely. That
is the mechanism behind 2005 and 2017, and it means "is the installed capacity
sufficient?" genuinely has two different answers at low and high water — which
is what makes the tide control on the dashboard worth having.

    Uncalibrated. Infiltration rates, runoff behaviour, gravity capacities and
    outfall inverts are all estimates (see `stations`). The structure of the
    calculation is sound and mass is conserved within it; the coefficients
    have not been fitted to a gauged storm. Read the *comparison* between
    inflow and capacity, and how it moves with tide, rather than the absolute
    cumecs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from rainshield.grid import infra_proximity, static_layers
from rainshield.regions import PRIMARY_REGION_ID
from rainshield.hydro.stations import (
    DESIGN_INTENSITY_MM_HR,
    PUMP_UNIT_CUMECS,
    PumpStation,
)
from rainshield.hydro.terrain import DrainageTerrain, drainage_terrain
from rainshield.hydro.tide import TideState, tide_level

#: Infiltration capacity of fully pervious ground, mm/hr. A monsoon-climate
#: loam on the low end of its range, since the profile is rarely dry in season.
PERVIOUS_INFILTRATION_MM_HR = 9.0

#: Infiltration through fully built-up ground, mm/hr. Not zero: even dense
#: urban fabric leaks through joints, verges and unsealed margins.
IMPERVIOUS_INFILTRATION_MM_HR = 1.2

#: Volumetric soil moisture (m3/m3) at which infiltration capacity has fallen
#: to zero. Saturated ground accepts nothing further.
SATURATION_M3_M3 = 0.45

#: Head below an outfall invert at which gravity discharge reaches its design
#: capacity, m. Discharge follows sqrt(head) below this, as an orifice does.
GRAVITY_DESIGN_HEAD_M = 1.0

#: Nominal gravity capacity of one unpumped coastal outfall, m3/s, and the
#: invert level assumed for it. Both are ESTIMATES standing in for outfalls
#: that are not individually surveyed in this model.
UNGAUGED_OUTFALL_CUMECS = 3.0
UNGAUGED_INVERT_M_CD = 1.6

#: Catchment index meaning "drains to the coast without a modelled station".
UNSERVED = -1


def infiltration_mm_hr(
    imperviousness: np.ndarray, soil_moisture: np.ndarray
) -> np.ndarray:
    """Per-cell infiltration capacity, mm/hr.

    Linear between the pervious and impervious rates by built fraction, then
    scaled down by how close the soil already is to saturation. Both factors
    only ever reduce the loss, so runoff is never underestimated by them.
    """
    built = np.clip(imperviousness, 0.0, 1.0)
    base = (
        PERVIOUS_INFILTRATION_MM_HR * (1.0 - built)
        + IMPERVIOUS_INFILTRATION_MM_HR * built
    )
    wetness = np.clip(soil_moisture / SATURATION_M3_M3, 0.0, 1.0)
    return (base * (1.0 - wetness)).astype(np.float32)


def gravity_discharge(
    design_cumecs: float, invert_m_cd: float, tide_m_cd: float
) -> float:
    """Gravity discharge available through a tide-gated outfall, m3/s.

    Zero once the sea is above the invert — the flap gate is shut and there is
    nothing gravity can do. Below it, discharge follows the square root of the
    available head up to the design capacity, which is the standard orifice
    relation and gives the smooth roll-off a hard on/off switch would not.
    """
    head = invert_m_cd - tide_m_cd
    if head <= 0.0:
        return 0.0
    return float(design_cumecs * min(1.0, math.sqrt(head / GRAVITY_DESIGN_HEAD_M)))


@dataclass(frozen=True)
class CatchmentBalance:
    """The mass balance of one drainage catchment at one lead time."""

    id: str
    name: str
    #: The station serving it, or None for the unserved remainder.
    station: PumpStation | None
    area_km2: float
    cell_count: int
    #: Catchment-mean rainfall over the accounting window, mm/hr.
    rainfall_mm_hr: float
    #: Catchment-mean infiltration capacity, mm/hr.
    infiltration_mm_hr: float
    #: Runoff actually generated, mm/hr — rainfall less infiltration, floored
    #: at zero per cell before averaging.
    net_runoff_mm_hr: float
    #: Volumetric inflow arriving at the outfall, m3/s.
    inflow_cumecs: float
    #: Gravity discharge available right now, m3/s. Tide-dependent.
    gravity_cumecs: float
    #: Installed pump capacity, m3/s.
    pump_cumecs: float
    #: gravity + pump, m3/s.
    supply_cumecs: float
    #: inflow - supply. Positive means water is accumulating.
    deficit_cumecs: float
    #: Additional pumps of PUMP_UNIT_CUMECS needed to close the deficit.
    extra_pumps_required: int
    #: The rainfall intensity the current supply can clear over this
    #: catchment, mm/hr. The most directly comparable number on the panel:
    #: put it beside `rainfall_mm_hr` and the answer is immediate.
    capacity_mm_hr: float
    #: The same with the tide gate open — the catchment's best case.
    open_gate_capacity_mm_hr: float
    #: True when the gravity gate is shut by the tide.
    gate_closed: bool
    #: False for the unserved remainder, whose capacity is a nominal stand-in
    #: rather than a modelled station.
    supply_modelled: bool

    @property
    def sufficient(self) -> bool:
        return self.deficit_cumecs <= 0.0

    @property
    def utilisation(self) -> float:
        """Inflow as a fraction of supply. >1 means accumulating."""
        if self.supply_cumecs <= 0.0:
            return float("inf") if self.inflow_cumecs > 0 else 0.0
        return self.inflow_cumecs / self.supply_cumecs


@dataclass(frozen=True)
class DrainageAssessment:
    """Every catchment in a region at one lead time, plus the totals."""

    region_id: str
    lead: int
    tide: TideState
    #: Catchments with a modelled pumping station. The totals cover these and
    #: only these — they are the only ground this model has a capacity figure
    #: for, so they are the only ground it can say "sufficient" or not about.
    catchments: tuple[CatchmentBalance, ...]
    #: Everything else: land draining to outfalls this model does not survey.
    #: Reported so the area is visible and not silently dropped, but kept out
    #: of every total, because a deficit against a capacity we never modelled
    #: would be an invented number.
    unpumped: CatchmentBalance | None
    total_inflow_cumecs: float
    total_supply_cumecs: float
    total_deficit_cumecs: float
    total_extra_pumps: int
    #: Installed pump capacity across the region, m3/s.
    installed_pump_cumecs: float
    #: Catchments where inflow exceeds supply.
    catchments_in_deficit: int
    #: The design standard the service areas were sized at, mm/hr.
    design_intensity_mm_hr: float

    @property
    def sufficient(self) -> bool:
        return self.total_deficit_cumecs <= 0.0


def _balance_one(
    index: int,
    station: PumpStation | None,
    terrain: DrainageTerrain,
    rain_mm_hr: np.ndarray,
    infiltration: np.ndarray,
    tide_m: float,
    pump_availability: float,
) -> CatchmentBalance | None:
    mask = terrain.catchment_mask(index)
    cells = int(mask.sum())
    if cells == 0:
        return None

    area_m2 = cells * terrain.cell_area_m2
    rain = rain_mm_hr[mask]
    loss = infiltration[mask]
    # Floor per cell before averaging: a dry cell cannot lend its spare
    # infiltration capacity to a saturated one next door.
    net = np.clip(rain - loss, 0.0, None)

    # mm/hr -> m/s, times area, gives m3/s.
    inflow = float(net.mean()) / 1000.0 / 3600.0 * area_m2

    n_outlets = 0
    if station is not None:
        gravity = gravity_discharge(station.gravity_cumecs, station.outfall_invert_m_cd, tide_m)
        pumps = station.capacity_cumecs * pump_availability
        invert = station.outfall_invert_m_cd
        modelled = True
        cid, name = station.id, station.name
    else:
        # The remainder drains through outfalls this model does not survey
        # individually. Scale a nominal per-outfall capacity by how many
        # distinct coastal outlets the remainder actually discharges through,
        # so the figure at least tracks the size of the coastline it uses.
        outlets = np.unique(terrain.outlet.reshape(terrain.shape)[mask])
        n_outlets = int((outlets >= 0).sum())
        gravity = n_outlets * gravity_discharge(
            UNGAUGED_OUTFALL_CUMECS, UNGAUGED_INVERT_M_CD, tide_m
        )
        pumps = 0.0
        invert = UNGAUGED_INVERT_M_CD
        modelled = False
        cid, name = "unserved", "Gravity outfalls (no modelled station)"

    supply = gravity + pumps
    deficit = inflow - supply

    # Supply expressed back as an intensity over this catchment, so it can be
    # compared with the rainfall directly rather than through a volume.
    to_mm_hr = 1000.0 * 3600.0 / area_m2
    open_gate = (
        gravity_discharge(station.gravity_cumecs, station.outfall_invert_m_cd, -99.0)
        if station is not None
        else n_outlets * UNGAUGED_OUTFALL_CUMECS
    ) + pumps

    return CatchmentBalance(
        id=cid,
        name=name,
        station=station,
        area_km2=area_m2 / 1e6,
        cell_count=cells,
        rainfall_mm_hr=float(rain.mean()),
        infiltration_mm_hr=float(loss.mean()),
        net_runoff_mm_hr=float(net.mean()),
        inflow_cumecs=inflow,
        gravity_cumecs=gravity,
        pump_cumecs=pumps,
        supply_cumecs=supply,
        deficit_cumecs=deficit,
        extra_pumps_required=max(0, math.ceil(deficit / PUMP_UNIT_CUMECS)) if deficit > 0 else 0,
        capacity_mm_hr=supply * to_mm_hr,
        open_gate_capacity_mm_hr=open_gate * to_mm_hr,
        gate_closed=tide_m >= invert,
        supply_modelled=modelled,
    )


def assess_drainage(
    rain_mm_hr: np.ndarray,
    soil_moisture: np.ndarray,
    lead: int = 0,
    region_id: str = PRIMARY_REGION_ID,
    moment: datetime | None = None,
    tide_override_m: float | None = None,
    pump_availability: float = 1.0,
) -> DrainageAssessment:
    """Run the Stage A balance over every catchment in a region.

    `rain_mm_hr` is the rate the accounting is done at — the balance asks
    whether the system can keep up with the rain that is falling, so an
    instantaneous rate is the right input rather than an accumulation.

    `tide_override_m` pins sea level, for asking what the same storm would do
    at high water. `pump_availability` scales installed capacity, for asking
    what happens when a station is down.
    """
    terrain = drainage_terrain(region_id)
    tide = tide_level(moment, region_id, override_m=tide_override_m)
    imperviousness = infra_proximity(region_id)
    infiltration = infiltration_mm_hr(imperviousness, soil_moisture)

    balances: list[CatchmentBalance] = []
    for i, station in enumerate(terrain.stations):
        one = _balance_one(
            i, station, terrain, rain_mm_hr, infiltration, tide.level_m, pump_availability
        )
        if one is not None:
            balances.append(one)
    remainder = _balance_one(
        UNSERVED, None, terrain, rain_mm_hr, infiltration, tide.level_m, pump_availability
    )

    total_inflow = sum(b.inflow_cumecs for b in balances)
    total_supply = sum(b.supply_cumecs for b in balances)
    # Summed per catchment, not computed from the totals: surplus in one
    # catchment cannot drain another's water, so the deficits do not net off.
    total_deficit = sum(max(0.0, b.deficit_cumecs) for b in balances)

    return DrainageAssessment(
        region_id=region_id,
        lead=lead,
        tide=tide,
        catchments=tuple(balances),
        unpumped=remainder,
        total_inflow_cumecs=total_inflow,
        total_supply_cumecs=total_supply,
        total_deficit_cumecs=total_deficit,
        total_extra_pumps=sum(b.extra_pumps_required for b in balances),
        installed_pump_cumecs=sum(s.capacity_cumecs for s in terrain.stations),
        catchments_in_deficit=sum(1 for b in balances if b.deficit_cumecs > 0),
        design_intensity_mm_hr=DESIGN_INTENSITY_MM_HR,
    )
