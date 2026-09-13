import { DATA_SOURCES, REGION, SCENARIOS } from '@/lib/config';
import { useDashboard } from '@/hooks/useDashboard';
import { TierBadge } from '@/components/ui/TierBadge';

export function Header() {
  const { scenario, setScenarioId, regionSummary } = useDashboard();

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b
      border-surface-border bg-surface-raised px-5 py-3">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sky-500/15
          text-lg text-sky-300">
          ☂
        </div>
        <div>
          <h1 className="text-sm font-semibold tracking-tight text-slate-100">
            RainShield AI
            <span className="ml-2 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium
              uppercase tracking-wider text-slate-400">
              Prototype
            </span>
          </h1>
          <p className="text-xs text-slate-500">
            {REGION.name}, {REGION.state} — 1 km grid
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <DataSourceHealth />
        <label className="flex items-center gap-2 text-xs text-slate-400">
          Scenario
          <select
            value={scenario.id}
            onChange={(event) => setScenarioId(event.target.value)}
            className="rounded-md border border-surface-border bg-surface px-2 py-1.5 text-xs
              text-slate-200 outline-none focus:border-sky-500"
          >
            {SCENARIOS.map((option) => (
              <option key={option.id} value={option.id}>
                {option.isHistorical ? `↺ ${option.name}` : option.name}
              </option>
            ))}
          </select>
        </label>
        <TierBadge tier={regionSummary.tier} size="md" pulse={regionSummary.tier !== 'NORMAL'} />
      </div>
    </header>
  );
}

function DataSourceHealth() {
  return (
    <div className="hidden items-center gap-3 xl:flex">
      {DATA_SOURCES.map((source) => (
        <span
          key={source.id}
          className="flex items-center gap-1.5 text-[11px] text-slate-500"
          title={`Refresh cadence: ${source.cadence}`}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          {source.label}
        </span>
      ))}
    </div>
  );
}
