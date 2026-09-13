import { useDashboard } from '@/hooks/useDashboard';

/** Context card telling the operator which scenario the map is showing. */
export function ScenarioNote() {
  const { scenario, isSimulating } = useDashboard();

  return (
    <div className="pointer-events-auto max-w-xs rounded-[12px] border border-surface-border
      bg-black/70 px-3 py-2 backdrop-blur-xl">
      <p className="flex flex-wrap items-center gap-2 text-[12px] font-semibold text-white">
        {scenario.isHistorical && (
          <span className="rounded-full bg-violet-500/20 px-2 py-0.5 text-[10px] font-medium
            text-violet-300">
            Replay
          </span>
        )}
        {isSimulating && (
          <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium
            text-accent">
            Simulated
          </span>
        )}
        {scenario.name}
      </p>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-400">{scenario.description}</p>
    </div>
  );
}
