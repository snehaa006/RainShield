"""FastAPI service exposing the RainShield forecast to the dashboard."""

from __future__ import annotations

import logging

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from rainshield.config import LEAD_TIMES, SETTINGS
from rainshield.hazard import WhatIf
from rainshield.ingest import (
    clear_cache,
    get_observation,
    simulated_cadence,
    start_feed_clock,
    stop_feed_clock,
)
from rainshield.models.predictor import model_status
from rainshield.regions import PRIMARY_REGION_ID, get_region, region_ids
from rainshield.service import (
    cell_series_payload,
    forecast_payload,
    observation_meta,
    observation_payload,
    region_payload,
    regions_payload,
    series_payload,
)


def _resolve_region(region: str | None) -> str:
    """Validate a region id from the query string, defaulting to the primary."""
    try:
        return get_region(region).id
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


RegionQuery = Query(PRIMARY_REGION_ID, description="Region id; see /api/regions")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("rainshield")

def _warm_cache() -> None:
    """Pull the first observation for every region in the background.

    Without this the first visitor pays the upstream round trip plus the first
    inference, which on a sleeping free-tier instance lands on top of an already
    slow cold start. Runs off the startup path so a slow or unreachable feed
    cannot hold up (or fail) the deploy.
    """
    for region in region_ids():
        try:
            observation = get_observation(region_id=region)
            log.info(
                "warm-up observation [%s]: source=%s degraded=%s simulated=%s notes=%s",
                region,
                observation.source,
                observation.degraded,
                observation.simulated,
                "; ".join(observation.notes) or "-",
            )
        except Exception as exc:  # noqa: BLE001 — warm-up must never take the app down
            log.warning("warm-up fetch for %s failed: %s: %s", region, type(exc).__name__, exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load weights and static layers at boot so the first request is fast."""
    status = model_status()
    log.info("model backend=%s runtime=%s loaded=%s", status["backend"], status["runtime"], status["loaded"])
    if status["error"]:
        log.warning("model load issue: %s", status["error"])
    threading.Thread(target=_warm_cache, name="warm-cache", daemon=True).start()
    # Keep every region's feed arriving on its own cadence, so a dashboard that
    # is merely open still sees new data land.
    start_feed_clock()
    try:
        yield
    finally:
        stop_feed_clock()


app = FastAPI(
    lifespan=lifespan,
    title="RainShield API",
    version="1.0.0",
    description=(
        "Live flood-risk inference for the Mumbai 1 km grid. The CNN-transformer "
        "supplies terrain flood susceptibility; live Open-Meteo rainfall drives "
        "the hazard on top of it."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "RainShield API",
        "regions": region_ids(),
        "leadTimes": list(LEAD_TIMES),
        "docs": "/docs",
        "endpoints": [
            "/health",
            "/api/regions",
            "/api/region",
            "/api/observation",
            "/api/forecast",
            "/api/series",
            "/api/cell/{row}/{col}",
        ],
    }


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness plus the state of the model and every region's feed."""
    feeds = {}
    for rid in region_ids():
        try:
            feeds[rid] = observation_meta(get_observation(region_id=rid))
        except Exception as exc:  # noqa: BLE001 — health must never 500
            feeds[rid] = {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "status": "ok",
        "model": model_status(),
        "provider": SETTINGS.provider,
        "simulatedCadence": simulated_cadence(),
        "observation": feeds.get(PRIMARY_REGION_ID, {}),
        "feeds": feeds,
    }


@app.get("/api/regions", tags=["meta"])
def regions() -> dict:
    """Every region the service can score, live and simulated."""
    return regions_payload()


@app.get("/api/region", tags=["grid"])
def region(region: str = RegionQuery) -> dict:
    """Static grid geometry, wards and terrain layers. Fetch once and cache."""
    region_id = _resolve_region(region)
    try:
        return region_payload(region_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/observation", tags=["feed"])
def observation(region: str = RegionQuery) -> dict:
    """The current observation field by field, with units and timestamps.

    Backs the dashboard's live-feed view: what arrived, when it arrived in both
    UTC and the region's own zone, when the next one is due, and the spread of
    every channel the model is about to read.
    """
    region_id = _resolve_region(region)
    try:
        return observation_payload(region_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/forecast", tags=["forecast"])
def forecast(
    lead: int = Query(0, description="Lead time in minutes"),
    refresh: bool = Query(False, description="Bypass the observation cache"),
    extra_rainfall: float = Query(0.0, ge=0, le=300),
    soil_saturation: float = Query(1.0, ge=0.5, le=1.5),
    drainage_capacity: float = Query(1.0, ge=0.3, le=1.2),
    region: str = RegionQuery,
) -> dict:
    """Scored grid at one lead time, plus region and ward roll-ups."""
    region_id = _resolve_region(region)
    settings = WhatIf(extra_rainfall, soil_saturation, drainage_capacity)
    try:
        return forecast_payload(lead, settings, force_refresh=refresh, region_id=region_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/series", tags=["forecast"])
def series(
    extra_rainfall: float = Query(0.0, ge=0, le=300),
    soil_saturation: float = Query(1.0, ge=0.5, le=1.5),
    drainage_capacity: float = Query(1.0, ge=0.3, le=1.2),
    region: str = RegionQuery,
) -> dict:
    """Region-wide trend across every lead time."""
    region_id = _resolve_region(region)
    settings = WhatIf(extra_rainfall, soil_saturation, drainage_capacity)
    try:
        return series_payload(settings, region_id=region_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/cell/{row}/{col}", tags=["forecast"])
def cell(
    row: int,
    col: int,
    extra_rainfall: float = Query(0.0, ge=0, le=300),
    soil_saturation: float = Query(1.0, ge=0.5, le=1.5),
    drainage_capacity: float = Query(1.0, ge=0.3, le=1.2),
    region: str = RegionQuery,
) -> dict:
    """One cell's attributes and its forecast across every lead time."""
    region_id = _resolve_region(region)
    settings = WhatIf(extra_rainfall, soil_saturation, drainage_capacity)
    try:
        return cell_series_payload(row, col, settings, region_id=region_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/refresh", tags=["forecast"])
def refresh(region: str = RegionQuery) -> dict:
    """Drop the cached observation for a region and pull its feed again."""
    region_id = _resolve_region(region)
    clear_cache(region_id)
    fresh = get_observation(force_refresh=True, region_id=region_id)
    return {"refreshed": True, "observation": observation_meta(fresh)}
