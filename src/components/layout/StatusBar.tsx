import { DATA_SOURCES, REGION } from '@/lib/config';
import { useDashboard } from '@/hooks/useDashboard';

/** Feed health and grid telemetry along the bottom of the board. */
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
    <footer className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-1 border-t
      border-surface-border bg-surface-deep px-5 py-2">
      {DATA_SOURCES.map((source) => (
        <span
          key={source.id}
          className="flex items-center gap-1.5 text-[11px] text-slate-500"
          title={`Refresh cadence: ${source.cadence}`}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-tier-normal" />
          {source.label}
        </span>
      ))}

      <span className="hidden h-3 w-px bg-white/10 lg:block" />

      {telemetry.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5 text-[11px]">
          <span className="text-slate-600">{item.label}</span>
          <span className="text-slate-300">{item.value}</span>
        </span>
      ))}

      <span className="ml-auto hidden text-[11px] font-medium text-slate-600 xl:block">
        RainShield · Prototype
      </span>
    </footer>
  );
}
