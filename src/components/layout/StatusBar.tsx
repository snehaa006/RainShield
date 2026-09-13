import { DATA_SOURCES, REGION } from '@/lib/config';
import { useDashboard } from '@/hooks/useDashboard';

/**
 * Operations footer: live feed health on the left, grid telemetry on the right,
 * mirroring the status strip along the bottom of a control-room board.
 */
export function StatusBar() {
  const { regionSummary, wardSummaries, lead } = useDashboard();
  const actionable = wardSummaries.filter((w) => w.tier !== 'NORMAL').length;

  const telemetry = [
    { label: 'Grid', value: `${REGION.cols * REGION.rows} cells · 1 km` },
    { label: 'Wards actionable', value: `${actionable} / ${wardSummaries.length}` },
    { label: 'Cells flooding', value: `${regionSummary.floodedArea}` },
    { label: 'Horizon', value: lead === 0 ? 'Now' : `+${lead} min` },
  ];

  return (
    <footer className="relative z-10 flex shrink-0 flex-wrap items-center gap-x-5 gap-y-1
      border-t border-surface-border bg-surface-deep/80 px-5 py-1.5 backdrop-blur-md">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r
        from-transparent via-hud/50 to-transparent" />

      {/* Feed health LEDs. */}
      {DATA_SOURCES.map((source) => (
        <span
          key={source.id}
          className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em]
            text-slate-500"
          title={`Refresh cadence: ${source.cadence}`}
        >
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-hud-pulse rounded-full
              bg-emerald-400/70" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400
              shadow-[0_0_8px_1px_rgba(52,211,153,0.8)]" />
          </span>
          {source.label}
        </span>
      ))}

      <span className="hidden h-3.5 w-px bg-hud/25 lg:block" />

      {telemetry.map((item) => (
        <span
          key={item.label}
          className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em]"
        >
          <span className="text-slate-600">{item.label}</span>
          <span className="text-cyan-200">{item.value}</span>
        </span>
      ))}

      <span className="ml-auto hidden font-display text-[11px] font-semibold uppercase
        tracking-[0.3em] text-hud/50 2xl:block">
        RainShield · Flood Intelligence
      </span>
    </footer>
  );
}
