/** Domain model for the RainShield AI dashboard. */

/** Forecast lead times produced by the nowcasting model (minutes from now). */
export type LeadTime = 0 | 30 | 60 | 120 | 180 | 360;

/** Four-tier warning level driven by the composite risk score. */
export type AlertTier = 'NORMAL' | 'WATCH' | 'WARNING' | 'CRITICAL';

/** Confidence tag emitted by the ensemble fusion model. */
export type Confidence = 'LOW' | 'MEDIUM' | 'HIGH';

export type LandUse = 'urban-dense' | 'urban' | 'periurban' | 'vegetation' | 'water';

/** Static attributes of a 1 km grid cell, from DEM / LULC / census layers. */
export interface GridCellStatic {
  id: string;
  /** Cell centre, WGS84. */
  lon: number;
  lat: number;
  /** Column/row inside the demo grid, used for deterministic generation. */
  col: number;
  row: number;
  wardId: string;
  elevation: number;
  slope: number;
  landUse: LandUse;
  /** People per square kilometre. */
  population: number;
  /** 0-1 proximity weighting for hospitals, schools, bridges and arterial roads. */
  criticalInfraProximity: number;
}

/** Model output for one cell at one lead time. */
export interface CellForecast {
  /**
   * Terrain flood susceptibility straight from the network, 0-1. The live
   * rainfall drives `floodProbability` on top of this.
   */
  susceptibility: number;
  /** Nowcast rainfall intensity, mm/hr. */
  rainfallIntensity: number;
  /** Accumulated rainfall over the preceding 3 hours, mm. */
  rainfall3h: number;
  /** P(flooding) from the runoff/inundation model, 0-1. */
  floodProbability: number;
  /** Expected standing water depth, metres. */
  waterDepth: number;
  /** Minutes until inundation begins, or null when no inundation is expected. */
  timeToInundation: number | null;
  confidence: Confidence;
}

/** A cell with its forecast and scored risk at the active lead time. */
export interface ScoredCell extends GridCellStatic, CellForecast {
  risk: RiskScore;
  tier: AlertTier;
}

/** Weighted breakdown of the composite risk score. */
export interface RiskScore {
  total: number;
  components: {
    rainfallSeverity: number;
    floodProbability: number;
    waterDepth: number;
    populationExposure: number;
    criticalInfra: number;
  };
}

export interface Ward {
  id: string;
  name: string;
  /** Administrative centre, [lon, lat]. */
  centre: [number, number];
  /**
   * Outline rings, [lon, lat] pairs. Built by dissolving the ward's member
   * cells, so it follows the 1 km grid rather than a smooth admin boundary.
   */
  boundary: [number, number][][];
}

/** Aggregated ward-level view used by the alert list and drill-down. */
export interface WardSummary {
  ward: Ward;
  tier: AlertTier;
  risk: number;
  peakFloodProbability: number;
  peakWaterDepth: number;
  /** Earliest time-to-inundation across the ward's cells, minutes. */
  timeToInundation: number | null;
  confidence: Confidence;
  populationAtRisk: number;
  cellCount: number;
  floodedCellCount: number;
}

/**
 * One instant, rendered by the backend in both UTC and the region's own zone.
 *
 * The board used to format timestamps with the *browser's* locale and then
 * label them IST, which is wrong for anyone outside India. The backend knows
 * which zone a region is in, so it says so rather than leaving the client to
 * assume.
 */
export interface Stamp {
  utc: string;
  local: string;
  localTime: string;
  localDate: string;
  /** IANA zone, e.g. "Asia/Kolkata". */
  timezone: string;
  /** Short zone name, e.g. "IST". */
  abbreviation: string;
  /** e.g. "+05:30". */
  utcOffset: string;
  epoch: number;
}

/** State of the live ingestion feed, reported alongside every forecast. */
export interface FeedStatus {
  /** Provider that produced the observation, e.g. "openmeteo". */
  source: string;
  regionId: string;
  fetchedAt: string;
  ageSeconds: number;
  /** True when upstream failed and cached or synthetic data is standing in. */
  degraded: boolean;
  /**
   * True when the whole field is generated rather than observed. Distinct from
   * `degraded`: a simulated region has no real feed to lose.
   */
  simulated: boolean;
  notes: string[];
  cacheTtl: number;
  cadenceSeconds: number;
  timestamp: Stamp;
  nextUpdate: Stamp;
}

