"""Where water goes: sea mask, depression filling, D8 routing and catchments.

The hazard model this sits beside treats every cell independently — rain that
lands on a hillside raises that hillside's flood probability and never arrives
anywhere else. Routing is what fixes that, and routing needs three things the
raw DEM does not give you:

* **A sea mask.** Both regions have cells below zero elevation, but only the
  ones connected to the domain edge are sea; an inland pit at -2 m is a basin,
  not an inlet. The two are separated by flooding inward from the border, so
  the coast is discovered from the DEM rather than hardcoded — necessary,
  since Mumbai's sea is the western edge and the simulated delta's is the
  eastern one.

* **A depression-free surface.** A 1 km SRTM resample is full of one-cell
  pits, and D8 on a raw DEM terminates flow in every one of them. The
  priority-flood algorithm raises each pit to the lowest elevation on its rim,
  so every land cell has a downhill path to the sea. Fill depth is kept: it is
  a real physical quantity, the volume a basin holds before it spills, and the
  solver uses it.

* **Catchments.** A pumping station serves the land that drains to it — but
  how much land is a question 1 km cannot answer on its own. See below.

**Why the pumped service areas are design-derived, not delineated.** Working
back from installed capacity at BRIMSTOWAD's 50 mm/hr design standard, these
stations were built to drain catchments of roughly 1.3-2.6 km2 each. One cell
of this grid is 0.94 km2. A 1.3 km2 engineered catchment is therefore smaller
than the model's resolution, and a purely topographic D8 delineation does not
approximate it — asked for catchments within 1 km of each station it returns
nothing at all, and relaxed to 4.5 km it returns basins 5-25x too large,
because Mumbai has on the order of a hundred outfalls and only seven of them
are pumped. Attributing a whole coastal stretch to one station silently hands
it every other outfall's water.

So the two questions are separated. **Terrain decides which cells** — a cell is
eligible for a station only if its own flow path reaches the coast near that
station, which rules out everything draining the other way. **The design
standard decides how many** — the station's capacity divided by 50 mm/hr gives
the area it was built for, and the nearest eligible cells are taken up to that
area. Everything else is reported as unpumped, with no capacity claimed for it.

That keeps the comparison honest: inflow is measured over the area a station
was actually sized for, so "is capacity sufficient" is asked about the right
amount of ground. It is an assumption about design, not a survey of the drain
network, and it is labelled as one throughout.

At 1 km a catchment here is a drainage basin, not a street network. Real
BRIMSTOWAD hydraulic modelling runs at 10-30 m on the surveyed drain layout.
This is the catchment-scale question — how much water arrives at an outfall —
and nothing finer should be read into it.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from rainshield.grid import cell_centres, static_layers
from rainshield.regions import PRIMARY_REGION_ID, get_region
from rainshield.hydro.stations import (
    DESIGN_INTENSITY_MM_HR,
    PumpStation,
    stations_for,
)

#: Elevation at or below which a cell may be sea, m. Cells below this that are
#: not connected to the domain edge are inland depressions, not ocean.
SEA_LEVEL_M = 0.0

#: How far a coastal outlet may be from a pumping station for cells draining
#: through it to be *eligible* for that station's service area, km. This is an
#: eligibility filter on direction of flow, not the size of the catchment —
#: size comes from the design standard. Generous on purpose: narrowing it
#: cannot add cells, only starve a station of candidates.
STATION_REACH_KM = 5.0

#: Mean earth radius used to convert degrees to metres, m.
EARTH_RADIUS_M = 6_371_000.0

#: D8 neighbour offsets (drow, dcol) and their centre-to-centre distance
#: multiplier. Diagonals are sqrt(2) longer, which matters for the gradient.
_D8 = (
    (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
    (-1, -1, np.sqrt(2.0)), (-1, 1, np.sqrt(2.0)),
    (1, -1, np.sqrt(2.0)), (1, 1, np.sqrt(2.0)),
)


@dataclass(frozen=True)
class DrainageTerrain:
    """Everything the mass balance and the solver need about a region's shape."""

    region_id: str
    #: True where the cell is ocean (below sea level and connected to the edge).
    sea: np.ndarray
    #: Bare-earth elevation, m. Sea cells keep their negative values.
    elevation: np.ndarray
    #: Depression-filled elevation, m. Equal to `elevation` outside pits.
    filled: np.ndarray
    #: filled - elevation, m. The depth a basin ponds to before it spills.
    fill_depth: np.ndarray
    #: Flat index of the downslope neighbour, or -1 for sea and true outlets.
    downstream: np.ndarray
    #: Number of upslope cells draining through each cell, including itself.
    accumulation: np.ndarray
    #: Flat index of the coastal cell each land cell ultimately drains to,
    #: or -1 where the cell is sea.
    outlet: np.ndarray
    #: Index into `stations` of the station serving each cell; -1 where the
    #: cell drains to the coast without passing a modelled station.
    catchment: np.ndarray
    stations: tuple[PumpStation, ...]
    #: Ground area of one cell, m2.
    cell_area_m2: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.sea.shape

    @property
    def land(self) -> np.ndarray:
        return ~self.sea

    def catchment_mask(self, index: int) -> np.ndarray:
        """Cells served by station `index`, or by no station when -1."""
        return (self.catchment == index) & self.land

    def catchment_area_m2(self, index: int) -> float:
        return float(self.catchment_mask(index).sum()) * self.cell_area_m2


