# RainShield AI — Dashboard Prototype

Operator dashboard for the RainShield AI heavy-rainfall early-warning and inundation
prediction system (SIH26071, Team HydroNex).

This is the **dashboard layer only**. The AI/ML engine is not implemented yet: every
model output is produced by a deterministic synthetic data source behind a single,
clearly marked seam, so the real pipeline can be dropped in without touching the UI.

## Running it

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # typecheck + production bundle
```

### Basemap key

The basemap loads raster tiles from CARTO, which has required an API key since
August 2026 — without one the tiles carry an "API KEY REQUIRED" watermark. Keys are
free up to 5M tile requests/month: <https://carto.com/basemaps/apikey>.

```bash
cp .env.example .env.local     # then fill in VITE_BASEMAP_KEY
```

Two things to watch:

- **Vite inlines `VITE_*` values at build time.** Setting the variable on a hosting
  platform does nothing to an *existing* deployment — you have to redeploy so the key
  is baked into a fresh bundle. On Vercel: add it under Settings → Environment
  Variables for the right environment(s), then Redeploy with the build cache off.
- **CARTO's style paths are not uniform.** The voyager styles are nested under
  `rastertiles/`; the light and dark ones sit at the root. `rastertiles/dark_all`
  looks plausible but is not a valid style path. See `STYLE` in
  `src/components/map/mapStyle.ts`.

The map needs outbound network access for tiles. Without it the grid, wards and
overlays still render over a flat background — all model data is generated locally.

## What the dashboard does

| Area | Feature |
| --- | --- |
| Map | 1 km grid coloured by composite risk, rainfall intensity or flood depth; ward boundaries; OSM-style critical-infrastructure overlay; click any cell to inspect it |
| Forecast | Horizon scrubber across the nowcast lead times (now, +30 min, +1/2/3/6 hr) and a trend chart of peak/mean rainfall against peak flood probability |
| Alerts | Ward risk ranking, alert intelligence panel (probability, depth, time-to-inundation, ensemble confidence) and the four-tier Normal/Watch/Warning/Critical ladder |
| Simulation | What-if simulator — inject rainfall, change antecedent soil saturation and drainage capacity, and see population, flooded area and depth move against the unmodified forecast |
| Replay | Historical event scenarios (26 July 2005, Aug 2020) for validation demos |
| Dissemination | CAP 1.2 alert preview with XML output, plus the SMS / push / siren / authority-API channels it would fan out to (stubbed) |

## How it is put together

```
src/
  types/            Domain model — grid cells, forecasts, risk, wards, CAP
  lib/
    config.ts       Demo region, risk weights, tier thresholds, colour ramps, scenarios
    grid.ts         Static layers (DEM, LULC, population, infrastructure proximity)
    forecast.ts     ⟵ the ML seam: stands in for nowcasting → ensemble → inundation
    riskEngine.ts   Composite risk score, tier mapping, ward/region roll-ups
    infrastructure.ts, cap.ts, format.ts, math.ts
  hooks/
    useDashboard.tsx  Single state container: scenario, horizon, what-if, selection
  components/
    map/            MapLibre map, layer controls, legend
    panels/         Alert intelligence, ward list, what-if, inspector, exposure, CAP
    charts/         Nowcast trend, risk contribution breakdown
    ui/             Panel, tier badge, meter, slider
```

The risk score follows the architecture spec and is tunable in `lib/config.ts`:

```
Risk = 0.35 × rainfall_severity
     + 0.30 × flood_probability
     + 0.20 × water_depth
     + 0.10 × population_exposure
     + 0.05 × critical_infrastructure_proximity
```

Tiers: Normal < 0.25 ≤ Watch < 0.50 ≤ Warning < 0.75 ≤ Critical.

## Wiring in the real models

`lib/forecast.ts` exposes three pure functions — `getForecast`, `getCellSeries` and
`getRegionSeries`. They are the only place model output is produced. Replacing them
with an API client (and making `useDashboard` await the result) is the whole
integration:

- `nowcastRainfall` → Model 1, rainfall nowcasting (CNN + temporal transformer)
- `confidenceFor` → Model 2, ensemble/confidence fusion
- `inundationProbability` / `expectedDepth` / `timeToInundation` → Model 3, runoff & inundation

`lib/grid.ts` generates the static layers from seeded noise; those become real DEM,
LULC, census and OSM data loaded from the fusion engine's unified 1 km grid.

## Stack

React 18, TypeScript, Vite, Tailwind CSS, MapLibre GL, Recharts.
