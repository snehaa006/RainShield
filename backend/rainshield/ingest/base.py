"""Shared types for the live-observation providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import numpy as np

from rainshield.config import LEAD_TIMES
from rainshield.regions import PRIMARY_REGION_ID, get_region


@dataclass
class LiveObservation:
    """One refresh of the dynamic state of the atmosphere over the grid.

    Every array is shaped (rows, cols) with row 0 on the NORTHERN edge, matching
    the GeoTIFF transform of the Stage 0 rasters.
    """

    source: str
    fetched_at: datetime
    #: mm/hr instantaneous rain rate, keyed by lead time in minutes.
    rain_rate: dict[int, np.ndarray]
    #: mm accumulated over the 3 hours ending at the lead time.
    rain_3h: dict[int, np.ndarray]
    #: Volumetric soil moisture 0-7 cm, m3/m3.
    soil_moisture: np.ndarray
    #: Total cloud cover, percent.
    cloud_cover: np.ndarray
    #: Rainfall over the previous 24 hours, mm.
    antecedent_24h: np.ndarray
    #: True when upstream data was unavailable and a fallback filled in.
    degraded: bool = False
    notes: list[str] = field(default_factory=list)
    #: Region this observation describes.
    region_id: str = PRIMARY_REGION_ID
    #: True when the whole field is generated rather than observed. Distinct
    #: from `degraded`, which means a real feed failed and something stood in:
    #: a simulated region has no real feed to lose.
    simulated: bool = False

    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.fetched_at).total_seconds()

    def validate(self) -> None:
        expected = get_region(self.region_id).geometry.shape
        for lead in LEAD_TIMES:
            if lead not in self.rain_rate or lead not in self.rain_3h:
                raise ValueError(f"observation is missing lead time {lead}")
            for arr in (self.rain_rate[lead], self.rain_3h[lead]):
                if arr.shape != expected:
                    raise ValueError(f"array shape {arr.shape}, expected {expected}")
        for arr in (self.soil_moisture, self.cloud_cover, self.antecedent_24h):
            if arr.shape != expected:
                raise ValueError(f"array shape {arr.shape}, expected {expected}")


class Provider(Protocol):
    """A source of live observations for the grid."""

    name: str

    def fetch(self) -> LiveObservation:
        ...


def marshall_palmer_dbz(rain_mm_hr: np.ndarray) -> np.ndarray:
    """Radar reflectivity (dBZ) from rain rate via Z = 200 R^1.6.

    Mirrors the conversion Stage 0 used to build the DWR layer, so live values
    carry the same physical meaning as the ones the model was trained on.
    """
    rate = np.clip(rain_mm_hr, 0.0, None)
    z = 200.0 * np.power(rate, 1.6, where=rate > 0.01, out=np.zeros_like(rate))
    return np.where(rate > 0.01, 10.0 * np.log10(np.maximum(z, 1e-9)), 0.0).astype(np.float32)


def brightness_temp_from_cloud(cloud_pct: np.ndarray) -> np.ndarray:
    """Effective IR brightness temperature (K) from cloud cover percent.

    The same clear-sky 298.15 K baseline and 0.65 K/% lapse Stage 0 applied to
    stand in for the INSAT-3D thermal channel.
    """
    return (298.15 - np.clip(cloud_pct, 0.0, 100.0) * 0.65).astype(np.float32)


def assemble_observation(
    *,
    source: str,
    now: datetime,
    times: list[datetime],
    precip: np.ndarray,
    mesh_size: int,
    cloud: np.ndarray | None = None,
    soil: np.ndarray | None = None,
    notes: list[str] | None = None,
    region_id: str = PRIMARY_REGION_ID,
) -> "LiveObservation":
    """Build an observation from per-mesh-point hourly series.

    Shared by every provider so they differ only in how they obtain the series,
    not in how lead times, accumulations and substitutions are derived.

    `precip`, `cloud` and `soil` are (n_mesh_points, n_hours); `times` is the
    hourly axis. Only precipitation is required — the rest are substituted when
    a provider cannot supply them.
    """
    from rainshield.ingest.mesh import interpolate_mesh

    # Index of the hour containing `now`.
    idx = len(times) - 1
    for i, stamp in enumerate(times):
        if stamp > now:
            idx = max(0, i - 1)
            break

    n_hours = precip.shape[1]
    notes = list(notes or [])

    def at(offset_minutes: int, series: np.ndarray) -> np.ndarray:
        pos = idx + offset_minutes / 60.0
        lo = min(max(int(np.floor(pos)), 0), n_hours - 1)
        hi = min(lo + 1, n_hours - 1)
        frac = pos - lo
        return series[:, lo] * (1 - frac) + series[:, hi] * frac

    def accum_3h(offset_minutes: int) -> np.ndarray:
        end = idx + offset_minutes / 60.0
        start = max(0.0, end - 3.0)
        lo = min(max(int(np.floor(start)), 0), n_hours - 1)
        hi = min(max(int(np.ceil(end)), lo + 1), n_hours)
        return precip[:, lo:hi].sum(axis=1)

    def spline(values: np.ndarray) -> np.ndarray:
        return interpolate_mesh(values, mesh_size, region_id=region_id)

    rain_rate = {lead: spline(at(lead, precip)) for lead in LEAD_TIMES}
    rain_3h = {lead: spline(accum_3h(lead)) for lead in LEAD_TIMES}

    antecedent = np.clip(spline(precip[:, max(0, idx - 24) : idx + 1].sum(axis=1)), 0.0, None)

    # Ground wets with the rain that has already fallen: a stand-in when the
    # upstream serves no soil moisture. 60 mm over 24 hr saturates the top layer.
    if soil is None:
        soil_grid = np.clip(0.22 + antecedent / 60.0, 0.0, 1.0)
    else:
        soil_grid = np.clip(spline(at(0, soil)), 0.0, 1.0)

    # Cloud cover only feeds the brightness-temperature channel, which the
    # network is barely sensitive to; overcast is the safe default in a storm.
    cloud_grid = (
        np.full_like(antecedent, 70.0)
        if cloud is None
        else np.clip(spline(at(0, cloud)), 0.0, 100.0)
    )

    observation = LiveObservation(
        source=source,
        fetched_at=now,
        rain_rate={k: np.clip(v, 0.0, None) for k, v in rain_rate.items()},
        rain_3h={k: np.clip(v, 0.0, None) for k, v in rain_3h.items()},
        soil_moisture=soil_grid,
        cloud_cover=cloud_grid,
        antecedent_24h=antecedent,
        degraded=False,
        notes=notes,
        region_id=region_id,
    )
    observation.validate()
    return observation