def cell_area_m2(region_id: str = PRIMARY_REGION_ID) -> float:
    """Ground area of one grid cell, m2.

    Computed from the region's own degree spacing at its centre latitude
    rather than assumed to be exactly 1 km2, so the two regions — which sit at
    different latitudes — both get their true area.
    """
    g = get_region(region_id).geometry
    lat = np.deg2rad(g.centre[1])
    metres_per_deg_lat = EARTH_RADIUS_M * np.pi / 180.0
    metres_per_deg_lon = metres_per_deg_lat * np.cos(lat)
    return float(g.cell_height * metres_per_deg_lat * g.cell_width * metres_per_deg_lon)


def sea_mask(elevation: np.ndarray, sea_level: float = SEA_LEVEL_M) -> np.ndarray:
    """Ocean cells: at or below sea level AND connected to the domain edge.

    A breadth-first flood inward from the border. An inland cell below sea
    level that no chain of below-sea-level cells connects to the edge is a
    closed depression — Mumbai has several — and stays land, because water
    collects in it rather than draining out through it.
    """
    rows, cols = elevation.shape
    low = elevation <= sea_level
    sea = np.zeros_like(low, dtype=bool)

    stack: list[tuple[int, int]] = []
    for c in range(cols):
        for r in (0, rows - 1):
            if low[r, c] and not sea[r, c]:
                sea[r, c] = True
                stack.append((r, c))
    for r in range(rows):
        for c in (0, cols - 1):
            if low[r, c] and not sea[r, c]:
                sea[r, c] = True
                stack.append((r, c))

    while stack:
        r, c = stack.pop()
        for dr, dc, _ in _D8:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and low[nr, nc] and not sea[nr, nc]:
                sea[nr, nc] = True
                stack.append((nr, nc))
    return sea


def fill_depressions(elevation: np.ndarray, sea: np.ndarray) -> np.ndarray:
    """Priority-flood depression filling, seeded from the sea and the border.

    Every cell is raised to the highest water level it would have to reach to
    escape, which is the running maximum along the cheapest path out. The
    result is hydrologically conditioned: no interior cell is a local minimum,
    so D8 always finds a way downhill.
    """
    rows, cols = elevation.shape
    filled = elevation.astype(np.float64).copy()
    closed = np.zeros((rows, cols), dtype=bool)
    heap: list[tuple[float, int, int]] = []

    def push(r: int, c: int) -> None:
        if not closed[r, c]:
            closed[r, c] = True
            heapq.heappush(heap, (float(filled[r, c]), r, c))

    # Seed from every sea cell and every domain-border cell: those are the
    # places water can leave from.
    for r in range(rows):
        for c in range(cols):
            if sea[r, c] or r in (0, rows - 1) or c in (0, cols - 1):
                push(r, c)

    while heap:
        level, r, c = heapq.heappop(heap)
        for dr, dc, _ in _D8:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols) or closed[nr, nc]:
                continue
            # To leave, this neighbour's water must at least reach `level`.
            if filled[nr, nc] < level:
                filled[nr, nc] = level
            closed[nr, nc] = True
            heapq.heappush(heap, (float(filled[nr, nc]), nr, nc))

    return filled.astype(np.float32)


