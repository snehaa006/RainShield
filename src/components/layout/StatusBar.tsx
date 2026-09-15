import { FEED_LABELS } from '@/lib/config';
import { useDashboard } from '@/hooks/useDashboard';

/** Feed health and grid telemetry along the bottom of the board. */
export function StatusBar() {
  const { regionSummary, wardSummaries, lead, region, feed } = useDashboard();
  const actionable = wardSummaries.filter((w) => w.tier !== 'NORMAL').length;

  // The strip used to list five fixed upstream feeds with a green dot each,
  // regardless of what the backend was actually serving. It now reports the
  // provider the current observation really came from, and its real state.
  const source = feed ? (FEED_LABELS[feed.source] ?? feed.source) : 'connecting…';
  const dot = !feed
    ? 'bg-slate-600'
    : feed.simulated
      ? 'bg-tier-warning'
      : feed.degraded
        ? 'bg-tier-warning'
        : 'bg-tier-normal';

  const telemetry = [
    {
      label: 'Grid',
      value: region ? `${region.cellCount} cells · 1 km` : '—',
    },
    { label: 'Wards actionable', value: `${actionable} / ${wardSummaries.length}` },
    { label: 'Cells flooding', value: `${regionSummary.floodedArea}` },
    { label: 'Horizon', value: lead === 0 ? 'Now' : `+${lead} min` },
    {
      label: 'Feed age',
      value: feed ? `${Math.round(feed.ageSeconds)}s` : '—',
    },
  ];

  return (
    <footer className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-1 border-t
      border-surface-border bg-surface-deep px-5 py-2">
      <span
        className="flex items-center gap-1.5 text-[11px] text-slate-500"
        title={feed ? feed.notes.join(' · ') || 'Feed healthy' : undefined}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
        {source}
        {feed?.simulated && (
          <span className="rounded-full bg-amber-500/20 px-1.5 py-0.5 text-[9px]
            font-medium text-amber-300">
            simulated
          </span>
        )}
        {feed?.degraded && !feed.simulated && (
          <span className="rounded-full bg-tier-warning/20 px-1.5 py-0.5 text-[9px]
            font-medium text-tier-warning">
            degraded
          </span>
        )}
      </span>

      <span className="hidden h-3 w-px bg-white/10 lg:block" />

      {telemetry.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5 text-[11px]">
          <span className="text-slate-600">{item.label}</span>
          <span className="tabular-nums text-slate-300">{item.value}</span>
        </span>
      ))}

      <span className="ml-auto hidden text-[11px] font-medium text-slate-600 xl:block">
        RainShield · Prototype
      </span>
    </footer>
  );
}
