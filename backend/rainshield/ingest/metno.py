"""Fallback weather ingestion from MET Norway (api.met.no).

Open-Meteo's free tier is rate-limited **per IP**, and Render's outbound
addresses are shared across customers, so the quota can already be spent by
someone else before this service makes its first call — which is exactly what
happened on first deploy ("Daily API request limit exceeded"). MET Norway's
Locationforecast is keyless, has no per-IP daily cap, and is a genuinely
independent forecast, so it makes a real second source rather than a retry.

Two differences from Open-Meteo shape the code:

* One coordinate per request, so the mesh is coarser here (3 x 3 by default).
  At ~18 km spacing that still over-samples an 11-25 km native model.
* The series starts at the present, so there is no past rainfall. Antecedent
  accumulation is therefore unavailable and soil wetness falls back to the
  neutral substitution in `assemble_observation`.

MET Norway's terms require a descriptive User-Agent identifying the
application; set RAINSHIELD_USER_AGENT to include a contact address.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
import requests

from rainshield.config import SETTINGS
from rainshield.ingest.base import LiveObservation, assemble_observation
from rainshield.ingest.mesh import mesh_query_pairs

ENDPOINT = "https://api.met.no/weatherapi/locationforecast/2.0/compact"

DEFAULT_USER_AGENT = "RainShield/1.0 (flood early warning; https://github.com/snehaa006/RainShield)"

#: One HTTP request per point, so this mesh stays small.
DEFAULT_MESH = 3


class MetNoProvider:
    """Fetches precipitation and cloud cover from MET Norway Locationforecast."""

    name = "metno"

    def __init__(self, timeout: float | None = None, mesh_size: int | None = None):
        self.timeout = timeout or SETTINGS.http_timeout
        self.mesh_size = mesh_size or int(os.getenv("RAINSHIELD_METNO_MESH", DEFAULT_MESH))
        self.user_agent = os.getenv("RAINSHIELD_USER_AGENT", DEFAULT_USER_AGENT)

    def _request_point(self, lat: float, lon: float) -> dict:
        response = requests.get(
            ENDPOINT,
            params={"lat": f"{lat:.4f}", "lon": f"{lon:.4f}"},
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
            timeout=self.timeout,
        )
        if not response.ok:
            raise RuntimeError(
                f"met.no HTTP {response.status_code} for ({lat:.3f},{lon:.3f}): "
                f"{response.text[:200]}"
            )
        return response.json()

    def _parse_point(self, lat: float, lon: float) -> tuple[list[datetime], list[float], list[float]]:
        """Fetch and parse one mesh point. Safe to call from a worker thread."""
        return self._parse(self._request_point(lat, lon))

    @staticmethod
    def _parse(payload: dict) -> tuple[list[datetime], list[float], list[float]]:
        """Extract (times, hourly precipitation mm, cloud cover %) from one point.

        Entries beyond roughly three days carry `next_6_hours` instead of
        `next_1_hours`; those are dropped so the series stays hourly, which is
        what the lead-time interpolation assumes.
        """
        series = payload.get("properties", {}).get("timeseries") or []
        if not series:
            raise ValueError("met.no response has no timeseries")

        times: list[datetime] = []
        precip: list[float] = []
        cloud: list[float] = []

        for entry in series:
            details = entry.get("data", {}).get("next_1_hours", {}).get("details")
            if details is None or "precipitation_amount" not in details:
                continue
            stamp = datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
            times.append(stamp.astimezone(timezone.utc))
            precip.append(float(details["precipitation_amount"]))
            instant = entry.get("data", {}).get("instant", {}).get("details", {})
            cloud.append(float(instant.get("cloud_area_fraction", 70.0)))

        if not times:
            raise ValueError("met.no response carries no hourly precipitation")
        return times, precip, cloud

    def fetch(self) -> LiveObservation:
        now = datetime.now(timezone.utc)
        lats, lons = mesh_query_pairs(self.mesh_size)

        # One request per point, issued in parallel. Sequentially this was the
        # slowest thing in the system: a 3x3 mesh is nine round trips, so a
        # timing-out upstream cost nine whole timeouts back to back — minutes,
        # while the dashboard sat waiting. In parallel the chain costs one.
        with ThreadPoolExecutor(max_workers=min(len(lats), 12)) as pool:
            points = list(pool.map(self._parse_point, lats, lons))

        times: list[datetime] = []
        precip_rows: list[list[float]] = []
        cloud_rows: list[list[float]] = []

        for point_times, precip, cloud in points:
            if not times:
                times = point_times
            # Points can differ by an entry at the tail; clip to the shortest.
            length = min(len(times), len(precip))
            times = times[:length]
            precip_rows = [row[:length] for row in precip_rows]
            cloud_rows = [row[:length] for row in cloud_rows]
            precip_rows.append(precip[:length])
            cloud_rows.append(cloud[:length])

        return assemble_observation(
            source=self.name,
            now=now,
            times=times,
            precip=np.array(precip_rows, dtype=np.float64),
            cloud=np.array(cloud_rows, dtype=np.float64),
            soil=None,  # not served; substituted from antecedent rainfall
            mesh_size=self.mesh_size,
            notes=[
                f"MET Norway Locationforecast, {len(precip_rows)} mesh points",
                "forecast-only feed — no antecedent rainfall, soil wetness substituted",
            ],
        )
