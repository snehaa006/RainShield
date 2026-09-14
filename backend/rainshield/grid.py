"""Grid geometry and the static terrain / exposure layers.

The static channels (elevation, slope, infrastructure, population) are read
straight out of the Stage 1 tensor rather than re-opening the GeoTIFFs, which
keeps rasterio and GDAL out of the serving image entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from rainshield.config import CHANNEL_INDEX, REGION, SETTINGS, STATIC_CHANNELS


@dataclass(frozen=True)
class Ward:
    """An administrative unit operators actually act on."""

    id: str
    name: str
    lon: float
    lat: float


#: Municipal wards and neighbouring municipal areas covering the analysis grid.
#: Centroids are approximate administrative centres; cells are assigned to the
#: nearest one, giving a Voronoi partition of the 45 x 39 grid.
WARDS: tuple[Ward, ...] = (
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

WARD_BY_ID = {w.id: w for w in WARDS}


@lru_cache(maxsize=1)
def cell_centres() -> tuple[np.ndarray, np.ndarray]:
    """(lons, lats) of every cell centre, each shaped (rows, cols).

    Row 0 is the northern edge, matching the GeoTIFF transform.
    """
    cols = np.arange(REGION.cols)
    rows = np.arange(REGION.rows)
    lons = REGION.west + (cols + 0.5) * REGION.cell_width
    lats = REGION.north - (rows + 0.5) * REGION.cell_height
    return np.meshgrid(lons, lats)


def cell_polygon(row: int, col: int) -> list[list[float]]:
    """Cell footprint as a closed GeoJSON ring, [lon, lat] pairs."""
    x0 = REGION.west + col * REGION.cell_width
    x1 = x0 + REGION.cell_width
    y1 = REGION.north - row * REGION.cell_height
    y0 = y1 - REGION.cell_height
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


@lru_cache(maxsize=1)
def ward_assignment() -> np.ndarray:
    """Index into WARDS for each cell, shaped (rows, cols).

    Nearest-centroid assignment in degrees, with longitude scaled by
    cos(latitude) so the distance is close to true ground distance.
    """
    lons, lats = cell_centres()
    scale = np.cos(np.deg2rad(REGION.centre[1]))
    best = np.full(REGION.shape, -1, dtype=np.int16)
    best_d = np.full(REGION.shape, np.inf)
    for i, ward in enumerate(WARDS):
        d = np.hypot((lons - ward.lon) * scale, lats - ward.lat)
        closer = d < best_d
        best = np.where(closer, i, best)
        best_d = np.where(closer, d, best_d)
    return best


@lru_cache(maxsize=1)
def static_layers() -> dict[str, np.ndarray]:
    """Elevation, slope, infrastructure and population, each (rows, cols).

    Sourced from the Stage 1 tensor so the values are bit-identical to what the
    model was trained on.
    """
    if not SETTINGS.tensor_path.exists():
        raise FileNotFoundError(
            f"Stage 1 tensor not found at {SETTINGS.tensor_path}. "
            "Run backend/pipeline/stage1_build_tensor.py first."
        )
    with np.load(SETTINGS.tensor_path) as data:
        tensor = data["X_tensor"].astype(np.float32)
    if tensor.shape != (len(CHANNEL_INDEX), *REGION.shape):
        raise ValueError(
            f"Stage 1 tensor has shape {tensor.shape}, expected "
            f"{(len(CHANNEL_INDEX), *REGION.shape)}"
        )
    return {name: tensor[CHANNEL_INDEX[name]].copy() for name in STATIC_CHANNELS}


@lru_cache(maxsize=1)
def ground_truth() -> np.ndarray:
    """The Stage 0 inundation mask used as the training target, (rows, cols)."""
    with np.load(SETTINGS.tensor_path) as data:
        return data["Y_tensor"].astype(np.float32)


@lru_cache(maxsize=1)
def infra_proximity() -> np.ndarray:
    """Infrastructure density rescaled to a 0-1 proximity weight.

    The raw layer is a per-cell OSM feature count with a long tail, so it is
    squashed against its 95th percentile rather than its maximum.
    """
    infra = static_layers()["infrastructure"]
    ceiling = float(np.percentile(infra, 95)) or 1.0
    return np.clip(infra / ceiling, 0.0, 1.0).astype(np.float32)


def land_use() -> np.ndarray:
    """Coarse land-use class per cell, derived from elevation and built density.

    Stage 0 carries no LULC raster, so this is inferred for display only — it
    is never fed to the model.
    """
    layers = static_layers()
    elev, infra = layers["elevation"], infra_proximity()
    out = np.full(REGION.shape, "vegetation", dtype=object)
    out[infra > 0.12] = "periurban"
    out[infra > 0.35] = "urban"
    out[infra > 0.70] = "urban-dense"
    out[elev <= 0.5] = "water"
    return out
