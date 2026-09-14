"""Shared types for the live-observation providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import numpy as np

from rainshield.config import LEAD_TIMES, REGION


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

    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.fetched_at).total_seconds()

    def validate(self) -> None:
        expected = REGION.shape
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
