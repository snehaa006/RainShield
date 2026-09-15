"""Central configuration for the RainShield serving backend.

Geometry, channel order and risk weights all live here so that re-pointing the
system at another district is a config change rather than a rewrite.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Spatial domain
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Region:
    """The 1 km analysis grid the model was trained on (Stage 0).

    18.85-19.25 N, 72.75-73.10 E at ~1 km, giving a 45 x 39 (rows x cols)
    raster of 1755 cells. Row 0 is the NORTH edge, matching the GeoTIFF
    convention used by every processed_data raster.
    """

    name: str
    state: str
    west: float
    south: float
    east: float
    north: float
    rows: int
    cols: int

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.west, self.south, self.east, self.north)

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.west + self.east) / 2, (self.south + self.north) / 2)

    @property
    def cell_width(self) -> float:
        return (self.east - self.west) / self.cols

    @property
    def cell_height(self) -> float:
        return (self.north - self.south) / self.rows

    @property
    def cell_count(self) -> int:
        return self.rows * self.cols

    @property
    def shape(self) -> tuple[int, int]:
        return (self.rows, self.cols)


REGION = Region(
    name="Mumbai Suburban",
    state="Maharashtra",
    # Exact bounds of processed_data/dem_1km_master.tif, so API cell polygons
    # line up with the rasters the model was trained on.
    west=72.74986111111112,
    south=18.845903888888888,
    east=73.10019811111111,
    north=19.250138888888888,
    rows=45,
    cols=39,
)


# --------------------------------------------------------------------------
# Model input channels
# --------------------------------------------------------------------------

#: The 10 aligned rasters stacked into the model input tensor, in the exact
#: order Stage 1 wrote them. Reordering breaks the trained weights.
CHANNELS: tuple[str, ...] = (
    "elevation",           # 0  SRTM DEM, m
    "slope",               # 1  terrain slope, degrees
    "infrastructure",      # 2  OSM feature count per cell
    "population",          # 3  WorldPop, people per km2
    "aws_rain",            # 4  IMD AWS gauge rainfall, mm
    "river_level",         # 5  CWC river overflow index, 0-1+
    "gpm_rain",            # 6  NASA GPM satellite rain rate, mm/hr
    "gfs_forecast",        # 7  NOAA GFS 3 hr accumulated forecast, mm
    "cloud_top_temp",      # 8  INSAT-3D brightness temperature, K
    "radar_reflectivity",  # 9  IMD DWR reflectivity, dBZ
)

N_CHANNELS = len(CHANNELS)
CHANNEL_INDEX = {name: i for i, name in enumerate(CHANNELS)}

#: Channels refreshed from live feeds on every inference. The rest are static
#: terrain/exposure layers read once from the Stage 1 tensor.
DYNAMIC_CHANNELS: tuple[str, ...] = (
    "aws_rain",
    "river_level",
    "gpm_rain",
    "gfs_forecast",
    "cloud_top_temp",
    "radar_reflectivity",
)

STATIC_CHANNELS: tuple[str, ...] = tuple(c for c in CHANNELS if c not in DYNAMIC_CHANNELS)


# --------------------------------------------------------------------------
# Forecast horizons
# --------------------------------------------------------------------------

#: Nowcast lead times in minutes; the API scores the grid at each.
LEAD_TIMES: tuple[int, ...] = (0, 30, 60, 120, 180, 360)


# --------------------------------------------------------------------------
# Risk scoring
# --------------------------------------------------------------------------

RISK_WEIGHTS: dict[str, float] = {
    "rainfall_severity": 0.35,
    "flood_probability": 0.30,
    "water_depth": 0.20,
    "population_exposure": 0.10,
    "critical_infra": 0.05,
}

#: Ceilings mapping raw output onto the 0-1 risk axes.
RISK_NORMALISERS: dict[str, float] = {
    "rainfall_3h": 100.0,    # mm/3hr — the spec's P(>100mm/3hr) trigger
    "water_depth": 1.5,      # m of standing water treated as full hazard
    "population": 40_000.0,  # people/km2 treated as maximum exposure
}

#: Lower bound of each warning tier on the 0-1 composite risk score.
TIER_THRESHOLDS: tuple[tuple[str, float], ...] = (
    ("CRITICAL", 0.75),
    ("WARNING", 0.50),
    ("WATCH", 0.25),
    ("NORMAL", 0.0),
)


def tier_for(risk: float) -> str:
    for tier, minimum in TIER_THRESHOLDS:
        if risk >= minimum:
            return tier
    return "NORMAL"


# --------------------------------------------------------------------------
# Runtime settings
# --------------------------------------------------------------------------


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Environment-driven runtime settings, read once at import."""

    processed_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("RAINSHIELD_PROCESSED_DIR", REPO_ROOT / "processed_data")
        )
    )
    weights_filename: str = field(
        default_factory=lambda: os.getenv(
            "RAINSHIELD_WEIGHTS", "rainshield_cnn_transformer.pth"
        )
    )
    tensor_filename: str = field(
        default_factory=lambda: os.getenv(
            "RAINSHIELD_TENSOR", "rainshield_stage1_tensor.npz"
        )
    )
    #: Live weather provider: "openmeteo" (real feeds) or "synthetic" (offline).
    provider: str = field(default_factory=lambda: os.getenv("RAINSHIELD_PROVIDER", "openmeteo"))
    #: Seconds an observation set stays valid before it is re-fetched.
    cache_ttl: int = field(default_factory=lambda: int(os.getenv("RAINSHIELD_CACHE_TTL", "600")))
    #: Coarse mesh sampled upstream, then splined onto the 1 km grid. Stage 0
    #: used 5x5; GFS/ICON are 11-25 km native so this already over-samples.
    mesh_size: int = field(default_factory=lambda: int(os.getenv("RAINSHIELD_MESH", "5")))
    #: Per-request upstream timeout. Both feeds answer in well under a second
    #: when healthy, so a long timeout only buys a longer wait on the days they
    #: are down — which are exactly the days the dashboard has to stay usable.
    http_timeout: float = field(
        default_factory=lambda: float(os.getenv("RAINSHIELD_HTTP_TIMEOUT", "10"))
    )
    #: How long a request will wait for an in-flight refresh before serving the
    #: last good observation instead. Fetching happens on a background thread;
    #: this only bounds how long a *caller* blocks on it.
    fetch_budget: float = field(
        default_factory=lambda: float(os.getenv("RAINSHIELD_FETCH_BUDGET", "12"))
    )
    cors_origins: str = field(default_factory=lambda: os.getenv("RAINSHIELD_CORS_ORIGINS", "*"))
    #: Skip the neural net entirely and use the analytical susceptibility model.
    force_analytical: bool = field(default_factory=lambda: _flag("RAINSHIELD_FORCE_ANALYTICAL"))

    @property
    def weights_path(self) -> Path:
        return self.processed_dir / self.weights_filename

    @property
    def tensor_path(self) -> Path:
        return self.processed_dir / self.tensor_filename

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


SETTINGS = Settings()
