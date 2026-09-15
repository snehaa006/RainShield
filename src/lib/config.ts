import type { AlertTier, Confidence, LeadTime } from '@/types';

/**
 * Demo region. The pipeline is grid-based and config-driven: pointing it at a
 * different district is a data-onboarding change, not a redesign.
 */
/**
 * The analysis grid, mirroring backend/rainshield/config.py. These are the
 * exact bounds of processed_data/dem_1km_master.tif — the raster every model
 * layer is aligned to — so cell polygons drawn here land on the same ground
 * the network was trained on. Row 0 is the NORTHERN edge.
 */
export const REGION = {
  name: 'Mumbai Suburban',
  state: 'Maharashtra',
  /** [west, south, east, north] */
  bounds: [72.74986, 18.8459, 73.1002, 19.25014] as [number, number, number, number],
  centre: [72.92503, 19.04802] as [number, number],
  /** 1755 cells of ~1 km. */
  cols: 39,
  rows: 45,
};

/**
 * Base URL of the inference API. Vite inlines VITE_* at build time, so changing
 * this on the host requires a redeploy. Render's fromService gives a bare
 * hostname, hence the scheme fix-up; empty means same-origin (the dev proxy).
 */
export const API_BASE = normaliseApiBase(import.meta.env.VITE_API_BASE);

function normaliseApiBase(raw: string | undefined): string {
  const value = (raw ?? '').trim().replace(/\/$/, '');
  if (!value) return '';
  return /^https?:\/\//.test(value) ? value : `https://${value}`;
}

/** How often the dashboard re-pulls the forecast, ms. */
export const REFRESH_INTERVAL_MS = 5 * 60 * 1000;

/** Risk weights from the system architecture spec. Tunable against past events. */
export const RISK_WEIGHTS = {
  rainfallSeverity: 0.35,
  floodProbability: 0.3,
  waterDepth: 0.2,
  populationExposure: 0.1,
  criticalInfra: 0.05,
} as const;

/** Lower bound of each warning tier on the 0-1 composite risk score. */
export const TIER_THRESHOLDS: { tier: AlertTier; min: number }[] = [
  { tier: 'CRITICAL', min: 0.75 },
  { tier: 'WARNING', min: 0.5 },
  { tier: 'WATCH', min: 0.25 },
  { tier: 'NORMAL', min: 0 },
];

export const TIER_COLORS: Record<AlertTier, string> = {
  NORMAL: '#22c55e',
  WATCH: '#eab308',
  WARNING: '#f97316',
  CRITICAL: '#ef4444',
};

export const TIER_LABELS: Record<AlertTier, string> = {
  NORMAL: 'Normal',
  WATCH: 'Watch',
  WARNING: 'Warning',
  CRITICAL: 'Critical',
};

export const CONFIDENCE_COLORS: Record<Confidence, string> = {
  LOW: '#94a3b8',
  MEDIUM: '#38bdf8',
  HIGH: '#2dd4bf',
};

export const LEAD_TIMES: LeadTime[] = [0, 30, 60, 120, 180, 360];

export const LEAD_TIME_LABELS: Record<LeadTime, string> = {
  0: 'Now',
  30: '+30 min',
  60: '+1 hr',
  120: '+2 hr',
  180: '+3 hr',
  360: '+6 hr',
};

/** Rainfall intensity colour ramp, mm/hr breakpoints. */
export const RAINFALL_RAMP: { value: number; color: string }[] = [
  { value: 0, color: '#0b1220' },
  { value: 2.5, color: '#1e3a5f' },
  { value: 7.5, color: '#2563eb' },
  { value: 15, color: '#22d3ee' },
  { value: 30, color: '#4ade80' },
  { value: 50, color: '#facc15' },
  { value: 75, color: '#f97316' },
  { value: 100, color: '#dc2626' },
];

/** Water depth colour ramp, metres. */
export const DEPTH_RAMP: { value: number; color: string }[] = [
  { value: 0, color: '#0b1220' },
  { value: 0.15, color: '#155e75' },
  { value: 0.3, color: '#0891b2' },
  { value: 0.6, color: '#6366f1' },
  { value: 1.0, color: '#a855f7' },
  { value: 1.5, color: '#ec4899' },
];

export const DEFAULT_WHAT_IF = {
  extraRainfall: 0,
  soilSaturation: 1,
  drainageCapacity: 1,
};

/** Feed labels for the ingestion health strip, keyed to the provider name. */
export const FEED_LABELS: Record<string, string> = {
  openmeteo: 'Open-Meteo live feed',
  metno: 'MET Norway live feed',
  synthetic: 'Synthetic demo field',
  'simulated-storm': 'Simulated storm feed',
};
