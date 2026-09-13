import { GRID, cellPolygon } from '@/lib/grid';
import { REGION } from '@/lib/config';
import { clamp, fbm, logistic } from '@/lib/math';
import { scoreRisk, tierFor } from '@/lib/riskEngine';
import type {
  CellForecast,
  Confidence,
  GridCellStatic,
  LeadTime,
  ScoredCell,
  Scenario,
  WhatIfSettings,
} from '@/types';

/**
 * Stand-in for the AI/ML engine (nowcasting -> ensemble fusion -> inundation).
 *
 * Every function here is pure and synchronous so it can be swapped for an API
 * client without touching the UI: `getForecast` is the single seam where real
 * model output will arrive.
 */
export function getForecast(
  scenario: Scenario,
  lead: LeadTime,
  whatIf: WhatIfSettings,
): ScoredCell[] {
  return GRID.map((cell) => {
    const forecast = forecastCell(cell, scenario, lead, whatIf);
    const risk = scoreRisk(cell, forecast);
    return { ...cell, ...forecast, risk, tier: tierFor(risk.total) };
  });
}

/** Rainfall time series for a single cell across every lead time. */
export function getCellSeries(
  cell: GridCellStatic,
  scenario: Scenario,
  leads: LeadTime[],
  whatIf: WhatIfSettings,
) {
  return leads.map((lead) => ({
    lead,
    ...forecastCell(cell, scenario, lead, whatIf),
  }));
}

/** Region-mean rainfall and flood probability across lead times, for the trend chart. */
export function getRegionSeries(
  scenario: Scenario,
  leads: LeadTime[],
  whatIf: WhatIfSettings,
) {
  return leads.map((lead) => {
    const cells = GRID.map((cell) => forecastCell(cell, scenario, lead, whatIf));
    const mean = (pick: (f: CellForecast) => number) =>
      cells.reduce((sum, f) => sum + pick(f), 0) / cells.length;

    return {
      lead,
      rainfall: round(mean((f) => f.rainfallIntensity), 1),
      peakRainfall: round(Math.max(...cells.map((f) => f.rainfallIntensity)), 1),
      peakFloodProbability: round(Math.max(...cells.map((f) => f.floodProbability)), 3),
      depth: round(mean((f) => f.waterDepth), 3),
    };
  });
}

function forecastCell(
  cell: GridCellStatic,
  scenario: Scenario,
  lead: LeadTime,
  whatIf: WhatIfSettings,
): CellForecast {
  const nowcast = nowcastRainfall(cell, scenario, lead);
  // Injected rainfall is spread evenly across the 3-hour accumulation window,
  // so the displayed intensity stays consistent with the flood response.
  const rainfallIntensity = nowcast + whatIf.extraRainfall / 3;
  const rainfall3h = accumulate(nowcast, lead) + whatIf.extraRainfall;
  const floodProbability = inundationProbability(cell, rainfall3h, whatIf);
  const waterDepth = expectedDepth(cell, rainfall3h, floodProbability, whatIf);

  return {
    rainfallIntensity: round(rainfallIntensity, 1),
    rainfall3h: round(rainfall3h, 1),
    floodProbability: round(floodProbability, 3),
    waterDepth: round(waterDepth, 2),
    timeToInundation: timeToInundation(floodProbability, rainfallIntensity, lead),
    confidence: confidenceFor(cell, lead, scenario),
  };
}

/** Model 1: storm cell advecting across the grid, sampled at each lead time. */
function nowcastRainfall(cell: GridCellStatic, scenario: Scenario, lead: LeadTime): number {
  const hours = lead / 60;
  const nx = cell.col / REGION.cols;
  const ny = cell.row / REGION.rows;

  // Storm tracks north-east at roughly 20 km/h.
  const cx = scenario.centre[0] + hours * 0.05;
  const cy = scenario.centre[1] + hours * 0.04;

  const distance = Math.hypot(nx - cx, ny - cy);
  const core = Math.exp(-(distance ** 2) / 0.045);

  // Intensity peaks around +2 hr then decays as the band moves through.
  const lifecycle = Math.exp(-(((hours - 1.8) / 2.4) ** 2));
  const texture = 0.55 + 0.9 * fbm(nx * 5 + hours, ny * 5 - hours, 91);
  // Orographic enhancement over the inland ridge.
  const orography = 1 + clamp(cell.elevation / 120, 0, 0.35);

  return clamp(62 * scenario.intensity * core * lifecycle * texture * orography, 0, 200);
}

