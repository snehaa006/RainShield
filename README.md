# RainShield AI

Heavy-rainfall early warning and flood inundation prediction for the Mumbai
suburban 1 km grid (SIH26071, Team HydroNex).

A FastAPI backend pulls live weather, runs the trained CNN-transformer over a
45 × 39 grid of 1 km cells, and serves the scored grid to a React dashboard.
Nothing on the board is canned any more — every number comes from the API.

```
┌─ live feed ──────┐   ┌─ backend/rainshield ─────────────┐   ┌─ dashboard ─┐
│ Open-Meteo       │──▶│ 10-channel tensor → RainShieldNet │──▶│ React +     │
│ (GFS / best_match)│   │ → susceptibility × rainfall       │   │ MapLibre    │
└──────────────────┘   │ → composite risk → ward roll-up   │   └─────────────┘
                       └───────────────────────────────────┘
```

## Running it

Two processes. The backend first:

```bash
cd backend
pip install -r requirements.txt
uvicorn rainshield.api.app:app --reload --port 8000     # http://localhost:8000/docs
```

Then the dashboard, which proxies `/api` and `/health` to port 8000 in dev:

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # typecheck + production bundle
```

Offline, or when the upstream feed is unreachable, run the backend with
`RAINSHIELD_PROVIDER=synthetic` for a deterministic demo field. It is always
labelled **Degraded** in the UI — synthetic output is never presented as live.

One-off scoring without the API:

```bash
python backend/pipeline/infer_realtime.py --all-leads
python backend/pipeline/infer_realtime.py --lead 180 --json out.json
```

## Layout

```
backend/
  rainshield/            the serving package
    config.py            region geometry, channel order, risk weights, tiers
    grid.py              cell geometry, wards, static layers from the Stage 1 tensor
    ingest/              Open-Meteo provider, synthetic fallback, mesh interpolation
    models/              network definition, torch-free checkpoint reader + forward pass
    hazard.py            susceptibility × rainfall → probability, depth, onset
    risk.py              composite score, tiers, ward roll-ups
    service.py           the payloads the dashboard consumes
    api/app.py           FastAPI routes
  pipeline/              the offline stages, runnable from any directory
    stage0_01..10        the ten aligned raster layers + the ground-truth mask
    stage1_build_tensor  stacks them into (10, 45, 39)
    stage2_train         trains RainShieldNet, saves weights + risk raster
    stage3_dashboard     the 4-panel validation figure
    infer_realtime       standalone live scoring
  tests/                 33 tests: checkpoint, numpy/torch equivalence, ingest, hazard, API
src/                     the React dashboard
processed_data/          aligned rasters, the Stage 1 tensor, the trained weights
```

## The model, and what it actually learned

`RainShieldNet` is a 2D CNN → squeeze-excitation → 3-layer spatial transformer →
per-cell sigmoid head (175k parameters). Three things about it are worth knowing
before trusting a number on the dashboard:

**It consumes raw physical units.** Stage 1 writes both a raw `X_tensor` and a
MinMax-scaled `X_matrix`; Stage 2 trains on the *raw* one, and the leading
BatchNorm absorbs the differing channel magnitudes. This was confirmed against
the checkpoint's stored BatchNorm running statistics — raw input reproduces them
to 0.06%, scaled input is 100% off. Feeding scaled input produces garbage.

**Its target is topographic.** The Stage 0 ground truth is
`elevation <= 12 m AND slope <= 1.5°` — and elevation and slope are input
channels 0 and 1. So the network learned to re-derive a terrain threshold from
data it was handed. That is why the holdout ROC-AUC is high, and it is also why
the output barely moves with the weather: scaling every rainfall channel by 4×
shifts the mean output by about +0.02, and the radar channel's response even has
the wrong sign.

**So the weather drives the hazard, not the network.** The model output is used
as *flood susceptibility* — where water collects, which is what it genuinely
knows — and live rainfall drives the hazard on top of it:

```
P(flood) = susceptibility × (1 − exp(−effective_rain / 45 mm))
```

No rain gives no flooding however low-lying the cell; sustained heavy rain
saturates toward that cell's susceptibility. `effective_rain` scales the 3-hour
accumulation by antecedent soil wetness and drainage capacity. Composite risk
then follows the architecture spec and is tunable in `config.py`:

```
Risk = 0.35 rainfall severity + 0.30 flood probability + 0.20 water depth
     + 0.10 population exposure + 0.05 critical-infrastructure proximity