def d8_downstream(filled: np.ndarray, sea: np.ndarray) -> np.ndarray:
    """Flat index of the steepest downslope neighbour, -1 for sea and sinks.

    Slope is per unit distance, so a diagonal drop is divided by sqrt(2) and
    does not beat an equal orthogonal drop that is physically steeper. Ties go
    to the first neighbour in `_D8` order, which is deterministic.
    """
    rows, cols = filled.shape
    down = np.full(rows * cols, -1, dtype=np.int32)
    for r in range(rows):
        for c in range(cols):
            if sea[r, c]:
                continue
            here = filled[r, c]
            best_slope = 0.0
            best = -1
            for dr, dc, length in _D8:
                nr, nc = r + dr, c + dc
                if not (0 <= nr < rows and 0 <= nc < cols):
                    continue
                if sea[nr, nc]:
                    # The sea is always downhill from land: discharge here.
                    slope = (here - min(filled[nr, nc], here)) / length + 1e3
                else:
                    slope = (here - filled[nr, nc]) / length
                if slope > best_slope:
                    best_slope = slope
                    best = nr * cols + nc
            down[r * cols + c] = best
    return down


def trace_outlets(downstream: np.ndarray, sea: np.ndarray) -> np.ndarray:
    """The coastal cell each land cell ultimately drains through.

    Walks each cell's flow path once and memoises, so the whole grid costs one
    pass rather than one walk per cell. A path that terminates inland (a sink
    the fill could not resolve) reports its own terminus, which keeps the
    result total instead of raising.
    """
    n = downstream.size
    flat_sea = sea.ravel()
    outlet = np.full(n, -2, dtype=np.int32)   # -2 = not yet resolved
    outlet[flat_sea] = -1

    for start in range(n):
        if outlet[start] != -2:
            continue
        path: list[int] = []
        node = start
        while node >= 0 and outlet[node] == -2:
            path.append(node)
            node = int(downstream[node])
        if node < 0:
            # Ran off the end of a flow path: the last cell is the terminus.
            terminus = path[-1] if path else start
        elif flat_sea[node]:
            terminus = node
        else:
            terminus = int(outlet[node])
        for cell in path:
            outlet[cell] = terminus
    return outlet


def flow_accumulation(downstream: np.ndarray, sea: np.ndarray) -> np.ndarray:
    """Upslope cell count per cell, including the cell itself.

    Cells are drained in descending topological order, which for D8 is simply
    descending order of the surface they were routed on — each cell's total is
    complete before it is passed downstream.
    """
    n = downstream.size
    indegree = np.zeros(n, dtype=np.int32)
    for cell in range(n):
        target = int(downstream[cell])
        if target >= 0:
            indegree[target] += 1

    accum = np.ones(n, dtype=np.float64)
    accum[sea.ravel()] = 0.0
    queue = [c for c in range(n) if indegree[c] == 0]
    while queue:
        cell = queue.pop()
        target = int(downstream[cell])
        if target < 0:
            continue
        accum[target] += accum[cell]
        indegree[target] -= 1
        if indegree[target] == 0:
            queue.append(target)
    return accum


def design_service_cells(station: PumpStation, cell_area_m2: float) -> int:
    """How many grid cells the station was built to drain.

    Installed capacity divided by the design intensity gives a design area;
    dividing by cell area gives a cell count. Always at least one cell — a
    station that exists drains *something*, and rounding it to zero would
    silently drop it from the assessment.
    """
    design_area_m2 = station.capacity_cumecs / (DESIGN_INTENSITY_MM_HR / 1000.0 / 3600.0)
    return max(1, int(round(design_area_m2 / cell_area_m2)))


