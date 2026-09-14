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

#: Only precipitation is required. Soil moisture is not served for every model
#: or location — asking for an unsupported variable fails the WHOLE request, so
#: the extras are dropped one tier at a time rather than losing the rain field
#: with them. Stage 0 only ever requested precipitation and cloud cover.
FIELD_TIERS: tuple[tuple[str, ...], ...] = (
    ("precipitation", "soil_moisture_0_to_7cm", "cloud_cover"),
    ("precipitation", "cloud_cover"),
    ("precipitation",),
)

REQUIRED_FIELD = "precipitation"


class OpenMeteoError(RuntimeError):
    """An Open-Meteo request that failed, carrying the upstream explanation."""


class OpenMeteoProvider:
    """Fetches the dynamic channels from Open-Meteo's forecast endpoint."""

    name = "openmeteo"

    def __init__(self, timeout: float | None = None, mesh_size: int | None = None):
        self.timeout = timeout or SETTINGS.http_timeout
        self.mesh_size = mesh_size or SETTINGS.mesh_size
        #: Optional variables the upstream refused on the last fetch.
        self.dropped: list[str] = []

    # -- request ----------------------------------------------------------

    def _request_fields(self, fields: tuple[str, ...]) -> list[dict]:
        """One request for a given variable set, or raise with the reason why."""
        lats, lons = mesh_query_pairs(self.mesh_size)
        params = {
            "latitude": ",".join(f"{v:.4f}" for v in lats),
            "longitude": ",".join(f"{v:.4f}" for v in lons),
            "hourly": ",".join(fields),
            "past_days": 1,
            "forecast_days": 2,
            "timezone": "UTC",
            "models": "best_match",
        }
        response = requests.get(ENDPOINT, params=params, timeout=self.timeout)

        if not response.ok:
            # Open-Meteo explains rejections in {"error": true, "reason": "..."}.
            # Without this the caller only sees "HTTPError", which is useless on
            # a host you cannot reach to reproduce the call.
            reason = ""
            try:
                body = response.json()
                if isinstance(body, dict):
                    reason = str(body.get("reason") or body)
            except ValueError:
                reason = response.text[:300]
            raise OpenMeteoError(f"HTTP {response.status_code} for [{','.join(fields)}]: {reason}")

        payload = response.json()
        # A single coordinate returns an object; a mesh returns a list.
        locations = payload if isinstance(payload, list) else [payload]
        if len(locations) != len(lats):
            raise ValueError(
                f"Open-Meteo returned {len(locations)} locations, expected {len(lats)}"
            )
        return locations

    def _request(self) -> list[dict]:
        """Fetch the richest variable set the upstream will serve.

        Returns the locations; `self.dropped` records what had to be given up so
        the UI can say the observation is thinner than usual.
        """
        self.dropped = []
        failures: list[str] = []

        for fields in FIELD_TIERS:
            try:
                locations = self._request_fields(fields)
            except OpenMeteoError as exc:
                failures.append(str(exc))
                continue
            self.dropped = [f for f in FIELD_TIERS[0] if f not in fields]
            return locations

        raise OpenMeteoError("; ".join(failures))

    # -- parsing ----------------------------------------------------------

    @staticmethod
    def _series(location: dict, field: str) -> np.ndarray:
        values = location.get("hourly", {}).get(field)
        if not values:
            raise ValueError(f"Open-Meteo response is missing hourly.{field}")
        return np.array([0.0 if v is None else float(v) for v in values], dtype=np.float64)

    @staticmethod
    def _optional_series(locations: list[dict], field: str) -> np.ndarray | None:
        """Stack an optional variable, or None when the tier that served it was dropped."""
        try:
            return np.stack([OpenMeteoProvider._series(loc, field) for loc in locations])
        except ValueError:
            return None

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

        precip = np.stack([self._series(loc, REQUIRED_FIELD) for loc in locations])
        soil = self._optional_series(locations, "soil_moisture_0_to_7cm")
        cloud = self._optional_series(locations, "cloud_cover")
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
        antecedent_grid = np.clip(interpolate_mesh(antecedent, self.mesh_size), 0.0, None)

        # Ground wets with the rain that has already fallen: a reasonable stand-in
        # when the upstream will not serve soil moisture. 60 mm over 24 hr takes
        # the top layer to saturation.
        if soil is None:
            soil_grid = np.clip(0.22 + antecedent_grid / 60.0, 0.0, 1.0)
        else:
            soil_grid = np.clip(interpolate_mesh(at(0, soil), self.mesh_size), 0.0, 1.0)

        # Cloud cover only feeds the brightness-temperature channel, which the
        # network is barely sensitive to; overcast is the safe default in a storm.
        if cloud is None:
            cloud_grid = np.full_like(antecedent_grid, 70.0)
        else:
            cloud_grid = np.clip(interpolate_mesh(at(0, cloud), self.mesh_size), 0.0, 100.0)

        notes = [f"Open-Meteo best_match, {len(locations)} mesh points, hour index {idx}"]
        if self.dropped:
            notes.append(f"upstream would not serve: {', '.join(self.dropped)} — substituted")

        observation = LiveObservation(
            source=self.name,
            fetched_at=now,
            rain_rate={k: np.clip(v, 0.0, None) for k, v in rain_rate.items()},
            rain_3h={k: np.clip(v, 0.0, None) for k, v in rain_3h.items()},
            soil_moisture=soil_grid,
            cloud_cover=cloud_grid,
            antecedent_24h=antecedent_grid,
            degraded=False,
            notes=notes,
        )
        observation.validate()
        return observation
