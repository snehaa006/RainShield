import { TIER_COLORS } from '@/lib/config';
import { compactNumber, duration, metres, percent } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';
import { TierBadge } from '@/components/ui/TierBadge';

/** Ward drill-down list, ordered by composite risk. */
export function WardList({ className = '' }: { className?: string }) {
  const { wardSummaries, selectedWardId, selectWard } = useDashboard();
  const actionable = wardSummaries.filter((w) => w.tier !== 'NORMAL').length;

  return (
    <Panel
      title="Ward risk ranking"
      actions={
        <span className="text-[11px] text-slate-500">
          {actionable} of {wardSummaries.length} actionable
        </span>
      }
      bodyClassName="min-h-0 flex-1 overflow-y-auto scroll-thin p-2"
      className={className}
    >
      <ul className="space-y-1">
        {wardSummaries.map((summary) => {
          const isSelected = summary.ward.id === selectedWardId;
          return (
            <li key={summary.ward.id}>
              <button
                type="button"
                onClick={() => selectWard(isSelected ? null : summary.ward.id)}
                className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors ${
                  isSelected
                    ? 'border-sky-500/60 bg-sky-500/10'
                    : 'border-transparent hover:border-surface-border hover:bg-surface'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-slate-100">{summary.ward.name}</span>
                  <TierBadge tier={summary.tier} />
                </div>

                <div className="mt-2 flex items-center gap-2">
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-slate-800">
                    <div
                      className="h-full rounded-full transition-[width] duration-500"
                      style={{
                        width: `${summary.risk * 100}%`,
                        backgroundColor: TIER_COLORS[summary.tier],
                      }}
                    />
                  </div>
                  <span className="w-8 text-right text-[11px] tabular-nums text-slate-400">
                    {summary.risk.toFixed(2)}
                  </span>
                </div>

                <dl className="mt-2 grid grid-cols-4 gap-2 text-[11px]">
                  <Stat label="P(flood)" value={percent(summary.peakFloodProbability)} />
                  <Stat label="Depth" value={metres(summary.peakWaterDepth)} />
                  <Stat label="Onset" value={duration(summary.timeToInundation)} />
                  <Stat label="At risk" value={compactNumber(summary.populationAtRisk)} />
                </dl>
              </button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className="tabular-nums text-slate-300">{value}</dd>
    </div>
  );
}
