import { useDashboard } from '@/hooks/useDashboard';

/** Context card telling the operator which scenario the map is showing. */
export function ScenarioNote() {
  const { scenario, isSimulating } = useDashboard();

  return (
    <div className="pointer-events-auto max-w-xs rounded-lg border border-surface-border
      bg-surface/90 px-3 py-2 backdrop-blur">
      <p className="flex items-center gap-2 text-xs font-semibold text-slate-200">
        {scenario.isHistorical && (
          <span className="rounded bg-violet-500/15 px-1.5 py-0.5 text-[10px] uppercase
            tracking-wide text-violet-300">
            Replay
          </span>
        )}
        {isSimulating && (
          <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] uppercase
            tracking-wide text-sky-300">
            Simulated
          </span>
        )}
        {scenario.name}
      </p>
      <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">{scenario.description}</p>
    </div>
  );
}
