"""Assembles the payloads the dashboard consumes.

Kept separate from the HTTP layer so the same logic backs both the API and the
offline `infer_realtime` CLI.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from rainshield.config import LEAD_TIMES, REGION, SETTINGS
from rainshield.grid import (
    WARDS,
    cell_centres,
    infra_proximity,
    land_use,
    static_layers,
    ward_assignment,
)
from rainshield.hazard import HazardField, WhatIf, compute_hazard, confidence_for
from rainshield.ingest import get_observation
from rainshield.ingest.base import LiveObservation
from rainshield.models.predictor import model_status, predict_susceptibility
from rainshield.risk import composite_risk, population_at_risk, worst_tier


def _round_list(arr: np.ndarray, digits: int) -> list[float]:
    return [round(float(v), digits) for v in np.asarray(arr).ravel()]


def _nullable_list(arr: np.ndarray, digits: int = 0) -> list[float | None]:
    flat = np.asarray(arr).ravel()
    return [None if np.isnan(v) else round(float(v), digits) for v in flat]


# --------------------------------------------------------------------------
# Static payload — fetched once by the client
# --------------------------------------------------------------------------


def region_payload() -> dict:
    static = static_layers()
    lons, lats = cell_centres()
    return {
        "region": {
            "name": REGION.name,
            "state": REGION.state,
            "bounds": list(REGION.bounds),
            "centre": list(REGION.centre),
            "rows": REGION.rows,
            "cols": REGION.cols,
            "cellCount": REGION.cell_count,
            "cellWidth": REGION.cell_width,
            "cellHeight": REGION.cell_height,
        },
        "leadTimes": list(LEAD_TIMES),
        "wards": [
            {"id": w.id, "name": w.name, "lon": w.lon, "lat": w.lat} for w in WARDS
        ],
        "cells": {
            "lon": _round_list(lons, 5),
            "lat": _round_list(lats, 5),
            "elevation": _round_list(static["elevation"], 1),
            "slope": _round_list(static["slope"], 2),
            "population": [int(round(float(v))) for v in static["population"].ravel()],
            "infraProximity": _round_list(infra_proximity(), 3),
            "landUse": [str(v) for v in land_use().ravel()],
            "wardIndex": [int(v) for v in ward_assignment().ravel()],
        },
    }


# --------------------------------------------------------------------------
# Forecast payload
# --------------------------------------------------------------------------


#: Susceptibility depends only on the observation and lead time, never on the
#: what-if sliders, so it is memoised across a single observation. Keeps slider
#: drags and the 6-lead trend chart off the network's critical path.
_SUSCEPTIBILITY_CACHE: dict[tuple[str, int], np.ndarray] = {}


def _susceptibility_for(observation: LiveObservation, lead: int) -> np.ndarray:
    key = (observation.fetched_at.isoformat(), lead)
    cached = _SUSCEPTIBILITY_CACHE.get(key)
    if cached is not None:
        return cached
    value = predict_susceptibility(observation, lead)
    if len(_SUSCEPTIBILITY_CACHE) > 4 * len(LEAD_TIMES):
        _SUSCEPTIBILITY_CACHE.clear()
    _SUSCEPTIBILITY_CACHE[key] = value
    return value


def _hazard_for(observation: LiveObservation, lead: int, what_if: WhatIf) -> HazardField:
    susceptibility = _susceptibility_for(observation, lead)
    return compute_hazard(
        susceptibility,
        observation.rain_rate[lead],
        observation.rain_3h[lead],
        observation.soil_moisture,
        lead,
        what_if,
    )


def _summary(hazard: HazardField, risk: np.ndarray) -> dict:
    population = static_layers()["population"]
    tti = hazard.time_to_inundation
    finite = tti[np.isfinite(tti)]
    return {
        "tier": worst_tier(risk),
        "peakRisk": round(float(risk.max()), 4),
        "meanRisk": round(float(risk.mean()), 4),
        "peakRainfall": round(float(hazard.rainfall_intensity.max()), 2),
        "meanRainfall": round(float(hazard.rainfall_intensity.mean()), 2),
        "peakRainfall3h": round(float(hazard.rainfall_3h.max()), 2),
        "peakFloodProbability": round(float(hazard.flood_probability.max()), 4),
        "peakDepth": round(float(hazard.water_depth.max()), 3),
        "populationAtRisk": population_at_risk(hazard.flood_probability, population),
        "floodedArea": int((hazard.flood_probability >= 0.5).sum()),
        "leadTime": None if finite.size == 0 else int(finite.min()),
    }


def _ward_summaries(hazard: HazardField, risk: np.ndarray, confidence: str) -> list[dict]:
    assignment = ward_assignment().ravel()
    population = static_layers()["population"].ravel()
    risk_flat = risk.ravel()
    prob = hazard.flood_probability.ravel()
    depth = hazard.water_depth.ravel()
    tti = hazard.time_to_inundation.ravel()

    out: list[dict] = []
    for index, ward in enumerate(WARDS):
        mask = assignment == index
        if not mask.any():
            continue
        cell_risk = risk_flat[mask]
        cell_prob = prob[mask]
        # A ward leans on its worst cells: one flooded pocket still matters.
        score = 0.6 * float(cell_risk.max()) + 0.4 * float(cell_risk.mean())
        times = tti[mask][np.isfinite(tti[mask])]
        flooded = cell_prob >= 0.5
        out.append(
            {
                "id": ward.id,
                "name": ward.name,
                "tier": worst_tier(np.array([score])),
                "risk": round(score, 4),
                "peakFloodProbability": round(float(cell_prob.max()), 4),
                "peakWaterDepth": round(float(depth[mask].max()), 3),
                "timeToInundation": None if times.size == 0 else int(times.min()),
                "confidence": confidence,
                "populationAtRisk": int(
                    round(float((population[mask][flooded] * cell_prob[flooded]).sum()))
                ),
                "cellCount": int(mask.sum()),
                "floodedCellCount": int(flooded.sum()),
            }
        )
    return sorted(out, key=lambda w: w["risk"], reverse=True)


def observation_meta(observation: LiveObservation) -> dict:
    return {
        "source": observation.source,
        "fetchedAt": observation.fetched_at.isoformat(),
        "ageSeconds": round(observation.age_seconds(), 1),
        "degraded": observation.degraded,
        "notes": list(observation.notes),
        "cacheTtl": SETTINGS.cache_ttl,
    }


def forecast_payload(lead: int, what_if: WhatIf, force_refresh: bool = False) -> dict:
    if lead not in LEAD_TIMES:
        raise ValueError(f"lead must be one of {list(LEAD_TIMES)}")

    observation = get_observation(force_refresh=force_refresh)
    hazard = _hazard_for(observation, lead, what_if)
    risk, components = composite_risk(hazard)
    confidence = confidence_for(lead, observation.degraded)

    return {
        "lead": lead,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "confidence": confidence,
        "isSimulating": what_if.is_active(),
        "observation": observation_meta(observation),
        "model": model_status(),
        "cells": {
            "risk": _round_list(risk, 4),
            "floodProbability": _round_list(hazard.flood_probability, 4),
            "susceptibility": _round_list(hazard.susceptibility, 4),
            "rainfallIntensity": _round_list(hazard.rainfall_intensity, 2),
            "rainfall3h": _round_list(hazard.rainfall_3h, 2),
            "waterDepth": _round_list(hazard.water_depth, 3),
            "timeToInundation": _nullable_list(hazard.time_to_inundation),
        },
        "riskComponents": {k: _round_list(v, 4) for k, v in components.items()},
        "summary": _summary(hazard, risk),
        "wards": _ward_summaries(hazard, risk, confidence),
    }


def series_payload(what_if: WhatIf) -> dict:
    """Region-wide trend across every lead time, for the nowcast chart."""
    observation = get_observation()
    points = []
    for lead in LEAD_TIMES:
        hazard = _hazard_for(observation, lead, what_if)
        risk, _ = composite_risk(hazard)
        points.append(
            {
                "lead": lead,
                "rainfall": round(float(hazard.rainfall_intensity.mean()), 2),
                "peakRainfall": round(float(hazard.rainfall_intensity.max()), 2),
                "peakFloodProbability": round(float(hazard.flood_probability.max()), 4),
                "meanFloodProbability": round(float(hazard.flood_probability.mean()), 4),
                "depth": round(float(hazard.water_depth.mean()), 4),
                "peakRisk": round(float(risk.max()), 4),
            }
        )
    return {
        "observation": observation_meta(observation),
        "isSimulating": what_if.is_active(),
        "series": points,
    }


def cell_series_payload(row: int, col: int, what_if: WhatIf) -> dict:
    """Per-cell forecast across every lead time, for the inspector."""
    if not (0 <= row < REGION.rows and 0 <= col < REGION.cols):
        raise ValueError(f"cell ({row}, {col}) is outside the {REGION.shape} grid")

    observation = get_observation()
    static = static_layers()
    points = []
    for lead in LEAD_TIMES:
        hazard = _hazard_for(observation, lead, what_if)
        risk, _ = composite_risk(hazard)
        tti = float(hazard.time_to_inundation[row, col])
        points.append(
            {
                "lead": lead,
                "rainfallIntensity": round(float(hazard.rainfall_intensity[row, col]), 2),
                "rainfall3h": round(float(hazard.rainfall_3h[row, col]), 2),
                "floodProbability": round(float(hazard.flood_probability[row, col]), 4),
                "waterDepth": round(float(hazard.water_depth[row, col]), 3),
                "risk": round(float(risk[row, col]), 4),
                "timeToInundation": None if np.isnan(tti) else int(tti),
                "confidence": confidence_for(lead, observation.degraded),
            }
        )

    lons, lats = cell_centres()
    ward = WARDS[int(ward_assignment()[row, col])]
    return {
        "cell": {
            "id": f"c-{col}-{row}",
            "row": row,
            "col": col,
            "lon": round(float(lons[row, col]), 5),
            "lat": round(float(lats[row, col]), 5),
            "wardId": ward.id,
            "wardName": ward.name,
            "elevation": round(float(static["elevation"][row, col]), 1),
            "slope": round(float(static["slope"][row, col]), 2),
            "population": int(round(float(static["population"][row, col]))),
            "infraProximity": round(float(infra_proximity()[row, col]), 3),
            "landUse": str(land_use()[row, col]),
        },
        "observation": observation_meta(observation),
        "series": points,
    }
