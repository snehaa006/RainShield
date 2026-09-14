"""Live weather ingestion from Open-Meteo.

Open-Meteo is keyless and serves the same GFS/ICON/best-match fields Stage 0
pulled, so live analysis inputs stay consistent with the training feeds. One
request covers the whole mesh; the response is splined onto the 1 km grid.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import requests

from rainshield.config import SETTINGS
from rainshield.ingest.base import LiveObservation, assemble_observation
from rainshield.ingest.mesh import mesh_query_pairs

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

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status

    @property
    def is_variable_rejection(self) -> bool:
        """True when a narrower variable set could plausibly succeed.

        Only a 400 means "I will not serve that field". A 429 or a 5xx applies
        to the whole endpoint, so stepping down tiers just sends more requests
        to something that is already rate-limited or down.
        """
        return self.status == 400


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
            raise OpenMeteoError(
                f"HTTP {response.status_code} for [{','.join(fields)}]: {reason}",
                status=response.status_code,
            )

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
                # A rate limit or an outage applies to the endpoint, not to the
                # variables asked for — stepping down would only add load.
                if not exc.is_variable_rejection:
                    raise OpenMeteoError("; ".join(failures), status=exc.status) from exc
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

    def fetch(self) -> LiveObservation:
        now = datetime.now(timezone.utc)
        locations = self._request()

        times = [
            datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
            for t in locations[0].get("hourly", {}).get("time") or []
        ]
        if not times:
            raise ValueError("Open-Meteo response is missing hourly.time")

        notes = [f"Open-Meteo best_match, {len(locations)} mesh points"]
        if self.dropped:
            notes.append(f"upstream would not serve: {', '.join(self.dropped)} — substituted")

        return assemble_observation(
            source=self.name,
            now=now,
            times=times,
            precip=np.stack([self._series(loc, REQUIRED_FIELD) for loc in locations]),
            cloud=self._optional_series(locations, "cloud_cover"),
            soil=self._optional_series(locations, "soil_moisture_0_to_7cm"),
            mesh_size=self.mesh_size,
            notes=notes,
        )
