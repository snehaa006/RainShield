"""Deterministic offline provider.

Used when RAINSHIELD_PROVIDER=synthetic, and as the automatic fallback when the
live feed is unreachable, so the dashboard degrades to a labelled demo field
rather than an error page. The field is seeded on the current hour, so it
drifts slowly and visibly instead of being frozen.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np

from rainshield.config import LEAD_TIMES
from rainshield.regions import PRIMARY_REGION_ID, get_region
from rainshield.ingest.base import LiveObservation


class SyntheticProvider:
    """A storm cell advecting north-east across the grid."""

    name = "synthetic"

    def __init__(self, intensity: float = 1.0, region_id: str = PRIMARY_REGION_ID):
        self.intensity = intensity
        self.region_id = region_id

    def fetch(self, reason: str | None = None) -> LiveObservation:
        now = datetime.now(timezone.utc)
        region = get_region(self.region_id).geometry
        # One slow cycle per 6 hours keeps the demo visibly moving.
        phase = ((now.hour * 60 + now.minute) % 360) / 360.0

        rows = np.arange(region.rows)[:, None] / region.rows
        cols = np.arange(region.cols)[None, :] / region.cols

        def field(lead: int) -> np.ndarray:
            hours = lead / 60.0
            cx = 0.35 + 0.05 * hours + 0.3 * phase
            cy = 0.60 - 0.04 * hours
            dist2 = (cols - cx) ** 2 + (rows - cy) ** 2
            core = np.exp(-dist2 / 0.045)
            lifecycle = math.exp(-(((hours - 1.8) / 2.4) ** 2))
            texture = 0.75 + 0.25 * np.sin(cols * 11 + hours) * np.cos(rows * 9 - hours)
            return np.clip(28.0 * self.intensity * core * lifecycle * texture, 0.0, 200.0)

        rain_rate = {lead: field(lead).astype(np.float32) for lead in LEAD_TIMES}
        rain_3h = {lead: (rain_rate[lead] * 2.2).astype(np.float32) for lead in LEAD_TIMES}
        base = rain_rate[0]

        notes = ["synthetic field — not live weather"]
        if reason:
            notes.append(reason)

        observation = LiveObservation(
            source=self.name,
            fetched_at=now,
            rain_rate=rain_rate,
            rain_3h=rain_3h,
            soil_moisture=np.clip(0.28 + base / 120.0, 0.0, 1.0).astype(np.float32),
            cloud_cover=np.clip(35.0 + base * 2.4, 0.0, 100.0).astype(np.float32),
            antecedent_24h=(base * 3.5).astype(np.float32),
            degraded=True,
            notes=notes,
            region_id=self.region_id,
            simulated=True,
        )
        observation.validate()
        return observation
