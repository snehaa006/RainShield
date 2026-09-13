import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { DEFAULT_WHAT_IF, LEAD_TIMES, SCENARIOS } from '@/lib/config';
import { getForecast, getRegionSeries } from '@/lib/forecast';
import { WARDS } from '@/lib/grid';
import { summariseRegion, summariseWard } from '@/lib/riskEngine';
import type { LayerId, LeadTime, ScoredCell, WhatIfSettings } from '@/types';

interface DashboardState {
  scenarioId: string;
  lead: LeadTime;
  whatIf: WhatIfSettings;
  activeLayer: LayerId;
  showInfrastructure: boolean;
  selectedWardId: string | null;
  selectedCellId: string | null;
}

interface DashboardValue extends DashboardState {
  scenario: (typeof SCENARIOS)[number];
  cells: ScoredCell[];
  wardSummaries: ReturnType<typeof summariseWard>[];
  regionSummary: ReturnType<typeof summariseRegion>;
  regionSeries: ReturnType<typeof getRegionSeries>;
  selectedWard: ReturnType<typeof summariseWard> | null;
  selectedCell: ScoredCell | null;
  /** True when the what-if simulator is changing the baseline forecast. */
  isSimulating: boolean;
  setScenarioId: (id: string) => void;
  setLead: (lead: LeadTime) => void;
  setWhatIf: (settings: Partial<WhatIfSettings>) => void;
  resetWhatIf: () => void;
  setActiveLayer: (layer: LayerId) => void;
  toggleInfrastructure: () => void;
  selectWard: (id: string | null) => void;
  selectCell: (id: string | null) => void;
}

const DashboardContext = createContext<DashboardValue | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DashboardState>({
    scenarioId: SCENARIOS[1].id,
    lead: 120,
    whatIf: DEFAULT_WHAT_IF,
    activeLayer: 'risk',
    showInfrastructure: true,
    selectedWardId: null,
    selectedCellId: null,
  });

  const patch = (next: Partial<DashboardState>) => setState((prev) => ({ ...prev, ...next }));

  const scenario = useMemo(
    () => SCENARIOS.find((s) => s.id === state.scenarioId) ?? SCENARIOS[0],
    [state.scenarioId],
  );

  const cells = useMemo(
    () => getForecast(scenario, state.lead, state.whatIf),
    [scenario, state.lead, state.whatIf],
  );

  const wardSummaries = useMemo(() => {
    const byWard = new Map<string, ScoredCell[]>();
    cells.forEach((cell) => {
      const list = byWard.get(cell.wardId);
      if (list) list.push(cell);
      else byWard.set(cell.wardId, [cell]);
    });
    return WARDS.map((ward) => summariseWard(ward, byWard.get(ward.id) ?? [])).sort(
      (a, b) => b.risk - a.risk,
    );
  }, [cells]);

  const regionSummary = useMemo(() => summariseRegion(cells), [cells]);

  const regionSeries = useMemo(
    () => getRegionSeries(scenario, LEAD_TIMES, state.whatIf),
    [scenario, state.whatIf],
  );

  const selectedWard = useMemo(
    () => wardSummaries.find((w) => w.ward.id === state.selectedWardId) ?? null,
    [wardSummaries, state.selectedWardId],
  );

  const selectedCell = useMemo(
    () => cells.find((c) => c.id === state.selectedCellId) ?? null,
    [cells, state.selectedCellId],
  );

  const value: DashboardValue = {
    ...state,
    scenario,
    cells,
    wardSummaries,
    regionSummary,
    regionSeries,
    selectedWard,
    selectedCell,
    isSimulating:
      state.whatIf.extraRainfall !== DEFAULT_WHAT_IF.extraRainfall ||
      state.whatIf.soilSaturation !== DEFAULT_WHAT_IF.soilSaturation ||
      state.whatIf.drainageCapacity !== DEFAULT_WHAT_IF.drainageCapacity,
    setScenarioId: (scenarioId) => patch({ scenarioId }),
    setLead: (lead) => patch({ lead }),
    setWhatIf: (settings) =>
      setState((prev) => ({ ...prev, whatIf: { ...prev.whatIf, ...settings } })),
    resetWhatIf: () => patch({ whatIf: DEFAULT_WHAT_IF }),
    setActiveLayer: (activeLayer) => patch({ activeLayer }),
    toggleInfrastructure: () =>
      setState((prev) => ({ ...prev, showInfrastructure: !prev.showInfrastructure })),
    selectWard: (selectedWardId) => patch({ selectedWardId }),
    selectCell: (selectedCellId) => patch({ selectedCellId }),
  };

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboard(): DashboardValue {
  const value = useContext(DashboardContext);
  if (!value) throw new Error('useDashboard must be used inside <DashboardProvider>');
  return value;
}
