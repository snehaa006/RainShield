"""Turns susceptibility plus live rainfall into a flood hazard forecast.

The trained network supplies *where* water collects (terrain susceptibility);
the live feed supplies *whether it is raining hard enough to matter*. Combining
them is what makes the dashboard move with real weather — the network alone is
nearly static, because its training target was a topographic mask.

    flood probability = susceptibility x (1 - exp(-forcing / R0))

With no rain the response term is 0 and nothing floods, however low-lying the
cell; under sustained heavy rain it saturates toward the cell's susceptibility.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from rainshield.grid import static_layers

#: Effective 3 hr rainfall at which the hazard response reaches 1 - 1/e.
#: Anchored to the spec's 100 mm/3 hr trigger.
RAINFALL_SCALE_MM = 45.0

#: Depth normalisation — mm of effective rain producing ~1 m in a flat basin.
DEPTH_SCALE_MM = 95.0


@dataclass(frozen=True)
class WhatIf:
    """Operator overrides from the what-if simulator."""

    extra_rainfall: float = 0.0     # mm added across the grid
    soil_saturation: float = 1.0    # multiplier on antecedent wetness, 0.5-1.5
    drainage_capacity: float = 1.0  # fraction of design capacity, 0.3-1.2

    @property
    def drainage_deficit(self) -> float:
        return 1.0 / float(np.clip(self.drainage_capacity, 0.3, 1.2))

    def is_active(self) -> bool:
        return (
            self.extra_rainfall != 0.0
            or self.soil_saturation != 1.0
            or self.drainage_capacity != 1.0
        )


DEFAULT_WHAT_IF = WhatIf()


@dataclass
class HazardField:
    """Per-cell hazard at one lead time, every array (rows, cols)."""

    rainfall_intensity: np.ndarray  # mm/hr
    rainfall_3h: np.ndarray         # mm
    flood_probability: np.ndarray   # 0-1
    water_depth: np.ndarray         # m
    time_to_inundation: np.ndarray  # minutes; NaN where no inundation expected
    susceptibility: np.ndarray      # 0-1, straight from the model


def effective_rainfall(
    rain_3h: np.ndarray, soil_moisture: np.ndarray, what_if: WhatIf
) -> np.ndarray:
    """3 hr rainfall adjusted for antecedent wetness and drainage capacity.

    Wet ground and undersized drains both raise the runoff a given rainfall
    produces, so they scale the rain the hazard model sees.
    """
    wetness = 0.7 + 0.5 * np.clip(soil_moisture * what_if.soil_saturation, 0.0, 1.5)
    total = np.clip(rain_3h + what_if.extra_rainfall, 0.0, None)
    return total * wetness * what_if.drainage_deficit


def compute_hazard(
    susceptibility: np.ndarray,
    rain_rate: np.ndarray,
    rain_3h: np.ndarray,
    soil_moisture: np.ndarray,
    lead: int,
    what_if: WhatIf = DEFAULT_WHAT_IF,
) -> HazardField:
    """Combine the model's susceptibility with live rainfall forcing."""
    elevation = static_layers()["elevation"]

    forcing = effective_rainfall(rain_3h, soil_moisture, what_if)
    response = 1.0 - np.exp(-forcing / RAINFALL_SCALE_MM)
    probability = np.clip(susceptibility * response, 0.0, 1.0)

    # Low, flat ground ponds deeper for the same runoff volume.
    basin = 1.0 / (1.0 + np.clip(elevation, 0.0, None) / 4.0)
    depth = np.clip(
        probability * basin * (forcing / DEPTH_SCALE_MM) * 1.2, 0.0, 3.0
    )

    intensity = np.clip(rain_rate + what_if.extra_rainfall / 3.0, 0.0, None)

    # Onset shortens as probability and intensity rise; NaN marks "not expected".
    onset = 210.0 - 150.0 * probability - np.minimum(60.0, intensity * 0.5)
    tti = np.where(
        probability >= 0.35,
        np.maximum(10.0, np.round((lead + onset) / 5.0) * 5.0),
        np.nan,
    )

    return HazardField(
        rainfall_intensity=intensity.astype(np.float32),
        rainfall_3h=np.clip(rain_3h + what_if.extra_rainfall, 0.0, None).astype(np.float32),
        flood_probability=probability.astype(np.float32),
        water_depth=depth.astype(np.float32),
        time_to_inundation=tti.astype(np.float32),
        susceptibility=susceptibility.astype(np.float32),
    )


def confidence_for(lead: int, degraded: bool) -> str:
    """Ensemble confidence tag: decays with lead time, capped when degraded."""
    agreement = 0.92 - (lead / 360.0) * 0.30
    if degraded:
        agreement -= 0.25
    if agreement >= 0.75:
        return "HIGH"
    if agreement >= 0.58:
        return "MEDIUM"
    return "LOW"
