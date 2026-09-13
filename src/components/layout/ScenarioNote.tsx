import { useDashboard } from '@/hooks/useDashboard';

/** Context card telling the operator which scenario the map is showing. */
export function ScenarioNote() {
  const { scenario, isSimulating } = useDashboard();

  return (
    <div className="pointer-events-auto max-w-xs border border-surface-border bg-surface-deep/85
      px-3 py-2 backdrop-blur-md clip-notch shadow-[0_0_24px_-10px_rgba(34,211,238,0.8)]">
      <p className="flex flex-wrap items-center gap-2 font-display text-[13px] font-semibold
        uppercase tracking-[0.12em] text-cyan-100">
        {scenario.isHistorical && (
          <span className="border border-violet-400/40 bg-violet-500/15 px-1.5 py-px font-mono
            text-[9px] uppercase tracking-[0.18em] text-violet-300">
            Replay
          </span>
        )}
        {isSimulating && (
          <span className="border border-hud/40 bg-hud/15 px-1.5 py-px font-mono text-[9px]
            uppercase tracking-[0.18em] text-cyan-300">
            Simulated
          </span>
        )}
        {scenario.name}
      </p>
      <p className="mt-1 text-[11px] leading-relaxed text-slate-400">{scenario.description}</p>
    </div>
  );
}
