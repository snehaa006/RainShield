# RainShield AI

Heavy-rainfall early warning and flood inundation prediction for the Mumbai
suburban 1 km grid (SIH26071, Team HydroNex).

A FastAPI backend pulls live weather, runs the trained CNN-transformer over a
45 × 39 grid of 1 km cells, and serves the scored grid to a React dashboard.
Nothing on the board is canned any more — every number comes from the API.

Two regions are served: **Mumbai Suburban**, on real terrain and live weather,
and **Coromandel Delta**, a *simulated* region that exists to exercise the
Warning and Critical paths Mumbai rarely reaches. Everything about the second
one is labelled — see [Regions](#regions).

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
That is separate from the simulated *region* below, which is a deliberate second
region rather than a fallback.

One-off scoring without the API:

```bash
python backend/pipeline/infer_realtime.py --all-leads
python backend/pipeline/infer_realtime.py --lead 180 --json out.json
```

## Regions

`/api/regions` lists what the service can score. Every forecast endpoint takes
`?region=<id>`, defaulting to `mumbai`.

| Region | id | Terrain | Weather | Reaches |
| --- | --- | --- | --- | --- |
| Mumbai Suburban | `mumbai` | Stage 0/1 rasters (real) | Open-Meteo → MET Norway (real) | whatever the weather is doing |
| Coromandel Delta | `coromandel` | generated (`regions.py`) | scripted storm (`ingest/simulated.py`) | Normal → Watch → Warning → Critical, every cycle |

### Why a simulated region exists

Mumbai is quiet most of the year. With a genuinely live feed the board sits at
Normal or Watch, so the parts of the system that matter most — the Warning and
Critical tiers, ward escalation, time-to-inundation, the CAP alert path — never
get exercised in a demo. The second region drives them all.

**It is not dressed up as real.** A simulated region is `kind: "simulated"` in
the registry, every observation it produces carries `simulated: true`, the
dashboard shows an amber banner on every view, the status bar and map card tag
the feed, and its CAP alerts append `[SIMULATED — not a real place]` to the area
description. It never reaches for a live provider, whatever `RAINSHIELD_PROVIDER`
says, so nothing generated can be attributed to an upstream.

Note the distinction the code draws between two flags:

* `degraded` — a **real** feed failed and cached or synthetic data stood in.
* `simulated` — the field is generated. A simulated region has no real feed to
  lose, so it is *not* degraded; it is simply not a measurement.

### The storm

A monsoon depression makes landfall from the sea on the eastern edge, tracks
inland and decays, on a cycle of `RAINSHIELD_SIM_PERIOD` minutes (default 180):

```
phase 0.00   offshore, grid dry .......................... NORMAL
phase 0.25   rainband reaches the coast .................. WATCH
phase 0.45   landfall, peak intensity over the delta ..... CRITICAL
phase 0.65   centre inland, coastal rain easing .......... WARNING
phase 0.85   remnant rain, ground still saturated ........ WATCH
```

Over one 3-hour cycle that is roughly 57 min Normal, 34 Watch, 35 Warning and
54 Critical. Antecedent rainfall and soil wetness accumulate across the cycle
rather than tracking the instantaneous rate, so the ground stays saturated behind
the storm and the hazard decays more slowly than the rainfall does.

The storm is a **pure function of wall-clock time**, so every request computes
the same state and the API cannot drift from a client polling it.

**Lead times project, they do not loop.** Wall-clock time wraps — one depression
follows another — but a *forecast* advances the storm that exists now and clamps
at the end of its life:

```
storm offshore at the moment of asking
  +0 min    11 mm/3hr   NORMAL     it is offshore
  +30 min   58 mm/3hr   WARNING    rainband reaching the coast
  +60 min  128 mm/3hr   CRITICAL   landfall
  +120 min  61 mm/3hr   WATCH      centre inland
  +180 min   2 mm/3hr   NORMAL     passed
```

Wrapping the lead times instead — which is what the first cut did — made the
+3 hr and +6 hr panels replay exactly what "now" showed, because those leads are
whole multiples of a short cycle. A nowcast projects the current system forward
through the rest of its life; it does not predict the next one.

### It is scored by the real model

The simulated region is not a canned risk map. Its terrain is generated once —
deterministically, in the same physical units as the Stage 1 tensor — and then
the *actual trained network* runs over it to produce susceptibility, exactly as
it does for Mumbai. Only the inputs are invented; the inference, the hazard model
and the risk weights are the same code path.

### The feed clock

`RAINSHIELD_SIM_CADENCE` (default: the live feed's `RAINSHIELD_CACHE_TTL`) is how
often a simulated observation is issued, so the second region delivers on the
same rhythm the real one does rather than a rhythm of its own.

A background thread issues them whether or not anyone is asking. Lazy refresh on
request would have been enough for correctness, but a dashboard that is merely
*open* would then see nothing arrive — the feed has to be a stream, not a side
effect of someone clicking. Every arrival, for both regions, is appended to a
bounded log that backs the **Live feed** view.

## The live feed view

`/api/observation?region=<id>` returns the current observation field by field,
and the dashboard's **Live feed** tab renders it:

* **Provenance** — region, source, whether it is live or generated, feed state,
  which model is serving, and the grid it covers.
* **Timing** — when the observation is valid, when the next one is due, and the
  age counting up against the cadence. Every timestamp is given in **both UTC and
  the region's own zone**, with the offset and zone abbreviation.
* **Fields** — every channel the model is about to read, with units and its
  min/mean/max across the grid, split into what the upstream *served*, what is
  *derived* from it, and the *static* layers. The rainfall fields break down per
  lead time.
* **Arrivals** — the log of observations that have actually landed, newest
  first, each with its timestamp and what was in it.

> **Timestamps used to lie.** The header clock rendered the *browser's* local
> time and then labelled it IST regardless of where the browser was, so an
> operator outside India read a time hours off under a label saying otherwise.
> The backend knows each region's IANA zone and now says so explicitly; the
> client formats in that zone rather than assuming.

## Layout

```
backend/
  rainshield/            the serving package
    config.py            primary geometry, channel order, risk weights, tiers
    regions.py           the region registry + the generated terrain
    grid.py              cell geometry, wards, static layers, cached per region
    ingest/              Open-Meteo + MET Norway, synthetic fallback, the storm
                         simulator, the arrival log and the feed clock
    models/              network definition, torch-free checkpoint reader + forward pass
    hazard.py            susceptibility × rainfall → probability, depth, onset
    hydro/               tides, drainage terrain, catchments, pumping, the solver
    risk.py              composite score, tiers, ward roll-ups
    service.py           the payloads the dashboard consumes
    api/app.py           FastAPI routes
  pipeline/              the offline stages, runnable from any directory
    stage0_01..10        the ten aligned raster layers + the ground-truth mask
    stage1_build_tensor  stacks them into (10, 45, 39)
    stage2_train         trains RainShieldNet, saves weights + risk raster
    stage3_dashboard     the 4-panel validation figure
    infer_realtime       standalone live scoring
  tests/                 177 tests: checkpoint, numpy/torch equivalence, ingest,
                         hazard, API, the region registry, the feed, the drainage
                         balance and the solver's mass closure
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
accumulation by antecedent soil wetness and drainage capacity.

**This is the default path, and it conserves nothing.** Every cell is evaluated
independently, so rain landing on a hillside raises that hillside's flood
probability and never arrives in the basin below; a pumped cell is no drier than
its neighbour; water does not move. `RAINSHIELD_SOLVER=physics` swaps it for a
mass-conserving solver — see
[Physics](#physics-drainage-pumping-and-routing).

Composite risk then follows the architecture spec and is tunable in `config.py`:

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
pass in NumPy alone, matching torch to ~2 × 10⁻⁶. Attention is computed a block
of query rows at a time: the 45 × 39 grid is a 1755-token sequence, so a full
score matrix is 1755 × 1755, and materialising it three layers deep peaked at
~104 MB per forward pass — enough to get the worker OOM-killed on Render's
512 MB free instance while `/api/forecast` and `/api/series` ran together.
Softmax is independent per row, so blocking is **bit-identical**, and it is
also faster because the blocks fit in cache: peak allocation drops to 12.8 MB
and a forward pass from 0.46 s to 0.29 s. For a 175k-parameter model on
one 45 × 39 grid, torch bought nothing and cost a ~2.5 GB dependency and a slow
cold start. Torch is still needed to *train* — see `requirements-dev.txt`, which
also runs the equivalence test.

## Physics: drainage, pumping and routing

A pure CNN prediction is not a flood model. Nothing in it conserves mass, water
never flows between cells, and rain on a slope vanishes where it fell instead of
arriving downhill. Two stages address that, and **the trained network stays in
the loop in both** — in the role it can honestly fill.

### Stage A — catchment mass balance and pumping

`rainshield/hydro/` answers the operational question directly, per catchment:

```
inflow  = (rainfall − infiltration) × area            [m³/s]
supply  = tide-gated gravity outfall + installed pumps
deficit = inflow − supply  →  N more pumps of 6 m³/s
```

It is additive: nothing here feeds back into `hazard.py`, so it changes no
number already on the board. `GET /api/drainage` serves it and the **Drainage**
tab renders it.

**The seven real BRIMSTOWAD stations** are modelled at their real locations —
Haji Ali, Love Grove, Cleveland Bunder, Britannia, Gazdhar Bandh, Irla and
Mogra, 180 m³/s installed. Capacities are **estimates**, assembled from public
reporting of pump counts at a nominal 6 m³/s per unit, and every one carries a
`capacityBasis` string the API serves and the dashboard prints. Outfall invert
levels are a weaker estimate still, and say so.

**Tide gating is the mechanism, not a detail.** Mumbai's gravity outfalls shut
when the sea rises above their inverts, and both 2005 and 2017 were extreme rain
on a high tide. A four-constituent harmonic model (M2, S2, K1, O1) gives the
spring–neap cycle and the diurnal inequality — a 4.6 m spring range over a
30-day span of 0.12–4.97 m above chart datum, the right character for Apollo
Bandar. The answer genuinely flips:

| Rainfall | Low water | High water |
| --- | --- | --- |
| 25 mm/hr | sufficient | sufficient |
| 50 mm/hr (design standard) | sufficient | **3 of 7 catchments short** |
| 100 mm/hr | 3 of 7 short | **7 of 7 short, +30 pumps** |

Supply collapses from 320 to 180 m³/s as the gates shut. The tide slider on the
Drainage tab pins sea level, so this is one drag away.

> **Why the pumped service areas are design-derived.** Working back from
> installed capacity at BRIMSTOWAD's 50 mm/hr standard, these stations were
> built for catchments of 1.3–2.6 km². One cell of this grid is 0.94 km² — an
> engineered catchment is *smaller than the model's resolution*. Asked for
> topographic catchments within 1 km of each station, D8 returns nothing;
> relaxed to 4.5 km it returns basins 5–25× too large, because Mumbai has on the
> order of a hundred outfalls and only seven are pumped, so attributing a
> coastal stretch to one station hands it every other outfall's water. That
> produced a headline of 3,194 extra pumps.
>
> So terrain decides *which* cells — a cell is eligible only if its own flow path
> reaches the coast near that station — and the design standard decides *how
> many*. One consequence bounds what the model can conclude: because service
> areas are derived from capacity, every station is by construction sized for its
> own design standard. This cannot discover that a station is under-built for
> what it was designed for. It can say whether rain exceeds the standard, and how
> much of the margin the tide takes.

Land outside those areas is reported with its inflow and **no capacity figure at
all**, rather than a deficit against a capacity that was never modelled.

### Stage B — distributed routing

`RAINSHIELD_SOLVER=physics` replaces the hazard heuristic with a mass-conserving
finite-volume diffusive-wave solver:

```
∂h/∂t + ∇·q = R − I − P − D
q = −(1/n) · h^(5/3) · ∇(z+h) / |∇(z+h)|^(1/2)
```

Fluxes are computed on cell faces and applied with opposite signs to the two
cells sharing a face, so water removed from one is exactly the water added to
the other. **Mass conservation is a property of the discretisation, not a
penalty term.** The coast is an **open boundary, tide-gated**: land cells
adjacent to the sea discharge over a weir driven by head over sea level, and the
flap gate shuts rather than reversing when the sea is higher. A no-flux coast
would pond water against the shoreline exactly where the city drains.

One solve gives every lead time from a single trajectory, so "+3 hr" is genuinely
the state "+1 hr" evolved into — and water can *recede* when the rain stops,
which a per-lead response curve cannot represent. A full 6-hour solve is ~160 ms.

**Where the network sits.** The solver needs two parameters it cannot measure at
1 km, neither of which is in any raster the project has:

```
depression storage   d = d_min + (d_max − d_min)·s    where water ponds before routing
drain removal rate   k = k_max·(1 − s)                how badly the drains cope
```

`s` is the network's susceptibility — a dimensionless 0–1 statement about where
water collects and lingers, which is exactly what it genuinely learned. Manning's
n comes from built density instead, because roughness is a physical property the
terrain layers already describe. **Depth is never read from the network**; it
comes from conservation of mass over terrain. This is also the socket that gets
retrained when observed inundation exists, and nothing else has to change.

### Mass closure instead of a PDE residual

The solve tallies every volume that entered or left and reports the closure
error — the governing equation integrated over the whole domain and the whole
run. It comes out at **~3 × 10⁻¹⁵**, machine precision, and the **Hazard model**
panel on the Risk tab prints it with the volumes behind it. That is a checkable
claim, unlike "physics-informed".

### No strict PINN, deliberately

A residual-loss PINN has to be *trained*, and the Stage 0 target is
`elevation ≤ 12 AND slope ≤ 1.5` on a single grid at one timestep — with both as
input channels. There is nothing to train a residual against. A hard-constrained
solver is strictly stronger anyway: mass conservation exact by construction beats
mass conservation approximately penalised.

### What this is not

1 km is **catchment scale, not street scale**. Real BRIMSTOWAD hydraulic
modelling runs at 10–30 m on the surveyed drain layout. Nothing here supports a
claim about street-level inundation. Manning's n, infiltration rates, pump
capacities, outfall inverts, the depression-storage range and the tidal phases
are all **uncalibrated estimates**. The model is *defensible* — it conserves
mass, and responds to terrain, tide and pumping the way the real system does —
but it is **not validated** against a gauged flood.

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
| `GET /health` | model state, provider, and every region's feed |
| `GET /api/regions` | the regions on offer, live and simulated |
| `GET /api/region` | static grid, wards, terrain and exposure layers — fetch once |
| `GET /api/observation` | the current observation field by field, with timestamps |
| `GET /api/forecast?lead=` | scored grid at one lead time + region and ward roll-ups |
| `GET /api/series` | region-wide trend across every lead time |
| `GET /api/drainage` | catchment mass balance, pumping capacity and tide state |
| `GET /api/cell/{row}/{col}` | one cell across every lead time |
| `POST /api/refresh` | drop the cached observation and re-pull |

Every endpoint except `/api/regions` takes `?region=<id>`; omitting it means
`mumbai`. An unknown id is a 404 rather than a silent fallback.

The what-if sliders are query parameters on the forecast endpoints:
`extra_rainfall` (mm), `soil_saturation` (0.5–1.5), `drainage_capacity`
(0.3–1.2). Cell payloads are columnar — one array per metric, flattened
row-major, **row 0 is the northern edge** — which is far lighter than 1755
GeoJSON features per refresh. Interactive docs at `/docs`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `RAINSHIELD_PROVIDER` | `openmeteo` | preferred live source (`openmeteo`, `metno`); the others still follow as fallbacks. `synthetic` for an offline demo. Ignored by simulated regions, which never call out |
| `RAINSHIELD_CACHE_TTL` | `600` | seconds an observation is reused |
| `RAINSHIELD_HTTP_TIMEOUT` | `10` | per-request upstream timeout, seconds |
| `RAINSHIELD_FETCH_BUDGET` | `12` | how long a request waits for an in-flight refresh before serving the previous observation |
| `RAINSHIELD_SIM_CADENCE` | `RAINSHIELD_CACHE_TTL` | seconds between simulated observations |
| `RAINSHIELD_SIM_PERIOD` | `90` | minutes for one full landfall cycle |
| `RAINSHIELD_MESH` | `5` | upstream sample mesh per axis |
| `RAINSHIELD_CORS_ORIGINS` | `*` | comma-separated allowed origins |
| `RAINSHIELD_PROCESSED_DIR` | `./processed_data` | weights and Stage 1 tensor |
| `RAINSHIELD_FORCE_ANALYTICAL` | unset | skip the network, use the analytical fallback |
| `RAINSHIELD_SOLVER` | `heuristic` | hazard path. `physics` routes water with the mass-conserving solver; it moves every number on the board, so it is opt-in |
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

> **A cold start is not a failure, and the client no longer reports it as one.**
> Render's own dashboard warns that waking a free instance "can delay requests
> by 50 seconds or more", which the client's original 45 s budget expired
> before — so the first load after any quiet spell reliably showed "Cannot
> reach the inference API" against a backend that was fine. The budget is now
> 90 s and a timeout or dropped connection is retried once, with the board
> saying it is waking the API rather than showing a spinner. A 4xx or 5xx is
> never retried: that is a real answer from a running server. If the error card
> does appear, it means the retry already happened and the problem is not a
> cold start.

> **The blueprint is not what Render is running.** The `rainshield-api` service
> was created by hand rather than from `render.yaml`, so Render never reads this
> file: it was pinned to branch `sneha` with no health check path while the
> blueprint claimed `main` and `/health`. `sneha` stopped receiving commits at
> PR #7, so the deployed API predated `/api/regions` and `/api/observation` — a
> current dashboard calling a four-merge-old backend, which is why the region
> switcher and the Live feed tab vanished without any error on the board
> (`useDashboard` swallows the region-list failure by design). Editing
> `render.yaml` does not move the deploy; the branch must be changed in
> Render → Settings → Build & Deploy, or the service adopted into the blueprint.

**Frontend (Vercel).** For the record, Vercel was never the problem: the project
builds with the `vite` preset from `main`, and every merge to `main` has produced
a READY production deployment. When the board looks stale, check which commit
*Render* is on before suspecting the bundle. `vercel.json` now pins the preset,
install and build commands and the output directory so the build is reproducible
from the repo rather than from dashboard settings — the same reasoning that puts
`VITE_API_BASE` in `.env.production`.

### Why the first load used to take minutes

Four things compounded, and all four are fixed:

* **met.no was fetched serially.** A 3 × 3 mesh is nine HTTP requests, and they
  ran one after another — so an upstream that was timing out cost nine whole
  timeouts back to back, minutes of it, before the fallback chain gave up.
  They now go out in parallel, so the chain costs one timeout, not nine.
* **There was no single-flight.** The dashboard asks for `/api/forecast` and
  `/api/series` in parallel and the warm-up thread runs alongside them, so a
  cold cache had three callers each walking the whole provider chain at once —
  tripling load on an upstream that rate-limits *per IP*, which is exactly what
  makes it slow. One refresh now runs per region and the others wait on it.
* **Requests waited for the network.** A refresh now runs on a background
  thread and a request waits at most `RAINSHIELD_FETCH_BUDGET` seconds for it,
  then serves the last good observation — flagged degraded and stale — instead
  of holding the connection open. A slow upstream makes the board *older*, not
  permanently blank.
* **The client had no timeout.** It waited forever, so a slow backend rendered
  as an endless spinner with no explanation. It now bounds the wait and says
  what happened.

`RAINSHIELD_HTTP_TIMEOUT` also dropped from 25 s to 10 s: both feeds answer in
well under a second when healthy, so a long timeout only buys a longer wait on
the days they are down — the days the board most needs to stay usable.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests/ -q
```

Both hazard paths are covered: the suite passes with `RAINSHIELD_SOLVER`
unset and with it set to `physics`.

Covers the torch-free checkpoint reader against `torch.load`, the NumPy forward
pass against PyTorch, Open-Meteo and MET Norway parsing (including null handling
and the latitude orientation), the provider fallback chain, hazard monotonicity,
the API contract, the region registry, the generated terrain, the storm's tier
coverage, the per-region cache and the arrival log.

The four PyTorch-dependent tests skip without `torch` installed; everything else
runs from `requirements.txt` plus `pytest` and `httpx`.

## Stack

Backend: FastAPI, NumPy, SciPy. Training: PyTorch, rasterio, GeoPandas,
scikit-learn. Frontend: React 18, TypeScript, Vite, Tailwind, MapLibre GL,
Recharts.
