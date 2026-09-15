"""Coarse-mesh sampling and interpolation onto the 1 km grid.

Upstream NWP is 11-25 km native, so the grid is driven by a small mesh of
sample points that is splined up to 45 x 39 — the approach Stage 0 used, with
the latitude orientation corrected.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import RectBivariateSpline

from rainshield.config import SETTINGS
from rainshield.regions import PRIMARY_REGION_ID, get_region


def mesh_coordinates(
    size: int | None = None, region_id: str = PRIMARY_REGION_ID
) -> tuple[np.ndarray, np.ndarray]:
    """Ascending sample latitudes and longitudes for the request mesh."""
    n = size or SETTINGS.mesh_size
    region = get_region(region_id).geometry
    lats = np.linspace(region.south, region.north, n)
    lons = np.linspace(region.west, region.east, n)
    return lats, lons


def mesh_query_pairs(
    size: int | None = None, region_id: str = PRIMARY_REGION_ID
) -> tuple[list[float], list[float]]:
    """Flattened (lat, lon) pairs in row-major order over the mesh.

    The flattening order matches :func:`interpolate_mesh`, which reshapes the
    upstream response back to (n_lats, n_lons).
    """
    lats, lons = mesh_coordinates(size, region_id)
    qlat: list[float] = []
    qlon: list[float] = []
    for lat in lats:
        for lon in lons:
            qlat.append(float(lat))
            qlon.append(float(lon))
    return qlat, qlon


def interpolate_mesh(
    values: np.ndarray, size: int | None = None, region_id: str = PRIMARY_REGION_ID
) -> np.ndarray:
    """Spline a coarse (n, n) mesh onto the (rows, cols) grid.

    Returns an array whose row 0 is the NORTHERN edge. Stage 0 evaluated the
    spline over ascending latitudes and wrote the result straight into a
    north-up raster, which flipped those layers; the explicit flip here is what
    fixes that.
    """
    lats, lons = mesh_coordinates(size, region_id)
    grid = np.asarray(values, dtype=np.float64).reshape(len(lats), len(lons))

    # Spline degree must be < the number of samples along each axis.
    k = min(3, len(lats) - 1, len(lons) - 1)
    spline = RectBivariateSpline(lats, lons, grid, kx=k, ky=k)

    region = get_region(region_id).geometry
    out_lats = np.linspace(region.south, region.north, region.rows)  # ascending
    out_lons = np.linspace(region.west, region.east, region.cols)
    south_up = spline(out_lats, out_lons)

    # Flip so row 0 is north, matching the Stage 0 GeoTIFF transform.
    return np.flipud(south_up).astype(np.float32)
