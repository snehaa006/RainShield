"""Hugging Face Space entry point for the RainShield inference API.

Spaces' Docker SDK is a paid feature, so this Space runs under the Gradio SDK
instead. That is not a compromise in substance: Gradio is itself built on
FastAPI, so the real application is mounted and served unchanged — every route
under /api, /health and /docs behaves exactly as it does anywhere else. Gradio
supplies the landing page the Space embeds, and nothing more.

Why a Space at all: Render's free tier caps the service at 0.15 of a CPU core
and spins it down after fifteen minutes of inactivity. Scoring one observation
is seven neural forward passes, about 7.5 CPU-seconds, which at that cap is
most of a minute — and every cold start put a fresh minute on top. A free
Space gets 2 vCPU and sleeps after 48 hours instead of 15 minutes.

This file lives only on the `hf-space` branch. `main` has no Gradio dependency
and never imports this.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The serving package lives under backend/, and config.REPO_ROOT walks two
# parents up from rainshield/config.py to find processed_data/ — which lands on
# this directory either way, so the weights and rasters resolve unchanged.
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

import gradio as gr  # noqa: E402

from rainshield.api.app import app as api  # noqa: E402
from rainshield.config import LEAD_TIMES, SETTINGS  # noqa: E402
from rainshield.regions import get_region, region_ids  # noqa: E402

BASE = "https://huggingface.co/spaces"


def _landing() -> gr.Blocks:
    """The page the Space embeds. Documentation, not a control surface.

    Deliberately read-only: this Space exists to serve an API to the dashboard,
    and a second place to drive the model would be a second thing to keep
    truthful.
    """
    regions = ", ".join(f"`{r}` ({get_region(r).geometry.name})" for r in region_ids())
    leads = ", ".join(f"{lead}" for lead in LEAD_TIMES)

    with gr.Blocks(title="RainShield API", analytics_enabled=False) as page:
        gr.Markdown(
            f"""
# 🌧️ RainShield inference API

Heavy-rainfall early warning and flood inundation prediction for the Mumbai
suburban 1 km grid. This Space serves the **API only** — the dashboard is
deployed separately and points at this URL.

**Interactive docs:** [`/docs`](/docs) · **Health:** [`/health`](/health)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/regions` | the regions on offer, live and simulated |
| `GET /api/region` | static grid, wards, terrain — fetch once |
| `GET /api/observation` | the current observation, field by field |
| `GET /api/forecast?lead=` | scored grid at one lead time |
| `GET /api/series` | region-wide trend across every lead time |
| `GET /api/drainage` | catchment mass balance, pumping and tide |
| `GET /api/cell/{{row}}/{{col}}` | one cell across every lead time |

Regions: {regions}. Lead times, minutes: {leads}.

Model backend: `{SETTINGS.weights_filename}` served through NumPy — no PyTorch
in production.

> Rainfall forecasts come from Open-Meteo and MET Norway. Pump capacities,
> outfall levels and tidal constants are **uncalibrated estimates**; 1 km is
> catchment scale, not street scale. Defensible, not validated.
"""
        )
    return page


# FastAPI resolves an explicit route before a mount, so the service's own "/"
# banner would win over the landing page and the Space would embed raw JSON.
# On a Space the embedded page *is* the front door, so the banner gives way —
# everything it listed is on the landing page and in /docs anyway. Dropped
# here rather than in the API, so that `main` keeps serving it.
api.router.routes = [
    route for route in api.router.routes if getattr(route, "path", None) != "/"
]

# Every API route is untouched beneath the landing page.
app = gr.mount_gradio_app(api, _landing(), path="/")


if __name__ == "__main__":
    import uvicorn

    # Spaces proxies whatever listens on $PORT, 7860 by default.
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
