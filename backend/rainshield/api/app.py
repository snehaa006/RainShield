"""FastAPI service exposing the RainShield forecast to the dashboard."""

from __future__ import annotations

import logging

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from rainshield.config import LEAD_TIMES, REGION, SETTINGS
from rainshield.hazard import WhatIf
from rainshield.ingest import clear_cache, get_observation
from rainshield.models.predictor import model_status
from rainshield.service import (
    cell_series_payload,
    forecast_payload,
    observation_meta,
    region_payload,
    series_payload,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("rainshield")

def _warm_cache() -> None:
    """Pull the first observation in the background.

    Without this the first visitor pays the upstream round trip plus the first
    inference, which on a sleeping free-tier instance lands on top of an already
    slow cold start. Runs off the startup path so a slow or unreachable feed
    cannot hold up (or fail) the deploy.
    """
    try:
        observation = get_observation()
        log.info(
            "warm-up observation: source=%s degraded=%s notes=%s",
            observation.source,
            observation.degraded,
            "; ".join(observation.notes) or "-",
        )
    except Exception as exc:  # noqa: BLE001 — warm-up must never take the app down
        log.warning("warm-up fetch failed: %s: %s", type(exc).__name__, exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load weights and static layers at boot so the first request is fast."""
    status = model_status()
    log.info("model backend=%s runtime=%s loaded=%s", status["backend"], status["runtime"], status["loaded"])
    if status["error"]:
        log.warning("model load issue: %s", status["error"])
    threading.Thread(target=_warm_cache, name="warm-cache", daemon=True).start()
    yield


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
        "region": REGION.name,
        "leadTimes": list(LEAD_TIMES),
        "docs": "/docs",
        "endpoints": ["/health", "/api/region", "/api/forecast", "/api/series", "/api/cell/{row}/{col}"],
    }


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness plus the state of the model and the live feed."""
    try:
        observation = get_observation()
        feed = observation_meta(observation)
    except Exception as exc:  # noqa: BLE001 — health must never 500
        feed = {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "status": "ok",
        "model": model_status(),
        "provider": SETTINGS.provider,
        "observation": feed,
    }


@app.get("/api/region", tags=["grid"])
def region() -> dict:
    """Static grid geometry, wards and terrain layers. Fetch once and cache."""
    try:
        return region_payload()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/forecast", tags=["forecast"])
def forecast(
    lead: int = Query(0, description="Lead time in minutes"),
    refresh: bool = Query(False, description="Bypass the observation cache"),
    extra_rainfall: float = Query(0.0, ge=0, le=300),
    soil_saturation: float = Query(1.0, ge=0.5, le=1.5),
    drainage_capacity: float = Query(1.0, ge=0.3, le=1.2),
) -> dict:
    """Scored grid at one lead time, plus region and ward roll-ups."""
    settings = WhatIf(extra_rainfall, soil_saturation, drainage_capacity)
    try:
        return forecast_payload(lead, settings, force_refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/series", tags=["forecast"])
def series(
    extra_rainfall: float = Query(0.0, ge=0, le=300),
    soil_saturation: float = Query(1.0, ge=0.5, le=1.5),
    drainage_capacity: float = Query(1.0, ge=0.3, le=1.2),
) -> dict:
    """Region-wide trend across every lead time."""
    settings = WhatIf(extra_rainfall, soil_saturation, drainage_capacity)
    try:
        return series_payload(settings)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/cell/{row}/{col}", tags=["forecast"])
def cell(
    row: int,
    col: int,
    extra_rainfall: float = Query(0.0, ge=0, le=300),
    soil_saturation: float = Query(1.0, ge=0.5, le=1.5),
    drainage_capacity: float = Query(1.0, ge=0.3, le=1.2),
) -> dict:
    """One cell's attributes and its forecast across every lead time."""
    settings = WhatIf(extra_rainfall, soil_saturation, drainage_capacity)
    try:
        return cell_series_payload(row, col, settings)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/refresh", tags=["forecast"])
def refresh() -> dict:
    """Drop the cached observation and pull the live feed again."""
    clear_cache()
    observation = get_observation(force_refresh=True)
    return {"refreshed": True, "observation": observation_meta(observation)}
