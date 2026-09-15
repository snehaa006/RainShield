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
import type {
  AlertTier,
  Confidence,
  FeedArrival,
  FeedField,
  FeedStatus,
  LeadTime,
  ModelStatus,
  RegionDescriptor,
  Stamp,
  StormPhase,
  WhatIfSettings,
} from '@/types';

export interface RegionPayload {
  region: RegionDescriptor;
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
  region: RegionDescriptor;
  storm: StormPhase | null;
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
  region: RegionDescriptor;
  observation: FeedStatus;
  isSimulating: boolean;
  series: SeriesPoint[];
}

/** Everything in the current observation, as the live-feed view renders it. */
export interface ObservationPayload {
  region: RegionDescriptor;
  observation: FeedStatus;
  model: {
    loaded: boolean;
    backend: string;
    runtime: string;
    weights_present: boolean;
    error: string | null;
  };
  storm: StormPhase | null;
  leadTimes: LeadTime[];
  channelOrder: string[];
  dynamicChannels: string[];
  fields: {
    observed: FeedField[];
    derived: FeedField[];
    static: FeedField[];
  };
  arrivals: FeedArrival[];
  servedAt: Stamp;
}

export interface RegionsPayload {
  regions: RegionDescriptor[];
  default: string;
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

/** Every forecast endpoint is scoped to a region; omitting it means the default. */
function regionParam(region?: string): Record<string, string> {
  return region ? { region } : {};
}

/**
 * How long to wait for a response before giving up, ms.
 *
 * The client used to wait indefinitely, so a backend that was merely slow — a
 * free-tier instance waking up, an upstream feed timing out — showed as a
 * spinner with no end and no explanation. The backend now bounds its own waits
 * too; this is the backstop for the request never arriving at all.
 */
const REQUEST_TIMEOUT_MS = 45_000;

/** A caller's own abort signal, plus our timeout, as one signal. */
function withTimeout(signal: AbortSignal | undefined, ms: number) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(new DOMException('timeout', 'TimeoutError')), ms);
  const onAbort = () => controller.abort(signal?.reason);
  if (signal) {
    if (signal.aborted) onAbort();
    else signal.addEventListener('abort', onAbort, { once: true });
  }
  return {
    signal: controller.signal,
    done: () => {
      window.clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
    },
  };
}

async function request<T>(
  path: string,
  params: Record<string, string> = {},
  signal?: AbortSignal,
): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value));

  const guard = withTimeout(signal, REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(url, { signal: guard.signal, headers: { Accept: 'application/json' } });
  } catch (cause) {
    // The caller aborting (a lead-time change, an unmount) is not an error.
    if (signal?.aborted) throw new DOMException('aborted', 'AbortError');
    if (cause instanceof DOMException && cause.name === 'TimeoutError') {
      throw new ApiError(
        `The inference API did not respond within ${REQUEST_TIMEOUT_MS / 1000}s. ` +
          'It may be waking from sleep — retry in a moment.',
      );
    }
    throw new ApiError(
      `Cannot reach the inference API at ${API_BASE || window.location.origin}. ` +
        'Check that the backend is running and VITE_API_BASE points at it.',
    );
  } finally {
    guard.done();
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

export const fetchRegions = (signal?: AbortSignal) =>
  request<RegionsPayload>('/api/regions', {}, signal);

export const fetchRegion = (region?: string, signal?: AbortSignal) =>
  request<RegionPayload>('/api/region', regionParam(region), signal);

export const fetchForecast = (
  lead: LeadTime,
  whatIf: WhatIfSettings,
  region?: string,
  signal?: AbortSignal,
) =>
  request<ForecastPayload>(
    '/api/forecast',
    { lead: String(lead), ...whatIfParams(whatIf), ...regionParam(region) },
    signal,
  );

export const fetchSeries = (whatIf: WhatIfSettings, region?: string, signal?: AbortSignal) =>
  request<SeriesPayload>('/api/series', { ...whatIfParams(whatIf), ...regionParam(region) }, signal);

export const fetchObservation = (region?: string, signal?: AbortSignal) =>
  request<ObservationPayload>('/api/observation', regionParam(region), signal);

export const fetchHealth = (signal?: AbortSignal) =>
  request<{ status: string; model: ModelStatus; provider: string; observation: FeedStatus }>(
    '/health',
    {},
    signal,
  );

/** Drop the backend's cached observation and pull the live feed again. */
export async function refreshFeed(region?: string): Promise<void> {
  const url = new URL(`${API_BASE}/api/refresh`, window.location.origin);
  if (region) url.searchParams.set('region', region);
  const response = await fetch(url, { method: 'POST' });
  if (!response.ok) throw new ApiError(`Refresh failed (HTTP ${response.status})`, response.status);
}

/** Operational alert endpoints. The backend owns alert lifecycle state. */
export interface AlertApiRecord {
  id: string;
  createdAt: string;
  updatedAt: string;
  status: 'UNDER_REVIEW' | 'APPROVED' | 'BROADCASTING' | 'ACTIVE' | 'RESOLVED' | 'CANCELLED';
  tier: AlertTier;
  region: RegionDescriptor;
  ward: WardRollup;
  reason: string[];
  channels: Record<string, number>;
  simulation: boolean;
}

export const fetchAlerts = (region?: string, signal?: AbortSignal) =>
  request<{ alerts: AlertApiRecord[] }>('/api/alerts', regionParam(region), signal);

async function alertAction(alertId: string, action: 'approve' | 'broadcast' | 'resolve' | 'cancel') {
  const response = await fetch(`${API_BASE}/api/alerts/${encodeURIComponent(alertId)}/${action}`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new ApiError(detail?.detail ?? `Alert ${action} failed (HTTP ${response.status})`, response.status);
  }
  return response.json() as Promise<AlertApiRecord>;
}

export const approveAlert = (alertId: string) => alertAction(alertId, 'approve');
export const broadcastAlert = (alertId: string) => alertAction(alertId, 'broadcast');
export const resolveAlert = (alertId: string) => alertAction(alertId, 'resolve');
export const cancelAlert = (alertId: string) => alertAction(alertId, 'cancel');
