import { RISK_WEIGHTS, TIER_THRESHOLDS } from '@/lib/config';
import { clamp } from '@/lib/math';
import type {
  AlertTier,
  CellForecast,
  Confidence,
  GridCellStatic,
  RiskScore,
  ScoredCell,
  Ward,
  WardSummary,
} from '@/types';

/** Normalisation ceilings used to map raw model output onto the 0-1 risk axes. */
const NORMALISERS = {
  /** mm over 3 hr — the spec's P(>100mm/3hr) trigger. */
  rainfall3h: 100,
  /** metres of standing water treated as a fully saturated hazard. */
  waterDepth: 1.5,
  /** people per km² treated as maximum exposure. */
  population: 40_000,
};

/**
 * Composite risk score:
 *   0.35 rainfall severity + 0.30 flood probability + 0.20 water depth
 * + 0.10 population exposure + 0.05 critical-infrastructure proximity
 */
export function scoreRisk(cell: GridCellStatic, forecast: CellForecast): RiskScore {
  const components = {
    rainfallSeverity: clamp(forecast.rainfall3h / NORMALISERS.rainfall3h),
    floodProbability: clamp(forecast.floodProbability),
    waterDepth: clamp(forecast.waterDepth / NORMALISERS.waterDepth),
    populationExposure: clamp(cell.population / NORMALISERS.population),
    criticalInfra: clamp(cell.criticalInfraProximity),
  };

  const total = (Object.keys(components) as (keyof typeof components)[]).reduce(
    (sum, key) => sum + components[key] * RISK_WEIGHTS[key],
    0,
  );

  return { total: clamp(total), components };
}

/** Map a composite risk score onto the four-tier warning ladder. */
export function tierFor(risk: number): AlertTier {
  return (TIER_THRESHOLDS.find((t) => risk >= t.min) ?? TIER_THRESHOLDS.at(-1)!).tier;
}

const CONFIDENCE_RANK: Record<Confidence, number> = { LOW: 0, MEDIUM: 1, HIGH: 2 };

/** Roll cell-level output up to the ward the operator actually acts on. */
export function summariseWard(ward: Ward, cells: ScoredCell[]): WardSummary {
  const flooded = cells.filter((c) => c.floodProbability >= 0.5);
  const risk = cells.length
    ? // Ward risk leans on its worst cells: a single flooded pocket still matters.
      0.6 * Math.max(...cells.map((c) => c.risk.total)) +
      0.4 * (cells.reduce((s, c) => s + c.risk.total, 0) / cells.length)
    : 0;

  const times = cells
    .map((c) => c.timeToInundation)
    .filter((t): t is number => t !== null);

  const confidence = cells.reduce<Confidence>((worst, c) => {
    return CONFIDENCE_RANK[c.confidence] < CONFIDENCE_RANK[worst] ? c.confidence : worst;
  }, 'HIGH');

  return {
    ward,
    tier: tierFor(risk),
    risk,
    peakFloodProbability: cells.length ? Math.max(...cells.map((c) => c.floodProbability)) : 0,
    peakWaterDepth: cells.length ? Math.max(...cells.map((c) => c.waterDepth)) : 0,
    timeToInundation: times.length ? Math.min(...times) : null,
    confidence,
    populationAtRisk: Math.round(
      flooded.reduce((sum, c) => sum + c.population * c.floodProbability, 0),
    ),
    cellCount: cells.length,
    floodedCellCount: flooded.length,
  };
}

/** Region-wide headline numbers for the KPI strip. */
export function summariseRegion(cells: ScoredCell[]) {
  const peakRisk = cells.length ? Math.max(...cells.map((c) => c.risk.total)) : 0;
  const flooded = cells.filter((c) => c.floodProbability >= 0.5);
  const times = cells
    .map((c) => c.timeToInundation)
    .filter((t): t is number => t !== null);

  return {
    tier: tierFor(peakRisk),
    peakRisk,
    peakRainfall: cells.length ? Math.max(...cells.map((c) => c.rainfallIntensity)) : 0,
    peakDepth: cells.length ? Math.max(...cells.map((c) => c.waterDepth)) : 0,
    populationAtRisk: Math.round(
      flooded.reduce((sum, c) => sum + c.population * c.floodProbability, 0),
    ),
    floodedArea: flooded.length,
    leadTime: times.length ? Math.min(...times) : null,
  };
}
