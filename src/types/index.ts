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
  /** Kilometres to the nearest drainage line or river. */
  distanceToDrainage: number;
  landUse: LandUse;
  /** People per square kilometre. */
  population: number;
  /** 0-1 proximity weighting for hospitals, schools, bridges and arterial roads. */
  criticalInfraProximity: number;
}

/** Model output for one cell at one lead time. */
export interface CellForecast {
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
  /** Polygon ring, [lon, lat] pairs. */
  boundary: [number, number][];
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

/** A named historical or live event the dashboard can replay. */
export interface Scenario {
  id: string;
  name: string;
  description: string;
  /** Basin-wide rainfall multiplier applied to the synthetic nowcast. */
  intensity: number;
  /** Storm centre as a fraction of the grid, 0-1 in each axis. */
  centre: [number, number];
  isHistorical: boolean;
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
