"""Live weather ingestion from Open-Meteo.

Open-Meteo is keyless and serves the same GFS/ICON/best-match fields Stage 0
pulled, so live analysis inputs stay consistent with the training feeds. One
request covers the whole mesh; the response is splined onto the 1 km grid.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import requests

from rainshield.config import LEAD_TIMES, SETTINGS
from rainshield.ingest.base import LiveObservation
from rainshield.ingest.mesh import interpolate_mesh, mesh_query_pairs

ENDPOINT = "https://api.open-meteo.com/v1/forecast"

HOURLY_FIELDS = ("precipitation", "soil_moisture_0_to_7cm", "cloud_cover")


class OpenMeteoProvider:
    """Fetches the dynamic channels from Open-Meteo's forecast endpoint."""

    name = "openmeteo"

    def __init__(self, timeout: float | None = None, mesh_size: int | None = None):
        self.timeout = timeout or SETTINGS.http_timeout
        self.mesh_size = mesh_size or SETTINGS.mesh_size

    # -- request ----------------------------------------------------------

    def _request(self) -> list[dict]:
        lats, lons = mesh_query_pairs(self.mesh_size)
        params = {
            "latitude": ",".join(f"{v:.4f}" for v in lats),
            "longitude": ",".join(f"{v:.4f}" for v in lons),
            "hourly": ",".join(HOURLY_FIELDS),
            "past_days": 1,
            "forecast_days": 2,
            "timezone": "UTC",
            "models": "best_match",
        }
        response = requests.get(ENDPOINT, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        # A single coordinate returns an object; a mesh returns a list.
        locations = payload if isinstance(payload, list) else [payload]
        if len(locations) != len(lats):
            raise ValueError(
                f"Open-Meteo returned {len(locations)} locations, expected {len(lats)}"
            )
        return locations

    # -- parsing ----------------------------------------------------------

    @staticmethod
    def _series(location: dict, field: str) -> np.ndarray:
        values = location.get("hourly", {}).get(field)
        if not values:
            raise ValueError(f"Open-Meteo response is missing hourly.{field}")
        return np.array([0.0 if v is None else float(v) for v in values], dtype=np.float64)

    @staticmethod
    def _now_index(location: dict, now: datetime) -> int:
        """Index of the hour containing `now` in the hourly time axis."""
        times = location.get("hourly", {}).get("time") or []
        if not times:
            raise ValueError("Open-Meteo response is missing hourly.time")
        stamps = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in times]
        for i, stamp in enumerate(stamps):
            if stamp > now:
                return max(0, i - 1)
        return len(stamps) - 1

    def fetch(self) -> LiveObservation:
        now = datetime.now(timezone.utc)
        locations = self._request()

        precip = np.stack([self._series(loc, "precipitation") for loc in locations])
        soil = np.stack([self._series(loc, "soil_moisture_0_to_7cm") for loc in locations])
        cloud = np.stack([self._series(loc, "cloud_cover") for loc in locations])
        idx = self._now_index(locations[0], now)
        n_hours = precip.shape[1]

        def at(offset_minutes: int, series: np.ndarray) -> np.ndarray:
            """Linearly interpolate the hourly series `offset` minutes ahead."""
            pos = idx + offset_minutes / 60.0
            lo = int(np.floor(pos))
            hi = min(lo + 1, n_hours - 1)
            lo = min(max(lo, 0), n_hours - 1)
            frac = pos - lo
            return series[:, lo] * (1 - frac) + series[:, hi] * frac

        def accum_3h(offset_minutes: int) -> np.ndarray:
            """Rain over the 3 hours ending `offset` minutes from now."""
            end = idx + offset_minutes / 60.0
            start = max(0.0, end - 3.0)
            lo, hi = int(np.floor(start)), int(np.ceil(end))
            lo = min(max(lo, 0), n_hours - 1)
            hi = min(max(hi, lo + 1), n_hours)
            return precip[:, lo:hi].sum(axis=1)

        rain_rate = {lead: interpolate_mesh(at(lead, precip), self.mesh_size) for lead in LEAD_TIMES}
        rain_3h = {lead: interpolate_mesh(accum_3h(lead), self.mesh_size) for lead in LEAD_TIMES}

        past_start = max(0, idx - 24)
        antecedent = precip[:, past_start : idx + 1].sum(axis=1)

        observation = LiveObservation(
            source=self.name,
            fetched_at=now,
            rain_rate={k: np.clip(v, 0.0, None) for k, v in rain_rate.items()},
            rain_3h={k: np.clip(v, 0.0, None) for k, v in rain_3h.items()},
            soil_moisture=np.clip(interpolate_mesh(at(0, soil), self.mesh_size), 0.0, 1.0),
            cloud_cover=np.clip(interpolate_mesh(at(0, cloud), self.mesh_size), 0.0, 100.0),
            antecedent_24h=np.clip(interpolate_mesh(antecedent, self.mesh_size), 0.0, None),
            degraded=False,
            notes=[f"Open-Meteo best_match, {len(locations)} mesh points, hour index {idx}"],
        )
        observation.validate()
        return observation
