"""A scripted monsoon depression over the simulated region.

Why this exists
---------------
Mumbai is quiet most of the year. With a genuinely live feed the board sits at
Normal or Watch, which means the parts of the system that matter most — the
Warning and Critical tiers, ward escalation, time-to-inundation, the CAP alert
path — are never exercised in a demo. This provider drives a second region hard
enough to light all of them up.

Nothing here is a measurement. Every observation it produces carries
``simulated=True``, the region it belongs to is registered as ``kind="simulated"``
and the dashboard labels it. It is a flight simulator, not a forecast.

How it behaves
--------------
The storm is a pure function of wall-clock time, so every request computes the
same state and there is no drift between the API and a client that polls it.
A depression makes landfall from the sea on the eastern edge, tracks inland and
decays, on a cycle of ``RAINSHIELD_SIM_PERIOD`` minutes (default 90):

    phase 0.00   offshore, grid dry .......................... NORMAL
    phase 0.25   rainband reaches the coast .................. WATCH
    phase 0.45   landfall, peak intensity over the delta ..... CRITICAL
    phase 0.65   centre inland, coastal rain easing .......... WARNING
    phase 0.85   remnant rain, ground still saturated ........ WATCH

Antecedent rainfall and soil wetness accumulate across the cycle rather than
tracking the instantaneous rate, so the ground stays saturated behind the storm
and the hazard decays more slowly than the rainfall does — which is how real
flooding behaves.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import numpy as np

from rainshield.config import LEAD_TIMES
from rainshield.ingest.base import LiveObservation
from rainshield.regions import SIMULATED_REGION_ID, get_region

#: Minutes for one full landfall cycle. Long enough that the forecast horizon
#: (up to +6 hr) spans roughly one storm life rather than several, short enough
#: that a demo sees the whole arc without waiting all day.
DEFAULT_PERIOD_MINUTES = 180.0

#: Peak instantaneous rain rate at the storm core, mm/hr.
PEAK_RATE_MM_HR = 58.0

#: Peak 3 hr accumulation at the core, mm. Above the 100 mm/3 hr trigger the
#: risk model normalises against, so the core reaches the Critical tier.
PEAK_ACCUM_MM = 132.0


def period_minutes() -> float:
    try:
        value = float(os.getenv("RAINSHIELD_SIM_PERIOD", DEFAULT_PERIOD_MINUTES))
    except ValueError:
        return DEFAULT_PERIOD_MINUTES
    return value if value > 0 else DEFAULT_PERIOD_MINUTES


def phase_at(moment: datetime) -> float:
    """Position in the landfall cycle, 0-1, at a moment in wall-clock time.

    Wraps: over wall-clock time one depression follows another.
    """
    return (moment.timestamp() / 60.0 % period_minutes()) / period_minutes()


def projected_phase(moment: datetime, lead_minutes: float) -> float:
    """Where the *current* storm will be after a lead time, 0-1.

    Clamped rather than wrapped, which is the difference between a forecast and
    a loop. A nowcast projects the system that exists now forward through the
    rest of its life; it does not predict the next one. Wrapping here made the
    +3 hr and +6 hr panels show exactly what "now" showed, because those leads
    are whole multiples of the cycle — a forecast that repeats itself is worse
    than one that simply says the storm will have passed.
    """
    return min(1.0, phase_at(moment) + lead_minutes / period_minutes())


def _envelope(phase: float) -> float:
    """Storm intensity over the cycle, 0-1, peaking shortly after landfall."""
    return float(np.exp(-(((phase - 0.46) / 0.27) ** 2)))


def phase_label(phase: float) -> str:
    """Plain description of where the storm is, for the feed log and the UI."""
    if phase < 0.18:
        return "offshore — grid dry"
    if phase < 0.34:
        return "rainband reaching the coast"
    if phase < 0.56:
        return "landfall — peak intensity over the delta"
    if phase < 0.74:
        return "centre tracking inland, coastal rain easing"
    if phase < 0.90:
        return "remnant rain, ground still saturated"
    return "storm cleared — ground draining"


class SimulatedStormProvider:
    """Generates the dynamic channels for the simulated region."""

    name = "simulated-storm"

    def __init__(self, region_id: str = SIMULATED_REGION_ID):
        self.region_id = region_id

    # -- fields -----------------------------------------------------------

    def _grid(self) -> tuple[np.ndarray, np.ndarray]:
        region = get_region(self.region_id).geometry
        north = np.arange(region.rows, dtype=np.float64)[:, None] / (region.rows - 1)
        east = np.arange(region.cols, dtype=np.float64)[None, :] / (region.cols - 1)
        return north, east

    def _rain_field(self, phase: float, peak: float) -> np.ndarray:
        """Rainfall over the grid with the storm at a given point in its cycle.

        The core tracks in from the sea on the eastern edge; a trailing rainband
        keeps the coast wet after the centre has moved inland.
        """
        north, east = self._grid()

        # Centre track: offshore (east > 1) inland (east < 0), drifting north.
        cx = 1.18 - 1.34 * phase
        cy = 0.34 + 0.32 * phase
        intensity = peak * _envelope(phase)

        core = np.exp(-(((east - cx) / 0.30) ** 2 + ((north - cy) / 0.38) ** 2))

        # Trailing band along the coast, lagging the centre by a quarter cycle.
        band_phase = max(0.0, phase - 0.22)
        bx = 1.18 - 1.34 * band_phase
        band = 0.55 * np.exp(-(((east - bx) / 0.18) ** 2)) * _envelope(band_phase)

        # Orographic enhancement where the ground rises inland.
        relief = 1.0 + 0.22 * (1.0 - east)

        texture = 0.88 + 0.12 * np.sin(north * 17.0 + phase * 6.3) * np.cos(east * 13.0)

        return np.clip(intensity * (core + band) * relief * texture, 0.0, None)

    def _accumulated(self, phase: float) -> float:
        """How much of the cycle's rain has already fallen, 0-1.

        Integrates the intensity envelope from the start of the cycle, so
        antecedent wetness lags the storm instead of tracking it.
        """
        steps = np.linspace(0.0, phase, 40) if phase > 0 else np.array([0.0])
        return float(np.trapezoid([_envelope(p) for p in steps], steps)) if phase > 0 else 0.0

    # -- provider ---------------------------------------------------------

    def fetch(self, now: datetime | None = None) -> LiveObservation:
        now = now or datetime.now(timezone.utc)
        phase = phase_at(now)

        rain_rate = {
            lead: self._rain_field(projected_phase(now, lead), PEAK_RATE_MM_HR).astype(np.float32)
            for lead in LEAD_TIMES
        }
        rain_3h = {
            lead: self._rain_field(projected_phase(now, lead), PEAK_ACCUM_MM).astype(np.float32)
            for lead in LEAD_TIMES
        }

        # The 24 hr antecedent is the cycle's rain so far, scaled so a full
        # landfall leaves the ground thoroughly wet.
        soaked = self._accumulated(phase)
        base = rain_rate[0]
        antecedent = np.clip(
            118.0 * soaked * (0.45 + 0.55 * base / max(float(base.max()), 1e-6)), 0.0, None
        ).astype(np.float32)

        # Volumetric soil moisture saturates towards ~0.52 m3/m3 for this soil.
        soil = np.clip(0.24 + 0.30 * soaked + antecedent / 900.0, 0.0, 0.52).astype(np.float32)

        cloud = np.clip(28.0 + 78.0 * _envelope(phase) + base * 1.6, 0.0, 100.0).astype(np.float32)

        observation = LiveObservation(
            source=self.name,
            fetched_at=now,
            rain_rate=rain_rate,
            rain_3h=rain_3h,
            soil_moisture=soil,
            cloud_cover=cloud,
            antecedent_24h=antecedent,
            degraded=False,   # nothing failed — this region has no live upstream
            simulated=True,
            region_id=self.region_id,
            notes=[
                "SIMULATED region — generated storm, not an observation",
                f"landfall cycle {phase * 100:.0f}% — {phase_label(phase)}",
                f"cycle period {period_minutes():.0f} min",
            ],
        )
        observation.validate()
        return observation
