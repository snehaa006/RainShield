/**
 * Client for the RainShield inference API.
 *
 * This replaces the old synthetic `lib/forecast.ts`: every number the dashboard
 * shows now comes from the backend, which pulls live weather and runs the
 * trained CNN-transformer. The payloads are columnar — one array per metric,
 * flattened row-major over the grid — because sending 1755 GeoJSON features per
 * refresh is far heavier than sending the numbers and building geometry here.
 */

import { API_BASE } from '@/lib/config';
import type { AlertTier, Confidence, FeedStatus, LeadTime, ModelStatus, WhatIfSettings } from '@/types';

export interface RegionPayload {
  region: {
    name: string;
    state: string;
    bounds: [number, number, number, number];
    centre: [number, number];
    rows: number;
    cols: number;
    cellCount: number;
    cellWidth: number;
    cellHeight: number;
  };
  leadTimes: LeadTime[];
  wards: { id: string; name: string; lon: number; lat: number }[];
  cells: {
    lon: number[];
    lat: number[];
    elevation: number[];
    slope: number[];
    population: number[];
    infraProximity: number[];
    landUse: string[];
    wardIndex: number[];
  };
}

export interface ForecastPayload {
  lead: LeadTime;
  generatedAt: string;
  confidence: Confidence;
  isSimulating: boolean;
  observation: FeedStatus;
  model: {
    loaded: boolean;
    backend: string;
    runtime: string;
    weights_present: boolean;
    error: string | null;
  };
  cells: {
    risk: number[];
    floodProbability: number[];
    susceptibility: number[];
    rainfallIntensity: number[];
    rainfall3h: number[];
    waterDepth: number[];
    timeToInundation: (number | null)[];
  };
  riskComponents: Record<string, number[]>;
  summary: RegionSummary;
  wards: WardRollup[];
}

export interface RegionSummary {
  tier: AlertTier;
  peakRisk: number;
  meanRisk: number;
  peakRainfall: number;
  meanRainfall: number;
  peakRainfall3h: number;
  peakFloodProbability: number;
  peakDepth: number;
  populationAtRisk: number;
  floodedArea: number;
  leadTime: number | null;
}

export interface WardRollup {
  id: string;
  name: string;
  tier: AlertTier;
  risk: number;
  peakFloodProbability: number;
  peakWaterDepth: number;
  timeToInundation: number | null;
  confidence: Confidence;
  populationAtRisk: number;
  cellCount: number;
  floodedCellCount: number;
}

/** Zeroed summary used before the first forecast lands. */
export const EMPTY_SUMMARY: RegionSummary = {
  tier: 'NORMAL',
  peakRisk: 0,
  meanRisk: 0,
  peakRainfall: 0,
  meanRainfall: 0,
  peakRainfall3h: 0,
  peakFloodProbability: 0,
  peakDepth: 0,
  populationAtRisk: 0,
  floodedArea: 0,
  leadTime: null,
};

export interface SeriesPayload {
  observation: FeedStatus;
  isSimulating: boolean;
  series: SeriesPoint[];
}

export interface SeriesPoint {
  lead: LeadTime;
  rainfall: number;
  peakRainfall: number;
  peakFloodProbability: number;
    meanFloodProbability: number;
  depth: number;
  peakRisk: number;
}

/** Thrown for any non-2xx response or transport failure, with a readable cause. */
export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = 'ApiError';
  }
}

function whatIfParams(whatIf: WhatIfSettings): Record<string, string> {
  return {
    extra_rainfall: String(whatIf.extraRainfall),
    soil_saturation: String(whatIf.soilSaturation),
    drainage_capacity: String(whatIf.drainageCapacity),
  };
}

async function request<T>(
  path: string,
  params: Record<string, string> = {},
  signal?: AbortSignal,
): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value));

  let response: Response;
  try {
    response = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError(
      `Cannot reach the inference API at ${API_BASE || window.location.origin}. ` +
        'Check that the backend is running and VITE_API_BASE points at it.',
    );
  }

  if (!response.ok) {
    // FastAPI puts the useful message in `detail`.
    const detail = await response
      .json()
      .then((body) => (typeof body?.detail === 'string' ? body.detail : null))
      .catch(() => null);
    throw new ApiError(detail ?? `${path} failed (HTTP ${response.status})`, response.status);
  }

  return response.json() as Promise<T>;
}

export const fetchRegion = (signal?: AbortSignal) =>
  request<RegionPayload>('/api/region', {}, signal);

export const fetchForecast = (lead: LeadTime, whatIf: WhatIfSettings, signal?: AbortSignal) =>
  request<ForecastPayload>('/api/forecast', { lead: String(lead), ...whatIfParams(whatIf) }, signal);

export const fetchSeries = (whatIf: WhatIfSettings, signal?: AbortSignal) =>
  request<SeriesPayload>('/api/series', whatIfParams(whatIf), signal);

export const fetchHealth = (signal?: AbortSignal) =>
  request<{ status: string; model: ModelStatus; provider: string; observation: FeedStatus }>(
    '/health',
    {},
    signal,
  );

/** Drop the backend's cached observation and pull the live feed again. */
export async function refreshFeed(): Promise<void> {
  const url = new URL(`${API_BASE}/api/refresh`, window.location.origin);
  const response = await fetch(url, { method: 'POST' });
  if (!response.ok) throw new ApiError(`Refresh failed (HTTP ${response.status})`, response.status);
}
