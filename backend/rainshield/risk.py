"""Composite risk scoring and ward roll-ups.

    Risk = 0.35 rainfall severity + 0.30 flood probability + 0.20 water depth
         + 0.10 population exposure + 0.05 critical-infrastructure proximity
"""

from __future__ import annotations

import numpy as np

from rainshield.config import RISK_NORMALISERS, RISK_WEIGHTS, TIER_THRESHOLDS
from rainshield.grid import infra_proximity, static_layers
from rainshield.hazard import HazardField
from rainshield.regions import PRIMARY_REGION_ID

TIER_ORDER = ("NORMAL", "WATCH", "WARNING", "CRITICAL")


def risk_components(
    hazard: HazardField, region_id: str = PRIMARY_REGION_ID
) -> dict[str, np.ndarray]:
    """The five 0-1 axes the composite score is built from."""
    static = static_layers(region_id)
    return {
        "rainfall_severity": np.clip(hazard.rainfall_3h / RISK_NORMALISERS["rainfall_3h"], 0, 1),
        "flood_probability": np.clip(hazard.flood_probability, 0, 1),
        "water_depth": np.clip(hazard.water_depth / RISK_NORMALISERS["water_depth"], 0, 1),
        "population_exposure": np.clip(
            static["population"] / RISK_NORMALISERS["population"], 0, 1
        ),
        "critical_infra": infra_proximity(region_id),
    }


def composite_risk(
    hazard: HazardField, region_id: str = PRIMARY_REGION_ID
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    components = risk_components(hazard, region_id)
    total = sum(components[key] * weight for key, weight in RISK_WEIGHTS.items())
    return np.clip(total, 0.0, 1.0).astype(np.float32), components


def tier_array(risk: np.ndarray) -> np.ndarray:
    """Warning tier per cell, as an array of strings."""
    out = np.full(risk.shape, "NORMAL", dtype=object)
    for tier, minimum in sorted(TIER_THRESHOLDS, key=lambda t: t[1]):
        out[risk >= minimum] = tier
    return out


def worst_tier(risk_values: np.ndarray) -> str:
    if risk_values.size == 0:
        return "NORMAL"
    return tier_array(np.array([float(np.max(risk_values))]))[0]


def population_at_risk(
    probability: np.ndarray, population: np.ndarray, threshold: float = 0.5
) -> int:
    """People in cells above the flood-probability threshold, expectation-weighted."""
    mask = probability >= threshold
    return int(np.round(float((population[mask] * probability[mask]).sum())))