Normal < 0.25 ≤ Watch < 0.50 ≤ Warning < 0.75 ≤ Critical
```

To make the network itself weather-responsive it needs a target that depends on
weather — observed inundation from multiple storm dates, rather than a DEM
threshold — and more than one training sample. That is a data problem, not an
architecture one.

### No PyTorch in production

`models/checkpoint.py` reads a `.pth` into NumPy arrays without importing torch
(bit-identical to `torch.load`), and `models/numpy_backend.py` runs the forward
pass in NumPy alone, matching torch to ~2 × 10⁻⁶. For a 175k-parameter model on
one 45 × 39 grid, torch bought nothing and cost a ~2.5 GB dependency and a slow
cold start. Torch is still needed to *train* — see `requirements-dev.txt`, which
also runs the equivalence test.

## Live data

Six of the ten channels are refetched per inference; the four terrain and
exposure layers are read once from the Stage 1 tensor.

| Channel | Live source |
| --- | --- |
| `aws_rain` | Open-Meteo 3 hr accumulation |
| `gpm_rain` | Open-Meteo instantaneous rate |
| `gfs_forecast` | Open-Meteo forecast at the lead time |
| `river_level` | soil moisture + antecedent 24 hr rainfall |
| `cloud_top_temp` | cloud cover → brightness temperature, Stage 0's conversion |
| `radar_reflectivity` | rain rate → dBZ via Marshall-Palmer, Z = 200 R^1.6 |

A 5 × 5 mesh is requested and splined onto the 1 km grid — GFS is 11–25 km
native, so this already over-samples it. Observations are cached for
`RAINSHIELD_CACHE_TTL` (default 600 s).

**Two live sources, because one is not enough.** Open-Meteo's free tier is
capped *per IP*, and Render's outbound addresses are shared between customers —
the first deploy was rejected with `429: Daily API request limit exceeded`
before it had made a single successful call. So MET Norway's Locationforecast
(keyless, no per-IP cap, an independent forecast rather than a retry) follows
it. `RAINSHIELD_PROVIDER` names the *preferred* source, not the only one.

met.no serves one coordinate per request, so its mesh is 3 × 3, and its series
is forecast-only, so antecedent rainfall is unavailable and soil wetness uses
the substitution below. Its terms require an identifying User-Agent — set
`RAINSHIELD_USER_AGENT` to include a contact address.

Only when *every* live source fails is the last good observation reused, then
the synthetic field. Just those cases are flagged `degraded`: a working second
source is still live data.

> **Fixed along the way:** Stage 0 built the GPM, GFS, INSAT and DWR layers by
> evaluating a spline over *ascending* latitudes and writing the result into a
> north-up raster, which left those four layers vertically flipped relative to
> the DEM they were stacked with. The pipeline scripts and the live ingest now
> both flip correctly. Re-run Stages 0–2 to retrain on corrected layers.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | model state, provider, feed age |
| `GET /api/region` | static grid, wards, terrain and exposure layers — fetch once |
| `GET /api/forecast?lead=` | scored grid at one lead time + region and ward roll-ups |
| `GET /api/series` | region-wide trend across every lead time |
| `GET /api/cell/{row}/{col}` | one cell across every lead time |
| `POST /api/refresh` | drop the cached observation and re-pull |

The what-if sliders are query parameters on the forecast endpoints:
`extra_rainfall` (mm), `soil_saturation` (0.5–1.5), `drainage_capacity`
(0.3–1.2). Cell payloads are columnar — one array per metric, flattened
row-major, **row 0 is the northern edge** — which is far lighter than 1755
GeoJSON features per refresh. Interactive docs at `/docs`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `RAINSHIELD_PROVIDER` | `openmeteo` | preferred live source (`openmeteo`, `metno`); the others still follow as fallbacks. `synthetic` for an offline demo |
| `RAINSHIELD_CACHE_TTL` | `600` | seconds an observation is reused |
| `RAINSHIELD_MESH` | `5` | upstream sample mesh per axis |
| `RAINSHIELD_CORS_ORIGINS` | `*` | comma-separated allowed origins |
| `RAINSHIELD_PROCESSED_DIR` | `./processed_data` | weights and Stage 1 tensor |
| `RAINSHIELD_FORCE_ANALYTICAL` | unset | skip the network, use the analytical fallback |
| `VITE_API_BASE` | same-origin | backend URL, **inlined at build time** |
| `VITE_BASEMAP_KEY` | — | CARTO key; tiles watermark without one |

Both `VITE_*` values are baked into the bundle at build time, so changing them
on a host does nothing to an existing deployment — redeploy with the build cache
off.

## Deploying

The dashboard runs on Vercel and the inference API on Render — two services, so
the dashboard needs to be told where the API lives.

**Backend (Render).** `render.yaml` describes the service: Python, built with
`pip install -r backend/requirements.txt` and started with

```
uvicorn rainshield.api.app:app --app-dir backend --host 0.0.0.0 --port $PORT
```

The commands run from the repository root rather than using `rootDir`, so the
committed weights and rasters under `processed_data/` stay on the path. Nothing
needs uploading — the checkpoint is 726 KB and is in the repo.

**Frontend (Vercel).** Set `VITE_API_BASE` to the Render service URL in
Project → Settings → Environment Variables, then **redeploy**. Vite inlines
`VITE_*` at build time, so setting the variable alone does nothing to an
existing deployment — it has to be rebuilt. Set `VITE_BASEMAP_KEY` the same way
or the CARTO tiles carry a watermark.

Without `VITE_API_BASE` the client calls its own origin, which on Vercel means
`/api/*` 404s and the board shows "Cannot reach the inference API".

On Render's free tier the API sleeps after inactivity, so the first request
after a sleep pays a cold start of roughly a minute.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests/ -q
```

Covers the torch-free checkpoint reader against `torch.load`, the NumPy forward
pass against PyTorch, Open-Meteo parsing (including null handling and the
latitude orientation), hazard monotonicity, and the API contract.

## Stack

Backend: FastAPI, NumPy, SciPy. Training: PyTorch, rasterio, GeoPandas,
scikit-learn. Frontend: React 18, TypeScript, Vite, Tailwind, MapLibre GL,
Recharts.
