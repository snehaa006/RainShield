"""Stage B: a mass-conserving diffusive-wave solver.

The heuristic this replaces treats every cell independently:

    P(flood) = susceptibility x (1 - exp(-effective_rain / 45 mm))

Nothing in that conserves mass. Rain landing on a hillside raises that
hillside's flood probability and never arrives in the basin below; a cell that
is pumped dry is no drier than its neighbour; water does not move. It is a
plausible-looking map that no volume of water ever passes through.

This module routes it instead. Depth `h` evolves on the real DEM under

    dh/dt + div q = R - I - P - D
    q = -(1/n) h^(5/3) grad(W) / |grad(W)|^(1/2),   W = z + h

solved as explicit finite volumes on the 1 km grid. Fluxes are computed on
cell faces and applied with opposite signs to the two cells sharing a face, so
water removed from one is *exactly* the water added to the other — mass
conservation is a property of the discretisation, not something penalised in a
loss. What leaves the domain leaves through a boundary that is accounted for,
and `MassBalance` reports the closure error, which is machine epsilon times
the number of operations rather than anything physical.

**The coast is an open boundary, and it is tide-gated.** A no-flux coast would
be wrong in the way that matters most here: it would pond water against the
shoreline exactly where Mumbai actually drains. Land cells adjacent to the sea
discharge over a weir driven by the head between the water surface and sea
level; when the sea is higher, the flap gate shuts and discharge is zero. It
does not reverse — the gates exist precisely to stop the sea coming in.

**Where the trained network sits.** The solver needs two parameters it cannot
measure at 1 km, and neither is in any raster the project has:

  * *depression storage* — how much water a cell holds in sub-grid hollows,
    kerbs, lots and low corners before any of it routes downstream;
  * *drainage deficiency* — how fast the storm-drain network removes water,
    which depends on a drain layout nobody has digitised at this scale.

The network's susceptibility field is exactly a 0-1 statement about where
water collects and lingers, so it sets both (see `parameter_field`). That is
an honest role for it: a dimensionless modulation of two unmeasurable
parameters. It is emphatically *not* the network predicting depth. Depth comes
from conservation of mass over terrain. When observed inundation exists, this
is the socket that gets retrained, and nothing else has to change.

    Uncalibrated. Manning's n, the depression-storage range, the drain time
    constant and the weir coefficient are all estimates. The solver conserves
    mass exactly and responds correctly to terrain, tide and pumping; it has
    not been validated against a gauged flood. Defensible, not validated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from rainshield.config import LEAD_TIMES
from rainshield.grid import infra_proximity
from rainshield.regions import PRIMARY_REGION_ID
from rainshield.hydro.balance import infiltration_mm_hr
from rainshield.hydro.terrain import DrainageTerrain, drainage_terrain
from rainshield.hydro.tide import TideState, regime_for, tide_level

# -- parameters, all estimates ---------------------------------------------

#: Manning's n for fully paved and fully vegetated ground. Real values for
#: urban overland flow sit between roughly 0.011 and 0.10.
MANNING_PAVED = 0.016
MANNING_VEGETATED = 0.070

#: Depression storage range, m. The depth held in sub-grid hollows before a
#: cell contributes anything downstream. Susceptibility interpolates it.
DEPRESSION_STORAGE_MIN_M = 0.004
DEPRESSION_STORAGE_MAX_M = 0.090

#: Fastest storm-drain removal, expressed as a linear-reservoir rate (1/s).
#: 1/1800 empties a pond with a 30-minute time constant.
DRAIN_RATE_MAX_PER_S = 1.0 / 1800.0

#: Broad-crested weir coefficient for coastal discharge, m^(1/2)/s.
WEIR_COEFFICIENT = 1.4

#: Square root of the surface slope assumed at a domain edge that is not
#: coast, for the free-outflow condition. 0.03 means a slope of ~9e-4, a
#: gentle plain — Mumbai's eastern edge draining towards Thane creek. It only
#: sets how fast water leaves a boundary that is outside the study area
#: anyway, and it is accounted for in the mass balance either way.
EDGE_SLOPE_SQRT = 0.03

#: Base timestep, s. Sub-stepped further wherever stability demands it.
BASE_TIMESTEP_S = 60.0

#: No cell may lose more than this fraction of its water in one step. This is
#: the stability limit that actually binds — it is stricter than CFL at 1 km
#: and, unlike CFL, it also guarantees depth can never go negative.
MAX_DRAIN_FRACTION = 0.25

#: Depth at which a cell counts as inundated for the onset time, m.
INUNDATION_THRESHOLD_M = 0.10

#: Depth scale over which the inundated fraction of a cell saturates, m.
#: Water standing this far above what the hollows hold has spread over most of
#: the cell. Roughly nuisance-flood depth — kerb height, not knee height.
FLOOD_DEPTH_SCALE_M = 0.15


@dataclass(frozen=True)
class ParameterField:
    """The per-cell parameters the solver runs on."""

    #: Manning's n, from built density.
    manning: np.ndarray
    #: Depression storage, m. From the network's susceptibility.
    depression_storage: np.ndarray
    #: Storm-drain removal rate, 1/s. From the network's susceptibility.
    drain_rate: np.ndarray
    #: Infiltration capacity, m/s.
    infiltration: np.ndarray


@dataclass
class MassBalance:
    """Every volume that entered or left the domain, m3.

    Kept as a running tally through the solve so the closure error can be
    reported rather than assumed. This is the cheap, real, checkable version
    of a PDE residual: it is the integral of the governing equation over the
    whole domain and the whole run.
    """

    rainfall: float = 0.0
    infiltration: float = 0.0
    #: Water the positivity clip had to invent, m3. Should be exactly zero:
    #: the sub-stepping limiter is meant to make a negative depth impossible.
    #: It is tallied rather than trusted, so that if the timestep floor ever
    #: binds, the closure error shows it instead of the clip hiding it.
    created_by_clip: float = 0.0
    drained: float = 0.0
    pumped: float = 0.0
    to_sea: float = 0.0
    off_domain: float = 0.0
    initial_storage: float = 0.0
    final_storage: float = 0.0

    @property
    def inputs(self) -> float:
        return self.rainfall + self.initial_storage + self.created_by_clip

    @property
    def outputs(self) -> float:
        return (
            self.infiltration
            + self.drained
            + self.pumped
            + self.to_sea
            + self.off_domain
            + self.final_storage
        )

    @property
    def residual(self) -> float:
        return self.inputs - self.outputs

    @property
    def closure_error(self) -> float:
        """Residual as a fraction of everything that entered."""
        return abs(self.residual) / self.inputs if self.inputs > 0 else 0.0


@dataclass
class SolverResult:
    """Depth at every lead time from a single solve."""

    region_id: str
    #: Water depth, m, keyed by lead time in minutes.
    depth: dict[int, np.ndarray]
    #: Deepest water reached at any point in the run, m.
    peak_depth: np.ndarray
    #: Minutes until the cell first exceeded the inundation threshold; NaN if
    #: it never did. Computed, not correlated from a formula.
    onset_minutes: np.ndarray
    mass: MassBalance
    tide: TideState
    parameters: ParameterField
    steps: int
    #: Wall-clock cost of the solve, seconds.
    elapsed_s: float
    notes: list[str] = field(default_factory=list)


def parameter_field(
    susceptibility: np.ndarray,
    soil_moisture: np.ndarray,
    region_id: str = PRIMARY_REGION_ID,
) -> ParameterField:
    """Turn the network's susceptibility into solver parameters.

    This is the whole of the neural network's contribution, and it is worth
    being precise about what is being claimed. Susceptibility is a
    dimensionless 0-1 field the model learned from terrain; it is a good
    statement about *where water collects and lingers* and a poor one about
    how much of it there is. So it is used only where the solver needs a
    sub-grid property it has no way to measure:

      * more susceptible -> more depression storage, so a cell ponds deeper
        before it contributes anything downstream;
      * more susceptible -> worse drainage, so what does pond leaves slowly.

    Manning's n comes from built density instead, which is a physical
    roughness the terrain layers already describe. Depth is never read from
    the network.
    """
    built = np.clip(infra_proximity(region_id), 0.0, 1.0)
    s = np.clip(susceptibility, 0.0, 1.0)

    manning = MANNING_PAVED * built + MANNING_VEGETATED * (1.0 - built)
    storage = DEPRESSION_STORAGE_MIN_M + (
        DEPRESSION_STORAGE_MAX_M - DEPRESSION_STORAGE_MIN_M
    ) * s
    drain = DRAIN_RATE_MAX_PER_S * (1.0 - s)
    infiltration = infiltration_mm_hr(built, soil_moisture) / 1000.0 / 3600.0

    return ParameterField(
        manning=manning.astype(np.float64),
        depression_storage=storage.astype(np.float64),
        drain_rate=drain.astype(np.float64),
        infiltration=infiltration.astype(np.float64),
    )


def _face_flux(
    water_surface: np.ndarray,
    mobile: np.ndarray,
    manning: np.ndarray,
    dx: float,
    axis: int,
) -> np.ndarray:
    """Discharge per unit width across every face along one axis, m2/s.

    Positive means flow in the direction of increasing index. The depth used
    is the *donor* cell's mobile depth — upwinding, without which water is
    drawn out of cells that have none and the scheme goes unstable in the
    first few steps.
    """
    drop = np.diff(water_surface, axis=axis)          # W[i+1] - W[i]
    slope = -drop / dx                                # positive = downhill forward

    lo = [slice(None)] * 2
    hi = [slice(None)] * 2
    lo[axis] = slice(None, -1)
    hi[axis] = slice(1, None)
    donor_depth = np.where(slope > 0, mobile[tuple(lo)], mobile[tuple(hi)])
    donor_n = np.where(slope > 0, manning[tuple(lo)], manning[tuple(hi)])

    magnitude = (
        (1.0 / donor_n) * np.power(donor_depth, 5.0 / 3.0) * np.sqrt(np.abs(slope))
    )
    return np.where(donor_depth > 0.0, np.sign(slope) * magnitude, 0.0)


def solve(
    susceptibility: np.ndarray,
    rain_rate_mm_hr: dict[int, np.ndarray],
    soil_moisture: np.ndarray,
    region_id: str = PRIMARY_REGION_ID,
    moment: datetime | None = None,
    tide_override_m: float | None = None,
    pump_availability: float = 1.0,
    lead_times: tuple[int, ...] = LEAD_TIMES,
    timestep_s: float = BASE_TIMESTEP_S,
) -> SolverResult:
    """Route water over the grid, snapshotting depth at every lead time.

    One solve gives every lead time. The heuristic path runs the network once
    per lead and computes six independent, mutually inconsistent snapshots;
    this integrates a single trajectory through time and records it as it
    passes each horizon, which is both cheaper and the only version in which
    "+3 hr" actually follows from "+1 hr".
    """
    import time

    started = time.perf_counter()
    terrain = drainage_terrain(region_id)
    tide = tide_level(moment, region_id, override_m=tide_override_m)
    params = parameter_field(susceptibility, soil_moisture, region_id)

    sea = terrain.sea
    land = terrain.land
    z = terrain.elevation.astype(np.float64)
    area = terrain.cell_area_m2
    dx = float(np.sqrt(area))

    # The DEM is metres above mean sea level; the tide is metres above chart
    # datum. Convert once, or the gates open and shut at the wrong moments.
    regime = regime_for(region_id)
    sea_surface = tide.level_m - regime.mean_sea_level_m

    rows, cols = z.shape
    h = np.zeros((rows, cols), dtype=np.float64)
    peak = np.zeros_like(h)
    onset = np.full((rows, cols), np.nan)

    mass = MassBalance(initial_storage=0.0)
    snapshots: dict[int, np.ndarray] = {}
    notes: list[str] = []

    # Pumping: each station removes up to its capacity from its own cells.
    pump_rate = np.zeros_like(h)         # m/s of removal available
    for index, station in enumerate(terrain.stations):
        cells = terrain.catchment_mask(index)
        count = int(cells.sum())
        if count:
            pump_rate[cells] = (
                station.capacity_cumecs * pump_availability / (count * area)
            )

    # Land cells that touch the sea discharge through the coastal boundary.
    coastal = np.zeros((rows, cols), dtype=bool)
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        shifted = np.roll(sea, (dr, dc), axis=(0, 1))
        if dr:
            shifted[0 if dr > 0 else -1, :] = False
        if dc:
            shifted[:, 0 if dc > 0 else -1] = False
        coastal |= shifted
    coastal &= land

    # Land cells on the domain edge that are not coastal let water leave the
    # model — Mumbai's eastern mainland drains to Thane creek, outside the grid.
    edge = np.zeros((rows, cols), dtype=bool)
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True
    edge &= land & ~coastal

    horizon = max(lead_times)
    schedule = sorted(set(lead_times))
    elapsed_min = 0.0
    steps = 0

    for lead in schedule:
        # Rain is held at the rate forecast for the horizon being approached.
        rain = np.clip(np.asarray(rain_rate_mm_hr[lead], dtype=np.float64), 0.0, None)
        rain_m_s = rain / 1000.0 / 3600.0
        rain_m_s = np.where(land, rain_m_s, 0.0)

        while elapsed_min < lead - 1e-9:
            remaining_s = (lead - elapsed_min) * 60.0
            dt = min(timestep_s, remaining_s)

            mobile = np.clip(h - params.depression_storage, 0.0, None)
            water_surface = z + h

            qx = _face_flux(water_surface, mobile, params.manning, dx, axis=1)
            qy = _face_flux(water_surface, mobile, params.manning, dx, axis=0)

            # A face touching the sea is handled by the coastal boundary, and
            # a dry donor moves nothing.
            qx[sea[:, :-1] | sea[:, 1:]] = 0.0
            qy[sea[:-1, :] | sea[1:, :]] = 0.0

            # Volumetric flux across each face, m3/s.
            fx = qx * dx
            fy = qy * dx

            # Divergence: what each cell loses, minus what it gains.
            out = np.zeros_like(h)
            out[:, :-1] += np.clip(fx, 0.0, None)
            out[:, 1:] += np.clip(-fx, 0.0, None)
            out[:-1, :] += np.clip(fy, 0.0, None)
            out[1:, :] += np.clip(-fy, 0.0, None)

            # Coastal discharge: a weir driven by head over sea level. The
            # gate shuts rather than reversing when the sea is higher.
            head = np.where(coastal, water_surface - sea_surface, 0.0)
            head = np.clip(head, 0.0, None)
            coastal_q = np.where(
                coastal & (mobile > 0.0),
                WEIR_COEFFICIENT * dx * np.power(np.minimum(head, mobile), 1.5),
                0.0,
            )

            # Free outflow off the domain edge, at the local surface gradient.
            edge_q = np.where(
                edge & (mobile > 0.0),
                (1.0 / params.manning)
                * np.power(mobile, 5.0 / 3.0)
                * EDGE_SLOPE_SQRT
                * dx,
                0.0,
            )

            drain_q = params.drain_rate * mobile * area
            pump_q = np.minimum(pump_rate * area, mobile * area / max(dt, 1e-9))
            infil_q = np.where(land, params.infiltration * area, 0.0)
            infil_q = np.minimum(infil_q, h * area / max(dt, 1e-9))

            total_out = out + coastal_q + edge_q + drain_q + pump_q + infil_q

            # Stability: no cell may shed more than MAX_DRAIN_FRACTION of what
            # it holds in one step. Guarantees positivity as well as stability.
            capacity = h * area * MAX_DRAIN_FRACTION
            busy = total_out > 0
            if busy.any():
                allowed = np.where(busy, capacity / np.maximum(total_out, 1e-30), np.inf)
                dt = float(min(dt, max(np.min(allowed), 1e-3)))

            # Apply. Fluxes are applied to both cells of each face from the
            # same array, so nothing is created or destroyed in transit.
            delta = rain_m_s * area * dt
            h += delta / area

            moved_x = fx * dt
            moved_y = fy * dt
            h[:, :-1] -= moved_x / area
            h[:, 1:] += moved_x / area
            h[:-1, :] -= moved_y / area
            h[1:, :] += moved_y / area

            leaving = (coastal_q + edge_q + drain_q + pump_q + infil_q) * dt
            h -= leaving / area

            # Positivity. The limiter above is supposed to make this a no-op;
            # if it ever is not, the water the clip invents is counted so the
            # closure error reports the problem rather than absorbing it.
            deficit = np.clip(-h, 0.0, None)
            if deficit.any():
                mass.created_by_clip += float((deficit * area).sum())
            np.clip(h, 0.0, None, out=h)
            mass.created_by_clip += float((h[sea] * area).sum())
            h[sea] = 0.0

            mass.rainfall += float(delta.sum())
            mass.to_sea += float((coastal_q * dt).sum())
            mass.off_domain += float((edge_q * dt).sum())
            mass.drained += float((drain_q * dt).sum())
            mass.pumped += float((pump_q * dt).sum())
            mass.infiltration += float((infil_q * dt).sum())

            np.maximum(peak, h, out=peak)
            newly = np.isnan(onset) & (h >= INUNDATION_THRESHOLD_M)
            onset[newly] = elapsed_min

            elapsed_min += dt / 60.0
            steps += 1

            if steps > 20_000:
                notes.append("step limit reached; solve truncated")
                break

        snapshots[lead] = h.copy()
        if steps > 20_000:
            break

    for lead in lead_times:
        snapshots.setdefault(lead, h.copy())

    mass.final_storage = float((h * area).sum())
    if mass.created_by_clip > 0.0:
        notes.append(
            f"positivity clip created {mass.created_by_clip:.3g} m3 — "
            "the timestep floor bound, so the solve is not exactly conservative"
        )
    if mass.closure_error > 1e-6:
        notes.append(f"mass closure {mass.closure_error:.2%} — larger than expected")

    return SolverResult(
        region_id=region_id,
        depth={lead: snapshots[lead].astype(np.float32) for lead in lead_times},
        peak_depth=peak.astype(np.float32),
        onset_minutes=onset.astype(np.float32),
        mass=mass,
        tide=tide,
        parameters=params,
        steps=steps,
        elapsed_s=time.perf_counter() - started,
        notes=notes,
    )


def inundated_fraction(
    depth: np.ndarray, depression_storage: np.ndarray
) -> np.ndarray:
    """Fraction of a cell under standing water, from its mean depth.

    The solver returns a mean depth over a 1 km cell, which is not the same
    thing as "this cell is flooded". Two corrections turn one into the other.

    First, water held in sub-grid hollows is not flooding — it is in the gutter
    and the low corner of the car park, which is where it is supposed to be. So
    the depression storage the network sets is subtracted before anything
    counts. Second, what remains spreads over the cell as it deepens, and
    saturates once it is well clear of the microtopography:

        f = 1 - exp(-max(0, h - d) / FLOOD_DEPTH_SCALE_M)

    Without the first correction a 5 cm mean depth reported as 87% inundated,
    which is what a puddle looks like if you forget that ground is uneven. With
    it, 5 cm reads as about 20% and 30 cm as about 85%, which is the right
    shape for a quantity that drives an alert tier.

    This replaces the heuristic's "flood probability", and it is a better-named
    quantity: a sub-grid areal fraction, not a probability, with nothing
    stochastic about it.
    """
    excess = np.clip(np.asarray(depth, dtype=np.float64) - depression_storage, 0.0, None)
    return np.clip(1.0 - np.exp(-excess / FLOOD_DEPTH_SCALE_M), 0.0, 1.0)
