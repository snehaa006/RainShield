import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { DEFAULT_WHAT_IF, REFRESH_INTERVAL_MS } from '@/lib/config';
import {
  ApiError,
  EMPTY_SUMMARY,
  fetchForecast,
  fetchRegion,
  fetchRegions,
  fetchSeries,
  refreshFeed,
  type ForecastPayload,
  type RegionPayload,
  type RegionSummary,
  type SeriesPayload,
  type SeriesPoint,
} from '@/lib/api';
import { buildGrid, buildWards } from '@/lib/grid';
import { tierFor } from '@/lib/riskEngine';
import type {
  FeedStatus,
  GridCellStatic,
  LayerId,
  LeadTime,
  ModelStatus,
  PumpStationInfo,
  RegionDescriptor,
  ScoredCell,
  StormPhase,
  Ward,
  WardSummary,
  WhatIfSettings,
} from '@/types';

interface DashboardState {
  /** Region being scored. Every API call is scoped to it. */
  regionId: string;
  lead: LeadTime;
  whatIf: WhatIfSettings;
  activeLayer: LayerId;
  showInfrastructure: boolean;
  selectedWardId: string | null;
  selectedCellId: string | null;
}

interface DashboardValue extends DashboardState {
  /** Every region the backend can score, live and simulated. */
  regions: RegionDescriptor[];
  /** The active region's descriptor, null until /api/regions resolves. */
  region: RegionDescriptor | null;
  /** Where the scripted storm is, for a simulated region; null for a live one. */
  storm: StormPhase | null;
  /** Static grid, empty until /api/region resolves. */
  grid: GridCellStatic[];
  /** Pumping stations in the active region. Empty until /api/region resolves. */
  stations: PumpStationInfo[];
  wards: Ward[];
  cells: ScoredCell[];
  wardSummaries: WardSummary[];
  /** Zeroed until the first forecast lands, so panels never guard on null. */
  regionSummary: RegionSummary;
  regionSeries: SeriesPoint[];
  /** The same horizon with the sliders at their defaults, for what-if deltas. */
  baselineSummary: RegionSummary;
  selectedWard: WardSummary | null;
  selectedCell: ScoredCell | null;
  confidence: 'LOW' | 'MEDIUM' | 'HIGH';
  feed: FeedStatus | null;
  model: ModelStatus | null;
  generatedAt: string | null;
  /** True before the first successful load. */
  isLoading: boolean;
  /** True while a refresh is in flight over data that is already on screen. */
  isUpdating: boolean;
  error: string | null;
  isSimulating: boolean;
  refresh: () => void;
  setLead: (lead: LeadTime) => void;
  setWhatIf: (settings: Partial<WhatIfSettings>) => void;
  resetWhatIf: () => void;
  setActiveLayer: (layer: LayerId) => void;
  toggleInfrastructure: () => void;
  selectWard: (id: string | null) => void;
  selectCell: (id: string | null) => void;
  setRegionId: (id: string) => void;
}

const DashboardContext = createContext<DashboardValue | null>(null);