/** A region the service can score. */
export interface RegionDescriptor {
  id: string;
  name: string;
  state: string;
  bounds: [number, number, number, number];
  centre: [number, number];
  rows: number;
  cols: number;
  cellCount: number;
  cellWidth: number;
  cellHeight: number;
  timezone: string;
  /** "live" — real terrain and real weather. "simulated" — neither. */
  kind: 'live' | 'simulated';
  simulated: boolean;
  blurb: string;
  cadenceSeconds: number;
}

/** Where the scripted storm is, for a simulated region. */
export interface StormPhase {
  phase: number;
  label: string;
}

/** One field of the current observation, as the live-feed view lists it. */
export interface FeedField {
  key: string;
  unit: string;
  description: string;
  min: number;
  mean: number;
  max: number;
  /** Model channel this field feeds, when it feeds one directly. */
  modelChannel?: string | null;
  /** Per-lead-time spread, for the fields that vary with the horizon. */
  perLead?: Record<string, { min: number; mean: number; max: number }> | null;
}

/** One observation landing on the feed. */
export interface FeedArrival {
  source: string;
  degraded: boolean;
  simulated: boolean;
  peakRainRate: number;
  meanRainRate: number;
  peakRain3h: number;
  peakSoilMoisture: number;
  meanCloudCover: number;
  peakAntecedent24h: number;
  notes: string[];
  timestamp: Stamp;
}

/** State of the inference backend. */
export interface ModelStatus {
  loaded: boolean;
  /** "cnn-transformer" when the trained weights are serving. */
  backend: string;
  runtime: string;
  weightsPresent: boolean;
  error: string | null;
}

/** User-tunable inputs of the what-if simulator. */
export interface WhatIfSettings {
  /** Additional rainfall injected across the grid, mm. */
  extraRainfall: number;
  /** Multiplier on antecedent soil saturation, 0.5-1.5. */
  soilSaturation: number;
  /** Drainage capacity as a fraction of design capacity, 0.3-1.2. */
  drainageCapacity: number;
}

/** Common Alerting Protocol payload emitted by the warning engine. */
export interface CapAlert {
  identifier: string;
  sent: string;
  status: 'Actual' | 'Exercise';
  msgType: 'Alert' | 'Update';
  scope: 'Public';
  severity: 'Minor' | 'Moderate' | 'Severe' | 'Extreme';
  urgency: 'Future' | 'Expected' | 'Immediate';
  certainty: 'Possible' | 'Likely' | 'Observed';
  event: string;
  headline: string;
  description: string;
  instruction: string;
  areaDesc: string;
  expires: string;
}

/** The metric the map's grid layer is coloured by. */
export type LayerId = 'rainfall' | 'flood' | 'risk';

/** A pumping station, with the provenance of its capacity figure attached. */
export interface PumpStationInfo {
  id: string;
  name: string;
  lon: number;
  lat: number;
  pumps: number;
  capacityCumecs: number;
  unitCumecs: number;
  gravityCumecs: number;
  /** Outfall invert level, m above chart datum. The gate shuts above this. */
  outfallInvertMCd: number;
  commissioned: number | null;
  /**
   * Where the capacity figure comes from. Travels with every capacity the API
   * serves, because a number that arrives without its caveat is a number that
   * will eventually be quoted as fact.
   */
  capacityBasis: string;
  generated: boolean;
}

/** One catchment's mass balance at one lead time. */
export interface CatchmentBalance {
  id: string;
  name: string;
  stationId: string | null;
  areaKm2: number;
  cellCount: number;
  rainfallMmHr: number;
  infiltrationMmHr: number;
  netRunoffMmHr: number;
  /** Rainfall intensity the current supply can clear, mm/hr. */
  capacityMmHr: number;
  /** The same with the tide gate open. */
  openGateCapacityMmHr: number;
  inflowCumecs: number;
  gravityCumecs: number;
  pumpCumecs: number;
  supplyCumecs: number;
  deficitCumecs: number;
  extraPumpsRequired: number;
  sufficient: boolean;
  gateClosed: boolean;
  /** False for the unpumped remainder, which claims no capacity at all. */
  supplyModelled: boolean;
}

/** Sea level and how it is moving, m above chart datum. */
export interface TideState {
  levelMCd: number;
  rateMPerHr: number;
  /** Where this sits between LAT (0) and HAT (1). */
  normalised: number;
  phase: 'high' | 'low' | 'flooding' | 'ebbing';
  rising: boolean;
  validAt: string;
  meanSeaLevelMCd: number;
  highestAstronomicalMCd: number;
  lowestAstronomicalMCd: number;
  springRangeM: number;
  basis: string;
}
