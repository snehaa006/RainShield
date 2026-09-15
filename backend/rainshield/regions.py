"""The regions the service can score, and where each one's data comes from.

RainShield was built around a single 1 km grid over Mumbai Suburban, with its
static terrain and exposure layers read from the Stage 1 tensor. This module
generalises that into a registry so a second region can be served alongside it.

Two kinds of region exist, and the difference is never hidden:

* ``live`` — real terrain from the Stage 0/1 pipeline, real weather from the
  upstream providers. Mumbai Suburban is the only one today.
* ``simulated`` — procedurally generated terrain driven by a scripted storm.
  Every payload for such a region carries ``simulated: true`` and the dashboard
  labels it, because none of it is a measurement of anywhere.

The simulated region exists because Mumbai is usually quiet: without a live
storm there is nothing on the board above Watch, and the warning path, the CAP
alerts and the ward escalation never get exercised. A region that reliably
climbs into Warning and Critical makes those visible without ever dressing
invented numbers up as an observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from rainshield.config import REGION as PRIMARY_GEOMETRY, Region

#: IANA zone used to render timestamps for a region.
DEFAULT_TIMEZONE = "Asia/Kolkata"


@dataclass(frozen=True)
class Ward:
    """An administrative unit operators actually act on."""

    id: str
    name: str
    lon: float
    lat: float


#: Mumbai municipal wards and the neighbouring municipal areas the grid covers.
#: Centroids are approximate administrative centres; cells are assigned to the
#: nearest one, giving a Voronoi partition of the 45 x 39 grid.
MUMBAI_WARDS: tuple[Ward, ...] = (
    Ward("w-kw", "K/West — Andheri West", 72.834, 19.136),
    Ward("w-ke", "K/East — Andheri East", 72.869, 19.119),
    Ward("w-ps", "P/South — Goregaon", 72.849, 19.164),
    Ward("w-pn", "P/North — Malad", 72.848, 19.187),
    Ward("w-rs", "R/South — Kandivali", 72.851, 19.207),
    Ward("w-rc", "R/Central — Borivali", 72.857, 19.229),
    Ward("w-hw", "H/West — Bandra West", 72.827, 19.055),
    Ward("w-he", "H/East — Santacruz East", 72.851, 19.081),
    Ward("w-l", "L — Kurla", 72.883, 19.078),
    Ward("w-n", "N — Ghatkopar", 72.911, 19.094),
    Ward("w-mw", "M/West — Chembur", 72.897, 19.048),
    Ward("w-me", "M/East — Govandi", 72.928, 19.058),
    Ward("w-s", "S — Bhandup / Powai", 72.925, 19.151),
    Ward("w-t", "T — Mulund", 72.956, 19.174),
    Ward("w-fn", "F/North — Sion / Matunga", 72.862, 19.027),
    Ward("w-gn", "G/North — Dadar / Dharavi", 72.843, 19.002),
    Ward("w-thane", "Thane City", 72.980, 19.218),
    Ward("w-nm", "Navi Mumbai — Vashi", 73.005, 19.077),
    Ward("w-nma", "Navi Mumbai — Airoli", 73.015, 19.155),
    Ward("w-panvel", "Kalyan–Dombivli fringe", 73.070, 19.215),
)


# --------------------------------------------------------------------------
# The simulated region
# --------------------------------------------------------------------------

#: A coastal delta on the Coromandel coast, shaped like Chennai's flood basins:
#: a flat, densely built coastal strip drained by two sluggish rivers, rising
#: inland to low hills. The same 45 x 39 / 1 km geometry as the primary grid, so
#: the trained network's input shape is unchanged.
SIMULATED_GEOMETRY = Region(
    name="Coromandel Delta (Simulated)",
    state="Tamil Nadu",
    west=80.000,
    south=12.820,
    east=80.3594,   # 39 cells x ~1 km at 13 N
    north=13.225,   # 45 cells x ~1 km
    rows=45,
    cols=39,
)

SIMULATED_WARDS: tuple[Ward, ...] = (
    Ward("s-hbr", "Harbour Front", 80.330, 12.900),
    Ward("s-mar", "Marina Quarter", 80.318, 12.975),
    Ward("s-est", "Estuary Town", 80.322, 13.050),
    Ward("s-npt", "North Port", 80.330, 13.140),
    Ward("s-fsh", "Fisher Colony", 80.336, 13.205),
    Ward("s-cbd", "Central Business", 80.245, 12.985),
    Ward("s-rvn", "Riverside North", 80.235, 13.110),
    Ward("s-rvs", "Riverside South", 80.240, 12.890),
    Ward("s-tnk", "Tank Bund", 80.180, 13.045),
    Ward("s-mil", "Mill District", 80.170, 12.935),
    Ward("s-lak", "Lakeside", 80.165, 13.170),
    Ward("s-ind", "Industrial Belt", 80.105, 12.960),
    Ward("s-rly", "Railway Junction", 80.100, 13.080),
    Ward("s-agr", "Agrarian West", 80.040, 13.010),
    Ward("s-hil", "Hill Fringe", 80.030, 13.180),
    Ward("s-sth", "Southern Approach", 80.045, 12.860),
)


@lru_cache(maxsize=1)
def simulated_static_layers() -> dict[str, np.ndarray]:
    """Procedurally generated terrain and exposure for the simulated region.

    Returns the same four static channels the Stage 1 tensor supplies, in the
    same physical units, so the trained network can be run over them unchanged:
    elevation (m), slope (degrees), infrastructure (OSM feature count per cell)
    and population (people per km2).

    The field is deterministic — the same grid every call, on every host — so
    the simulated region's risk map is reproducible and only the weather moves.
    """
    rows, cols = SIMULATED_GEOMETRY.shape
    # Row 0 is north. `north` runs 0 (north) -> 1 (south); `east` runs
    # 0 (inland/west) -> 1 (coast/east).
    north = np.arange(rows, dtype=np.float64)[:, None] / (rows - 1)
    east = np.arange(cols, dtype=np.float64)[None, :] / (cols - 1)

    # Land rises inland from a flat coastal plain: ~0.5 m at the shore to a
    # ~170 m hill fringe at the western edge, steepest in the north-west. The
    # coastal third stays almost level, which is where the flooding happens.
    inland = 1.0 - east
    elevation = 0.5 + 168.0 * inland**3.0 * (0.50 + 0.50 * (1.0 - north))

    # Two ridges in the hill fringe, so inland slope spans a realistic range
    # rather than the gentle wash a smooth ramp would give.
    for ridge_east, ridge_north, height in ((0.16, 0.30, 46.0), (0.24, 0.78, 34.0)):
        elevation += height * np.exp(
            -(((east - ridge_east) / 0.085) ** 2 + ((north - ridge_north) / 0.26) ** 2)
        )

    # Two rivers running west to east, incised a few metres into the plain.
    for course, depth in ((0.34, 4.5), (0.66, 3.8)):
        centre = course + 0.05 * np.sin(east * 5.2)
        elevation -= depth * np.exp(-(((north - centre) / 0.045) ** 2))

    # A tidal creek and a shallow tank basin, both classic ponding ground.
    elevation -= 3.2 * np.exp(-(((north - 0.50) / 0.08) ** 2 + ((east - 0.88) / 0.10) ** 2))
    elevation -= 2.4 * np.exp(-(((north - 0.22) / 0.07) ** 2 + ((east - 0.42) / 0.09) ** 2))

    # Fine texture so the terrain is not implausibly smooth. It grows with
    # elevation: hillsides are rough, the reclaimed coastal plain is not.
    roughness = 0.35 + 13.5 * np.clip(elevation / 90.0, 0.0, 1.0) ** 1.4
    texture = roughness * (
        0.62 * np.sin(north * 94.0) * np.cos(east * 81.0)
        + 0.38 * np.sin(north * 61.0 + 1.3) * np.cos(east * 133.0 - 0.7)
    )
    elevation = np.clip(elevation + texture, -1.5, None)

    # Slope from the elevation gradient, converted to degrees over 1 km cells.
    dy, dx = np.gradient(elevation, 1000.0, 1000.0)
    slope = np.degrees(np.arctan(np.hypot(dy, dx)))

    # Population: a dense core behind the harbour, a secondary inland centre,
    # thinning towards the agrarian west.
    def blob(n0: float, e0: float, sn: float, se: float) -> np.ndarray:
        return np.exp(-(((north - n0) / sn) ** 2 + ((east - e0) / se) ** 2))

    density = (
        1.00 * blob(0.52, 0.80, 0.20, 0.16)
        + 0.62 * blob(0.30, 0.62, 0.16, 0.15)
        + 0.45 * blob(0.74, 0.70, 0.15, 0.14)
        + 0.28 * blob(0.55, 0.40, 0.22, 0.18)
    )
    population = np.clip(48_000.0 * density + 900.0 * (1.0 - inland), 0.0, 62_000.0)
    # Nobody lives in the river channels themselves.
    population *= np.clip((elevation + 1.0) / 2.0, 0.0, 1.0)

    infrastructure = np.round(np.clip(96.0 * density**1.25, 0.0, 98.0))

    return {
        "elevation": elevation.astype(np.float32),
        "slope": slope.astype(np.float32),
        "infrastructure": infrastructure.astype(np.float32),
        "population": population.astype(np.float32),
    }


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RegionProfile:
    """One scoreable region: its geometry, its wards and its data provenance."""

    id: str
    geometry: Region
    wards: tuple[Ward, ...]
    timezone: str
    #: "live" — real terrain, real upstream weather.
    #: "simulated" — generated terrain, scripted storm. Never a measurement.
    kind: str
    blurb: str

    @property
    def name(self) -> str:
        return self.geometry.name

    @property
    def state(self) -> str:
        return self.geometry.state

    @property
    def simulated(self) -> bool:
        return self.kind == "simulated"


PRIMARY_REGION_ID = "mumbai"
SIMULATED_REGION_ID = "coromandel"

REGIONS: dict[str, RegionProfile] = {
    PRIMARY_REGION_ID: RegionProfile(
        id=PRIMARY_REGION_ID,
        geometry=PRIMARY_GEOMETRY,
        wards=MUMBAI_WARDS,
        timezone=DEFAULT_TIMEZONE,
        kind="live",
        blurb=(
            "Real 1 km terrain from the Stage 0 pipeline, scored against live "
            "Open-Meteo / MET Norway weather."
        ),
    ),
    SIMULATED_REGION_ID: RegionProfile(
        id=SIMULATED_REGION_ID,
        geometry=SIMULATED_GEOMETRY,
        wards=SIMULATED_WARDS,
        timezone=DEFAULT_TIMEZONE,
        kind="simulated",
        blurb=(
            "Generated terrain driven by a scripted monsoon depression. Not a "
            "real place and not a measurement — it exists to exercise the "
            "warning path when the live region is quiet."
        ),
    ),
}


def get_region(region_id: str | None = None) -> RegionProfile:
    """Look up a region profile, defaulting to the primary live region."""
    key = (region_id or PRIMARY_REGION_ID).strip().lower()
    if key not in REGIONS:
        raise ValueError(f"unknown region {key!r}; expected one of {sorted(REGIONS)}")
    return REGIONS[key]


def region_ids() -> list[str]:
    """Registry order: the live region first, simulated ones after it."""
    return sorted(REGIONS, key=lambda rid: (REGIONS[rid].simulated, rid))