/** Convert an instantaneous rate into a 3-hour accumulation for the lead time. */
function accumulate(intensity: number, lead: LeadTime): number {
  const persistence = 1.6 + (lead / 360) * 1.1;
  return intensity * persistence;
}

/** Model 3 (tabular branch): flood probability from rainfall and terrain. */
function inundationProbability(
  cell: GridCellStatic,
  rainfall3h: number,
  whatIf: WhatIfSettings,
): number {
  const imperviousness = IMPERVIOUSNESS[cell.landUse];
  const drainageDeficit = 1 / clamp(whatIf.drainageCapacity, 0.3, 1.2);

  const score =
    -5.8 +
    0.055 * rainfall3h * drainageDeficit * (0.7 + 0.5 * whatIf.soilSaturation) +
    1.9 * imperviousness +
    2.0 / (1 + cell.elevation / 6) +
    1.6 / (1 + cell.distanceToDrainage) -
    0.11 * cell.slope;

  return clamp(logistic(score));
}

/** Expected standing-water depth in metres, conditional on flooding. */
function expectedDepth(
  cell: GridCellStatic,
  rainfall3h: number,
  floodProbability: number,
  whatIf: WhatIfSettings,
): number {
  const basinFactor = 1 / (1 + cell.elevation / 4) + 0.6 / (1 + cell.distanceToDrainage);
  const drainageDeficit = 1 / clamp(whatIf.drainageCapacity, 0.3, 1.2);
  return clamp(
    floodProbability * basinFactor * (rainfall3h / 95) * drainageDeficit * 1.2,
    0,
    3,
  );
}

/** Minutes until water is expected to reach the cell, or null when it is not. */
function timeToInundation(
  floodProbability: number,
  intensity: number,
  lead: LeadTime,
): number | null {
  if (floodProbability < 0.35) return null;
  const onset = 210 - 150 * floodProbability - Math.min(60, intensity * 0.5);
  return Math.max(10, Math.round((lead + onset) / 5) * 5);
}

/** Model 2: ensemble agreement degrades with lead time and in data-sparse cells. */
function confidenceFor(cell: GridCellStatic, lead: LeadTime, scenario: Scenario): Confidence {
  const agreement =
    0.92 -
    (lead / 360) * 0.38 -
    fbm(cell.col / 4, cell.row / 4, 41) * 0.18 +
    (scenario.isHistorical ? 0.12 : 0);

  if (agreement >= 0.75) return 'HIGH';
  if (agreement >= 0.58) return 'MEDIUM';
  return 'LOW';
}

const IMPERVIOUSNESS: Record<GridCellStatic['landUse'], number> = {
  'urban-dense': 0.92,
  urban: 0.75,
  periurban: 0.5,
  vegetation: 0.2,
  water: 1,
};

/** GeoJSON feature collection of the scored grid, consumed by the map. */
export function toGeoJson(cells: ScoredCell[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: cells.map((cell) => ({
      type: 'Feature',
      id: cell.col * REGION.rows + cell.row,
      geometry: { type: 'Polygon', coordinates: [cellPolygon(cell)] },
      properties: {
        id: cell.id,
        wardId: cell.wardId,
        rainfall: cell.rainfallIntensity,
        rainfall3h: cell.rainfall3h,
        floodProbability: cell.floodProbability,
        depth: cell.waterDepth,
        risk: cell.risk.total,
        tier: cell.tier,
        population: cell.population,
      },
    })),
  };
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
