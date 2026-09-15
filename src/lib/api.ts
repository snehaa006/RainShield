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
  CatchmentBalance,
  Confidence,
  FeedArrival,
  FeedField,
  FeedStatus,
  LeadTime,
  ModelStatus,
  PumpStationInfo,
  RegionDescriptor,
  SolverStatus,
  Stamp,
  StormPhase,
  TideState,
  WhatIfSettings,
} from '@/types';

export interface RegionPayload {
  region: RegionDescriptor;
  leadTimes: LeadTime[];
  /** Pumping stations inside the grid. Static geography, so it rides here. */
  stations: PumpStationInfo[];
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
  solver: SolverStatus;
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

/** The Stage A drainage assessment at one lead time. */
export interface DrainagePayload {
  lead: LeadTime;
  region: RegionDescriptor;
  observation: FeedStatus;
  isSimulating: boolean;
  tide: TideState;
  /** True when the tide was pinned rather than predicted. */
  tideOverridden: boolean;
  stations: PumpStationInfo[];
  /** Catchments with a modelled station — the only ones the totals cover. */
  catchments: CatchmentBalance[];
  /** Land draining to outfalls the model does not survey. No capacity claimed. */
  unpumped: CatchmentBalance | null;
  totals: {
    inflowCumecs: number;
    supplyCumecs: number;
    deficitCumecs: number;
    extraPumpsRequired: number;
    installedPumpCumecs: number;
    catchmentsInDeficit: number;
    catchmentCount: number;
    sufficient: boolean;
    pumpUnitCumecs: number;
    designIntensityMmHr: number;
  };
  cells: {
    /** Index into `stations`, or -1 where no modelled station drains the cell. */
    catchment: number[];
    sea: boolean[];
  };
  /** What this model can and cannot be read to say. Rendered, not hidden. */
  caveat: string;
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

/**
 * The drainage assessment.
 *
 * `tide` pins sea level in metres above chart datum instead of using the
 * harmonic prediction — the point of the control being that the answer to
 * "is there enough pumping capacity" genuinely changes between low and high
 * water. `pumpAvailability` scales installed capacity, for asking what a
 * station being down would cost.
 */
export const fetchDrainage = (
  lead: LeadTime,
  whatIf: WhatIfSettings,
  region?: string,
  tide?: number | null,
  pumpAvailability = 1,
  signal?: AbortSignal,
) =>
  request<DrainagePayload>(
    '/api/drainage',
    {
      lead: String(lead),
      ...whatIfParams(whatIf),
      ...regionParam(region),
      ...(tide == null ? {} : { tide: String(tide) }),
      ...(pumpAvailability === 1 ? {} : { pump_availability: String(pumpAvailability) }),
    },
    signal,
  );

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
