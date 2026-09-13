import { TIER_COLORS } from '@/lib/config';
import { compactNumber, duration, metres, percent } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';
import { TierBadge } from '@/components/ui/TierBadge';

interface WardListProps {
  className?: string;
  /** 'list' for the narrow rail, 'grid' for the full-width wards view. */
  variant?: 'list' | 'grid';
}

/** Ward drill-down, ordered by composite risk. */
export function WardList({ className = '', variant = 'list' }: WardListProps) {
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
      bodyClassName="min-h-0 flex-1 overflow-y-auto scroll-thin px-2 pb-2"
      className={className}
    >
      <ul
        className={
          variant === 'grid'
            ? 'grid gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4'
            : 'space-y-1'
        }
      >
        {wardSummaries.map((summary, index) => {
          const isSelected = summary.ward.id === selectedWardId;
          const color = TIER_COLORS[summary.tier];
          return (
            <li key={summary.ward.id}>
              <button
                type="button"
                onClick={() => selectWard(isSelected ? null : summary.ward.id)}
                className={`w-full rounded-[12px] border px-3 py-2.5 text-left transition-colors ${
                  isSelected
                    ? 'border-accent/60 bg-accent-soft'
                    : 'border-transparent hover:border-surface-border hover:bg-white/[0.04]'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-baseline gap-2">
                    <span className="text-[11px] tabular-nums text-slate-600">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <span className="truncate text-[14px] font-semibold text-white">
                      {summary.ward.name}
                    </span>
                  </span>
                  <TierBadge tier={summary.tier} />
                </div>

                <div className="mt-2 flex items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.08]">
                    <div
                      className="h-full rounded-full transition-[width] duration-500"
                      style={{ width: `${summary.risk * 100}%`, backgroundColor: color }}
                    />
                  </div>
                  <span
                    className="w-8 text-right text-[12px] font-semibold tabular-nums"
                    style={{ color }}
                  >
                    {summary.risk.toFixed(2)}
                  </span>
                </div>

                <dl className="mt-2 grid grid-cols-4 gap-2">
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
      <dt className="text-[10px] text-slate-600">{label}</dt>
      <dd className="text-[11px] tabular-nums text-slate-300">{value}</dd>
    </div>
  );
}