/** Stable identity, so memoising on `stations` does not rerun every render. */
const EMPTY_STATIONS: PumpStationInfo[] = [];

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DashboardState>({
    regionId: 'mumbai',
    lead: 120,
    whatIf: DEFAULT_WHAT_IF,
    activeLayer: 'risk',
    showInfrastructure: true,
    selectedWardId: null,
    selectedCellId: null,
  });

  const [regions, setRegions] = useState<RegionDescriptor[]>([]);
  const [region, setRegion] = useState<RegionPayload | null>(null);
  const [forecast, setForecast] = useState<ForecastPayload | null>(null);
  const [series, setSeries] = useState<SeriesPayload | null>(null);
  const [baseline, setBaseline] = useState<RegionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  const patch = (next: Partial<DashboardState>) => setState((prev) => ({ ...prev, ...next }));

  // The region list is fetched once; it never changes while the app is open.
  useEffect(() => {
    const controller = new AbortController();
    fetchRegions(controller.signal)
      .then((payload) => setRegions(payload.regions))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  // The static grid is fetched per region — terrain and exposure do not change
  // within one, but they are completely different between them.
  const { regionId, lead, whatIf } = state;
  useEffect(() => {
    const controller = new AbortController();
    setRegion(null);
    fetchRegion(regionId, controller.signal)
      .then(setRegion)
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof ApiError ? cause.message : String(cause));
      });
    return () => controller.abort();
  }, [regionId]);

  // Forecast and trend follow the region, lead time, sliders and refreshes.
  useEffect(() => {
    const controller = new AbortController();
    setIsUpdating(true);

    Promise.all([
      fetchForecast(lead, whatIf, regionId, controller.signal),
      fetchSeries(whatIf, regionId, controller.signal),
    ])
      .then(([nextForecast, nextSeries]) => {
        if (controller.signal.aborted) return;
        setForecast(nextForecast);
        setSeries(nextSeries);
        setError(null);
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof ApiError ? cause.message : String(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsUpdating(false);
      });

    return () => controller.abort();
  }, [regionId, lead, whatIf, reloadToken]);

  // The unmodified forecast for the same horizon, so the what-if panel can show
  // a delta. Only fetched while the sliders are off their defaults.
  const simulating =
    whatIf.extraRainfall !== DEFAULT_WHAT_IF.extraRainfall ||
    whatIf.soilSaturation !== DEFAULT_WHAT_IF.soilSaturation ||
    whatIf.drainageCapacity !== DEFAULT_WHAT_IF.drainageCapacity;

  useEffect(() => {
    if (!simulating) {
      setBaseline(null);
      return undefined;
    }
    const controller = new AbortController();
    fetchForecast(lead, DEFAULT_WHAT_IF, regionId, controller.signal)
      .then((payload) => {
        if (!controller.signal.aborted) setBaseline(payload.summary);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [regionId, lead, simulating, reloadToken]);

  // Poll so the board keeps pace with the feed without a manual reload.
  useEffect(() => {
    const timer = window.setInterval(() => setReloadToken((n) => n + 1), REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, []);

  const refresh = useCallback(() => {
    // Ask the backend to drop its cached observation, then reload either way:
    // a failed refresh should still re-render whatever the API can serve.
    refreshFeed(regionId)
      .catch(() => undefined)
      .finally(() => setReloadToken((n) => n + 1));
  }, [regionId]);

  const grid = useMemo(() => (region ? buildGrid(region) : []), [region]);
  const stations = region?.stations ?? EMPTY_STATIONS;
  const wards = useMemo(() => (region ? buildWards(region) : []), [region]);

  // Join the static grid with the current forecast into the scored cells the
  // panels and map consume.
  const cells = useMemo<ScoredCell[]>(() => {
    if (!forecast || grid.length === 0) return [];
    // Both regions are 1755 cells, so a length check alone would happily paint
    // one region's forecast onto the other's grid during a switch.
    if (forecast.region.id !== regionId || region?.region.id !== regionId) return [];
    const { cells: c, riskComponents: rc } = forecast;
    if (c.risk.length !== grid.length) return [];

    return grid.map((cell, i) => ({
      ...cell,
      susceptibility: c.susceptibility[i],
      rainfallIntensity: c.rainfallIntensity[i],
      rainfall3h: c.rainfall3h[i],
      floodProbability: c.floodProbability[i],
      waterDepth: c.waterDepth[i],
      timeToInundation: c.timeToInundation[i],
      confidence: forecast.confidence,
      risk: {
        total: c.risk[i],
        components: {
          rainfallSeverity: rc.rainfall_severity?.[i] ?? 0,
          floodProbability: rc.flood_probability?.[i] ?? 0,
          waterDepth: rc.water_depth?.[i] ?? 0,
          populationExposure: rc.population_exposure?.[i] ?? 0,
          criticalInfra: rc.critical_infra?.[i] ?? 0,
        },
      },
      tier: tierFor(c.risk[i]),
    }));
  }, [forecast, grid, region, regionId]);

  const wardById = useMemo(() => new Map(wards.map((ward) => [ward.id, ward])), [wards]);

  const wardSummaries = useMemo<WardSummary[]>(() => {
    if (!forecast) return [];
    return forecast.wards.flatMap((summary) => {
      const ward = wardById.get(summary.id);
      if (!ward) return [];
      return [
        {
          ward,
          tier: summary.tier as WardSummary['tier'],
          risk: summary.risk,
          peakFloodProbability: summary.peakFloodProbability,
          peakWaterDepth: summary.peakWaterDepth,
          timeToInundation: summary.timeToInundation,
          confidence: summary.confidence,
          populationAtRisk: summary.populationAtRisk,
          cellCount: summary.cellCount,
          floodedCellCount: summary.floodedCellCount,
        },
      ];
    });
  }, [forecast, wardById]);

  const selectedWard = useMemo(
    () => wardSummaries.find((w) => w.ward.id === state.selectedWardId) ?? null,
    [wardSummaries, state.selectedWardId],
  );

  const selectedCell = useMemo(
    () => cells.find((c) => c.id === state.selectedCellId) ?? null,
    [cells, state.selectedCellId],
  );

  const activeRegion = useMemo(
    () => regions.find((r) => r.id === regionId) ?? region?.region ?? null,
    [regions, region, regionId],
  );

  const value: DashboardValue = {
    ...state,
    regions,
    region: activeRegion,
    storm: forecast?.region.id === regionId ? forecast?.storm ?? null : null,
    grid,
    stations,
    wards,
    cells,
    wardSummaries,
    regionSummary: forecast?.summary ?? EMPTY_SUMMARY,
    regionSeries: series?.series ?? [],
    baselineSummary: baseline ?? forecast?.summary ?? EMPTY_SUMMARY,
    selectedWard,
    selectedCell,
    confidence: forecast?.confidence ?? 'MEDIUM',
    feed: forecast?.observation ?? null,
    model: forecast
      ? {
          loaded: forecast.model.loaded,
          backend: forecast.model.backend,
          runtime: forecast.model.runtime,
          weightsPresent: forecast.model.weights_present,
          error: forecast.model.error,
        }
      : null,
    generatedAt: forecast?.generatedAt ?? null,
    isLoading: cells.length === 0 && !error,
    isUpdating,
    error,
    isSimulating: simulating,
    refresh,
    setLead: (nextLead) => patch({ lead: nextLead }),
    setWhatIf: (settings) =>
      setState((prev) => ({ ...prev, whatIf: { ...prev.whatIf, ...settings } })),
    resetWhatIf: () => patch({ whatIf: DEFAULT_WHAT_IF }),
    setActiveLayer: (activeLayer) => patch({ activeLayer }),
    toggleInfrastructure: () =>
      setState((prev) => ({ ...prev, showInfrastructure: !prev.showInfrastructure })),
    selectWard: (selectedWardId) => patch({ selectedWardId }),
    selectCell: (selectedCellId) => patch({ selectedCellId }),
    // Switching region invalidates every selection — ward and cell ids belong
    // to the region they came from — and drops back to the present. Carrying a
    // +2 hr horizon across the switch showed the new region's forecast while
    // the banner described its current conditions, which read as a contradiction.
    setRegionId: (nextRegionId) =>
      patch({
        regionId: nextRegionId,
        lead: 0,
        selectedWardId: null,
        selectedCellId: null,
      }),
  };

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboard(): DashboardValue {
  const value = useContext(DashboardContext);
  if (!value) throw new Error('useDashboard must be used inside <DashboardProvider>');
  return value;
}
