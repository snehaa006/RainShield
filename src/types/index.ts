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

/** State of the live ingestion feed, reported alongside every forecast. */
export interface FeedStatus {
  /** Provider that produced the observation, e.g. "openmeteo". */
  source: string;
  fetchedAt: string;
  ageSeconds: number;
  /** True when upstream failed and cached or synthetic data is standing in. */
  degraded: boolean;
  notes: string[];
  cacheTtl: number;
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
