"""Assembles the payloads the dashboard consumes.

Kept separate from the HTTP layer so the same logic backs both the API and the
offline `infer_realtime` CLI.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from zoneinfo import ZoneInfo

from rainshield.config import CHANNELS, DYNAMIC_CHANNELS, LEAD_TIMES, SETTINGS
from rainshield.grid import (
    cell_centres,
    infra_proximity,
    land_use,
    static_layers,
    ward_assignment,
    wards_for,
)
from rainshield.hazard import HazardField, WhatIf, compute_hazard, confidence_for
from rainshield.ingest import cadence_for, feed_log, get_observation, storm_phase
from rainshield.ingest.base import (
    LiveObservation,
    brightness_temp_from_cloud,
    marshall_palmer_dbz,
)
from rainshield.models.predictor import model_status, predict_susceptibility
from rainshield.regions import PRIMARY_REGION_ID, get_region
from rainshield.risk import composite_risk, population_at_risk, worst_tier


def _round_list(arr: np.ndarray, digits: int) -> list[float]:
    return [round(float(v), digits) for v in np.asarray(arr).ravel()]


def _nullable_list(arr: np.ndarray, digits: int = 0) -> list[float | None]:
    flat = np.asarray(arr).ravel()
    return [None if np.isnan(v) else round(float(v), digits) for v in flat]


# --------------------------------------------------------------------------
# Static payload — fetched once by the client
# --------------------------------------------------------------------------


def region_descriptor(region_id: str) -> dict:
    """Identity and provenance of one region, without any of its cell data."""
    profile = get_region(region_id)
    geometry = profile.geometry
    return {
        "id": profile.id,
        "name": geometry.name,
        "state": geometry.state,
        "bounds": list(geometry.bounds),
        "centre": list(geometry.centre),
        "rows": geometry.rows,
        "cols": geometry.cols,
        "cellCount": geometry.cell_count,
        "cellWidth": geometry.cell_width,
        "cellHeight": geometry.cell_height,
        "timezone": profile.timezone,
        "kind": profile.kind,
        "simulated": profile.simulated,
        "blurb": profile.blurb,
        "cadenceSeconds": cadence_for(profile.id),
    }


def regions_payload() -> dict:
    """Every region the service can score. Fetched once by the client."""
    from rainshield.regions import region_ids

    return {
        "regions": [region_descriptor(rid) for rid in region_ids()],
        "default": PRIMARY_REGION_ID,
    }


def region_payload(region_id: str = PRIMARY_REGION_ID) -> dict:
    static = static_layers(region_id)
    lons, lats = cell_centres(region_id)
    return {
        "region": region_descriptor(region_id),
        "leadTimes": list(LEAD_TIMES),
        "wards": [
            {"id": w.id, "name": w.name, "lon": w.lon, "lat": w.lat}
            for w in wards_for(region_id)
        ],
        "cells": {
            "lon": _round_list(lons, 5),
            "lat": _round_list(lats, 5),
            "elevation": _round_list(static["elevation"], 1),
            "slope": _round_list(static["slope"], 2),
            "population": [int(round(float(v))) for v in static["population"].ravel()],
            "infraProximity": _round_list(infra_proximity(region_id), 3),
            "landUse": [str(v) for v in land_use(region_id).ravel()],
            "wardIndex": [int(v) for v in ward_assignment(region_id).ravel()],
        },
    }


# --------------------------------------------------------------------------
# Forecast payload
# --------------------------------------------------------------------------


#: Susceptibility depends only on the observation and lead time, never on the
#: what-if sliders, so it is memoised across a single observation. Keeps slider
#: drags and the 6-lead trend chart off the network's critical path.
_SUSCEPTIBILITY_CACHE: dict[tuple[str, str, int], np.ndarray] = {}


def _susceptibility_for(observation: LiveObservation, lead: int) -> np.ndarray:
    key = (observation.region_id, observation.fetched_at.isoformat(), lead)
    cached = _SUSCEPTIBILITY_CACHE.get(key)
    if cached is not None:
        return cached
    value = predict_susceptibility(observation, lead, observation.region_id)
    if len(_SUSCEPTIBILITY_CACHE) > 8 * len(LEAD_TIMES):
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
        observation.region_id,
    )


def _summary(hazard: HazardField, risk: np.ndarray, region_id: str) -> dict:
    population = static_layers(region_id)["population"]
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


def _ward_summaries(
    hazard: HazardField, risk: np.ndarray, confidence: str, region_id: str
) -> list[dict]:
    assignment = ward_assignment(region_id).ravel()
    population = static_layers(region_id)["population"].ravel()
    risk_flat = risk.ravel()
    prob = hazard.flood_probability.ravel()
    depth = hazard.water_depth.ravel()
    tti = hazard.time_to_inundation.ravel()

    out: list[dict] = []
    for index, ward in enumerate(wards_for(region_id)):
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


def _stamp(moment: datetime, timezone_name: str) -> dict:
    """One instant, in UTC and in the region's own zone.

    The dashboard used to render timestamps with the *browser's* locale and then
    label them IST, which is wrong for anyone not sitting in India. The backend
    knows which zone a region is in, so it says so explicitly and hands over
    both renderings plus the offset.
    """
    zone = ZoneInfo(timezone_name)
    local = moment.astimezone(zone)
    offset = local.utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset else 0
    sign = "+" if minutes >= 0 else "-"
    return {
        "utc": moment.astimezone(timezone.utc).isoformat(),
        "local": local.isoformat(),
        "localTime": local.strftime("%H:%M:%S"),
        "localDate": local.strftime("%Y-%m-%d"),
        "timezone": timezone_name,
        "abbreviation": local.tzname() or timezone_name,
        "utcOffset": f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}",
        "epoch": moment.timestamp(),
    }


def observation_meta(observation: LiveObservation) -> dict:
    profile = get_region(observation.region_id)
    cadence = cadence_for(profile.id)
    fetched = observation.fetched_at
    return {
        "source": observation.source,
        "regionId": profile.id,
        "fetchedAt": fetched.isoformat(),
        "ageSeconds": round(observation.age_seconds(), 1),
        "degraded": observation.degraded,
        "simulated": observation.simulated,
        "notes": list(observation.notes),
        "cacheTtl": cadence,
        "cadenceSeconds": cadence,
        "timestamp": _stamp(fetched, profile.timezone),
        "nextUpdate": _stamp(
            fetched + timedelta(seconds=cadence), profile.timezone
        ),
    }


# --------------------------------------------------------------------------
# The live feed payload — every field, with units and timestamps
# --------------------------------------------------------------------------

#: What each field is, where it comes from and what it feeds. Ordered the way
#: the feed view lists them: what the upstream served, then what is derived
#: from it, then the static layers the model reads once.
_OBSERVED_FIELDS = (
    ("rainRate", "mm/hr", "Instantaneous rain rate", "gpm_rain"),
    ("rain3h", "mm", "Rainfall accumulated over the preceding 3 hours", "aws_rain"),
    ("soilMoisture", "m³/m³", "Volumetric soil moisture, 0–7 cm", None),
    ("cloudCover", "%", "Total cloud cover", None),
    ("antecedent24h", "mm", "Rainfall over the previous 24 hours", None),
)

_DERIVED_FIELDS = (
    ("river_level", "index 0–1.5", "Catchment wetness: soil moisture + antecedent load"),
    ("cloud_top_temp", "K", "Brightness temperature from cloud cover (Stage 0 conversion)"),
    ("radar_reflectivity", "dBZ", "Reflectivity from rain rate, Z = 200 R^1.6"),
)

_STATIC_FIELDS = (
    ("elevation", "m", "Terrain elevation (SRTM DEM)"),
    ("slope", "°", "Terrain slope"),
    ("infrastructure", "features/km²", "OSM critical-infrastructure count"),
    ("population", "people/km²", "WorldPop population density"),
)


def _stats(array: np.ndarray, digits: int = 2) -> dict:
    flat = np.asarray(array, dtype=np.float64).ravel()
    return {
        "min": round(float(flat.min()), digits),
        "mean": round(float(flat.mean()), digits),
        "max": round(float(flat.max()), digits),
    }


def observation_payload(region_id: str = PRIMARY_REGION_ID) -> dict:
    """Everything in the current observation, field by field.

    This is what the dashboard's live-feed view renders: the provenance and
    timing of the data, then every channel the model is about to read — the
    ones the upstream served, the ones derived from them, and the static layers
    — each with its units and its spread across the grid.
    """
    observation = get_observation(region_id=region_id)
    profile = get_region(region_id)

    observed = []
    for key, unit, description, channel in _OBSERVED_FIELDS:
        if key == "rainRate":
            values = observation.rain_rate
        elif key == "rain3h":
            values = observation.rain_3h
        else:
            values = None

        if values is not None:
            observed.append(
                {
                    "key": key,
                    "unit": unit,
                    "description": description,
                    "modelChannel": channel,
                    "perLead": {str(lead): _stats(values[lead]) for lead in LEAD_TIMES},
                    **_stats(values[0]),
                }
            )
        else:
            array = getattr(
                observation,
                {"soilMoisture": "soil_moisture", "cloudCover": "cloud_cover"}.get(
                    key, "antecedent_24h"
                ),
            )
            observed.append(
                {
                    "key": key,
                    "unit": unit,
                    "description": description,
                    "modelChannel": channel,
                    "perLead": None,
                    **_stats(array, 3 if key == "soilMoisture" else 2),
                }
            )

    # The derived channels, computed exactly as the model input builder does.
    river_level = np.clip(
        observation.soil_moisture * 0.6 + observation.antecedent_24h / 120.0, 0.0, 1.5
    )
    derived_arrays = {
        "river_level": river_level,
        "cloud_top_temp": brightness_temp_from_cloud(observation.cloud_cover),
        "radar_reflectivity": marshall_palmer_dbz(observation.rain_rate[0]),
    }
    derived = [
        {"key": key, "unit": unit, "description": description, **_stats(derived_arrays[key], 3)}
        for key, unit, description in _DERIVED_FIELDS
    ]

    static = static_layers(region_id)
    statics = [
        {"key": key, "unit": unit, "description": description, **_stats(static[key], 2)}
        for key, unit, description in _STATIC_FIELDS
    ]

    return {
        "region": region_descriptor(region_id),
        "observation": observation_meta(observation),
        "model": model_status(),
        "storm": storm_phase(region_id),
        "leadTimes": list(LEAD_TIMES),
        "channelOrder": list(CHANNELS),
        "dynamicChannels": list(DYNAMIC_CHANNELS),
        "fields": {"observed": observed, "derived": derived, "static": statics},
        "arrivals": [
            {
                "source": a.source,
                "degraded": a.degraded,
                "simulated": a.simulated,
                "peakRainRate": a.peak_rain_rate,
                "meanRainRate": a.mean_rain_rate,
                "peakRain3h": a.peak_rain_3h,
                "peakSoilMoisture": a.peak_soil_moisture,
                "meanCloudCover": a.mean_cloud_cover,
                "peakAntecedent24h": a.peak_antecedent_24h,
                "notes": list(a.notes),
                "timestamp": _stamp(a.fetched_at, profile.timezone),
            }
            for a in feed_log(region_id)
        ],
        "servedAt": _stamp(datetime.now(timezone.utc), profile.timezone),
    }


def forecast_payload(
    lead: int,
    what_if: WhatIf,
    force_refresh: bool = False,
    region_id: str = PRIMARY_REGION_ID,
) -> dict:
    if lead not in LEAD_TIMES:
        raise ValueError(f"lead must be one of {list(LEAD_TIMES)}")

    observation = get_observation(force_refresh=force_refresh, region_id=region_id)
    hazard = _hazard_for(observation, lead, what_if)
    risk, components = composite_risk(hazard, region_id)
    confidence = confidence_for(lead, observation.degraded)

    return {
        "lead": lead,
        "region": region_descriptor(region_id),
        "storm": storm_phase(region_id),
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
        "summary": _summary(hazard, risk, region_id),
        "wards": _ward_summaries(hazard, risk, confidence, region_id),
    }


def series_payload(what_if: WhatIf, region_id: str = PRIMARY_REGION_ID) -> dict:
    """Region-wide trend across every lead time, for the nowcast chart."""
    observation = get_observation(region_id=region_id)
    points = []
    for lead in LEAD_TIMES:
        hazard = _hazard_for(observation, lead, what_if)
        risk, _ = composite_risk(hazard, region_id)
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
        "region": region_descriptor(region_id),
        "observation": observation_meta(observation),
        "isSimulating": what_if.is_active(),
        "series": points,
    }


def cell_series_payload(
    row: int, col: int, what_if: WhatIf, region_id: str = PRIMARY_REGION_ID
) -> dict:
    """Per-cell forecast across every lead time, for the inspector."""
    geometry = get_region(region_id).geometry
    if not (0 <= row < geometry.rows and 0 <= col < geometry.cols):
        raise ValueError(f"cell ({row}, {col}) is outside the {geometry.shape} grid")

    observation = get_observation(region_id=region_id)
    static = static_layers(region_id)
    points = []
    for lead in LEAD_TIMES:
        hazard = _hazard_for(observation, lead, what_if)
        risk, _ = composite_risk(hazard, region_id)
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

    lons, lats = cell_centres(region_id)
    ward = wards_for(region_id)[int(ward_assignment(region_id)[row, col])]
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
            "infraProximity": round(float(infra_proximity(region_id)[row, col]), 3),
            "landUse": str(land_use(region_id)[row, col]),
        },
        "region": region_descriptor(region_id),
        "observation": observation_meta(observation),
        "series": points,
    }
