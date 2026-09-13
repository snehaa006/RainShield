import type { AlertTier, Confidence, LeadTime, Scenario } from '@/types';

/**
 * Demo region. The pipeline is grid-based and config-driven: pointing it at a
 * different district is a data-onboarding change, not a redesign.
 */
export const REGION = {
  name: 'Mumbai Suburban',
  state: 'Maharashtra',
  /** [west, south, east, north] */
  bounds: [72.79, 19.0, 72.99, 19.22] as [number, number, number, number],
  centre: [72.89, 19.11] as [number, number],
  /** Grid resolution in cells; each cell is roughly 1 km across. */
  cols: 22,
  rows: 24,
};

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

/** Ingestion feeds shown in the data-source health strip. */
export const DATA_SOURCES = [
  { id: 'radar', label: 'IMD Doppler Radar', cadence: '10 min' },
  { id: 'satellite', label: 'INSAT-3DR / GPM', cadence: '30 min' },
  { id: 'aws', label: 'AWS/ARG Network', cadence: '15 min' },
  { id: 'nwp', label: 'WRF / GFS', cadence: '6 hr' },
  { id: 'cwc', label: 'CWC River Gauges', cadence: '1 hr' },
];

export const SCENARIOS: Scenario[] = [
  {
    id: 'live',
    name: 'Live feed',
    description: 'Current radar + satellite nowcast for the demo region.',
    intensity: 1,
    centre: [0.45, 0.55],
    isHistorical: false,
  },
  {
    id: 'monsoon-surge',
    name: 'Monsoon surge',
    description: 'Active offshore trough pushing a sustained heavy band inland.',
    intensity: 1.3,
    centre: [0.35, 0.6],
    isHistorical: false,
  },
  {
    id: 'jul-2005',
    name: '26 July 2005 replay',
    description: 'Historical extreme: 944 mm in 24 hr over the central suburbs.',
    intensity: 2.0,
    centre: [0.5, 0.45],
    isHistorical: true,
  },
  {
    id: 'aug-2020',
    name: 'Aug 2020 replay',
    description: 'Cyclonic circulation with high tide coinciding with peak rainfall.',
    intensity: 1.6,
    centre: [0.6, 0.35],
    isHistorical: true,
  },
];

export const DEFAULT_WHAT_IF = {
  extraRainfall: 0,
  soilSaturation: 1,
  drainageCapacity: 1,
};