def _assign_catchments(
    outlet: np.ndarray,
    sea: np.ndarray,
    stations: tuple[PumpStation, ...],
    lons: np.ndarray,
    lats: np.ndarray,
    centre_lat: float,
    cell_area_m2: float,
) -> np.ndarray:
    """Build each station's service area: terrain picks which, design picks how many.

    Two passes. First, eligibility — a cell may be served by a station only if
    its own flow path reaches the coast within `STATION_REACH_KM` of it, which
    excludes everything draining to a different part of the coast. Distance is
    measured from the *outlet* rather than the cell, because what decides which
    station lifts a cell's water is where that water reaches the sea, not where
    it fell.

    Second, sizing — each station takes the nearest eligible cells up to the
    area its installed capacity implies at the design intensity. Cells that are
    eligible but beyond that area stay unserved, because the station was never
    built to drain them. Stations are filled largest-design-area first so that
    where two compete for the same cells, the one with more capacity to justify
    gets them.
    """
    n = outlet.size
    catchment = np.full(n, -1, dtype=np.int16)
    if not stations:
        return catchment.reshape(sea.shape)

    flat_lon, flat_lat = lons.ravel(), lats.ravel()
    flat_sea = sea.ravel()
    scale = np.cos(np.deg2rad(centre_lat))
    km_per_deg = EARTH_RADIUS_M * np.pi / 180.0 / 1000.0

    def km_between(lon_a, lat_a, lon_b, lat_b):
        return km_per_deg * np.hypot((lon_a - lon_b) * scale, lat_a - lat_b)

    # Pass 1: eligibility, one distance test per distinct outlet rather than
    # per cell. eligible[i] is the set of cells whose outlet is in station i's
    # reach; a cell can be eligible for more than one station.
    eligible: list[list[int]] = [[] for _ in stations]
    owner: dict[int, list[int]] = {}
    for out in np.unique(outlet[outlet >= 0]):
        near = [
            i for i, st in enumerate(stations)
            if km_between(flat_lon[out], flat_lat[out], st.lon, st.lat) < STATION_REACH_KM
        ]
        owner[int(out)] = near

    for cell in range(n):
        if flat_sea[cell]:
            continue
        for i in owner.get(int(outlet[cell]), ()):
            eligible[i].append(cell)

    # Pass 2: sizing. Largest design area first.
    order = sorted(
        range(len(stations)),
        key=lambda i: design_service_cells(stations[i], cell_area_m2),
        reverse=True,
    )
    for i in order:
        station = stations[i]
        quota = design_service_cells(station, cell_area_m2)
        free = [c for c in eligible[i] if catchment[c] == -1]
        free.sort(
            key=lambda c: km_between(flat_lon[c], flat_lat[c], station.lon, station.lat)
        )
        for cell in free[:quota]:
            catchment[cell] = i

    catchment[flat_sea] = -1
    return catchment.reshape(sea.shape)


@lru_cache(maxsize=8)
def drainage_terrain(region_id: str = PRIMARY_REGION_ID) -> DrainageTerrain:
    """Full drainage structure for a region. Cached — terrain does not change."""
    elevation = static_layers(region_id)["elevation"].astype(np.float32)
    lons, lats = cell_centres(region_id)
    stations = stations_for(region_id)

    sea = sea_mask(elevation)
    filled = fill_depressions(elevation, sea)
    downstream = d8_downstream(filled, sea)
    outlet = trace_outlets(downstream, sea)
    accumulation = flow_accumulation(downstream, sea).reshape(elevation.shape)
    area = cell_area_m2(region_id)
    catchment = _assign_catchments(
        outlet, sea, stations, lons, lats,
        get_region(region_id).geometry.centre[1], area,
    )

    return DrainageTerrain(
        region_id=region_id,
        sea=sea,
        elevation=elevation,
        filled=filled,
        fill_depth=(filled - elevation).astype(np.float32),
        downstream=downstream,
        accumulation=accumulation.astype(np.float32),
        outlet=outlet,
        catchment=catchment,
        stations=stations,
        cell_area_m2=area,
    )
