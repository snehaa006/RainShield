import { compactNumber, duration } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';

/** Headline situation numbers — the first thing an operator reads. */
export function OverviewPanel() {
  const { regionSummary, wardSummaries } = useDashboard();
  const critical = wardSummaries.filter((w) => w.tier === 'CRITICAL').length;
  const warning = wardSummaries.filter((w) => w.tier === 'WARNING').length;

  const headline = [
    { label: 'Critical wards', value: String(critical), color: '#ff453a' },
    { label: 'Warning wards', value: String(warning), color: '#ff9f0a' },
    {
      label: 'People at risk',
      value: compactNumber(regionSummary.populationAtRisk),
      color: '#ffffff',
    },
  ];

  return (
    <Panel title="Flood overview">
      <div className="grid grid-cols-3 gap-2">
        {headline.map((item) => (
          <div key={item.label}>
            <p
              className="text-[26px] font-semibold leading-none tabular-nums tracking-tight"
              style={{ color: item.color }}
            >
              {item.value}
            </p>
            <p className="mt-1.5 text-[11px] leading-tight text-slate-500">{item.label}</p>
          </div>
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between rounded-[10px] bg-white/[0.04]
        px-3 py-2">
        <span className="text-[11px] text-slate-400">Lead time to first inundation</span>
        <span className="text-[13px] font-semibold tabular-nums text-white">
          {duration(regionSummary.leadTime)}
        </span>
      </div>
    </Panel>
  );
}
