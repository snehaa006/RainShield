"""Grid geometry and the static terrain / exposure layers.

Every accessor takes a region id and is cached per region. The primary region's
static channels (elevation, slope, infrastructure, population) are read straight
out of the Stage 1 tensor rather than re-opening the GeoTIFFs, which keeps
rasterio and GDAL out of the serving image entirely. A simulated region supplies
the same four channels procedurally — see rainshield.regions.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from rainshield.config import CHANNEL_INDEX, SETTINGS, STATIC_CHANNELS
from rainshield.regions import (
    PRIMARY_REGION_ID,
    MUMBAI_WARDS,
    Ward,
    get_region,
    simulated_static_layers,
)

#: Kept as a module-level name so existing imports of the Mumbai ward table
#: keep working; per-region wards come from `wards_for`.
WARDS: tuple[Ward, ...] = MUMBAI_WARDS

WARD_BY_ID = {w.id: w for w in WARDS}


def wards_for(region_id: str = PRIMARY_REGION_ID) -> tuple[Ward, ...]:
    return get_region(region_id).wards


@lru_cache(maxsize=8)
def cell_centres(region_id: str = PRIMARY_REGION_ID) -> tuple[np.ndarray, np.ndarray]:
    """(lons, lats) of every cell centre, each shaped (rows, cols).

    Row 0 is the northern edge, matching the GeoTIFF transform.
    """
    region = get_region(region_id).geometry
    cols = np.arange(region.cols)
    rows = np.arange(region.rows)
    lons = region.west + (cols + 0.5) * region.cell_width
    lats = region.north - (rows + 0.5) * region.cell_height
    return np.meshgrid(lons, lats)


def cell_polygon(row: int, col: int, region_id: str = PRIMARY_REGION_ID) -> list[list[float]]:
    """Cell footprint as a closed GeoJSON ring, [lon, lat] pairs."""
    region = get_region(region_id).geometry
    x0 = region.west + col * region.cell_width
    x1 = x0 + region.cell_width
    y1 = region.north - row * region.cell_height
    y0 = y1 - region.cell_height
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


@lru_cache(maxsize=8)
def ward_assignment(region_id: str = PRIMARY_REGION_ID) -> np.ndarray:
    """Index into the region's wards for each cell, shaped (rows, cols).

    Nearest-centroid assignment in degrees, with longitude scaled by
    cos(latitude) so the distance is close to true ground distance.
    """
    profile = get_region(region_id)
    region = profile.geometry
    lons, lats = cell_centres(region_id)
    scale = np.cos(np.deg2rad(region.centre[1]))
    best = np.full(region.shape, -1, dtype=np.int16)
    best_d = np.full(region.shape, np.inf)
    for i, ward in enumerate(profile.wards):
        d = np.hypot((lons - ward.lon) * scale, lats - ward.lat)
        closer = d < best_d
        best = np.where(closer, i, best)
        best_d = np.where(closer, d, best_d)
    return best


@lru_cache(maxsize=8)
def static_layers(region_id: str = PRIMARY_REGION_ID) -> dict[str, np.ndarray]:
    """Elevation, slope, infrastructure and population, each (rows, cols).

    For the live region these come from the Stage 1 tensor, so the values are
    bit-identical to what the model was trained on. A simulated region generates
    them in the same physical units instead.
    """
    profile = get_region(region_id)
    if profile.simulated:
        return dict(simulated_static_layers())

    if not SETTINGS.tensor_path.exists():
        raise FileNotFoundError(
            f"Stage 1 tensor not found at {SETTINGS.tensor_path}. "
            "Run backend/pipeline/stage1_build_tensor.py first."
        )
    with np.load(SETTINGS.tensor_path) as data:
        tensor = data["X_tensor"].astype(np.float32)
    expected = (len(CHANNEL_INDEX), *profile.geometry.shape)
    if tensor.shape != expected:
        raise ValueError(f"Stage 1 tensor has shape {tensor.shape}, expected {expected}")
    return {name: tensor[CHANNEL_INDEX[name]].copy() for name in STATIC_CHANNELS}


@lru_cache(maxsize=1)
def ground_truth() -> np.ndarray:
    """The Stage 0 inundation mask used as the training target, (rows, cols)."""
    with np.load(SETTINGS.tensor_path) as data:
        return data["Y_tensor"].astype(np.float32)


@lru_cache(maxsize=8)
def infra_proximity(region_id: str = PRIMARY_REGION_ID) -> np.ndarray:
    """Infrastructure density rescaled to a 0-1 proximity weight.

    The raw layer is a per-cell OSM feature count with a long tail, so it is
    squashed against its 95th percentile rather than its maximum.
    """
    infra = static_layers(region_id)["infrastructure"]
    ceiling = float(np.percentile(infra, 95)) or 1.0
    return np.clip(infra / ceiling, 0.0, 1.0).astype(np.float32)


def land_use(region_id: str = PRIMARY_REGION_ID) -> np.ndarray:
    """Coarse land-use class per cell, derived from elevation and built density.

    Stage 0 carries no LULC raster, so this is inferred for display only — it
    is never fed to the model.
    """
    layers = static_layers(region_id)
    elev, infra = layers["elevation"], infra_proximity(region_id)
    out = np.full(get_region(region_id).geometry.shape, "vegetation", dtype=object)
    out[infra > 0.12] = "periurban"
    out[infra > 0.35] = "urban"
    out[infra > 0.70] = "urban-dense"
    out[elev <= 0.5] = "water"
    return out
