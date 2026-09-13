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
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">
          <span className="text-cyan-300">{actionable}</span>/{wardSummaries.length} act.
        </span>
      }
      bodyClassName="min-h-0 flex-1 overflow-y-auto scroll-thin p-2"
      className={className}
    >
      <ul className="space-y-1">
        {wardSummaries.map((summary, index) => {
          const isSelected = summary.ward.id === selectedWardId;
          const color = TIER_COLORS[summary.tier];
          return (
            <li key={summary.ward.id}>
              <button
                type="button"
                onClick={() => selectWard(isSelected ? null : summary.ward.id)}
                className={`clip-bevel relative w-full border px-3 py-2.5 text-left
                  transition-all duration-200 ${
                    isSelected
                      ? 'border-hud/60 bg-hud/10 shadow-[inset_0_0_20px_-10px_rgba(34,211,238,0.9)]'
                      : 'border-transparent hover:border-hud/30 hover:bg-hud/5'
                  }`}
              >
                {/* Tier spine so the list scans by colour at a glance. */}
                <span
                  className="absolute inset-y-0 left-0 w-[3px]"
                  style={{ backgroundColor: color, boxShadow: `0 0 10px 0 ${color}` }}
                />

                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-baseline gap-2">
                    <span className="font-mono text-[10px] tabular-nums text-hud/50">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <span className="font-display text-[15px] font-semibold tracking-wide
                      text-slate-100">
                      {summary.ward.name}
                    </span>
                  </span>
                  <TierBadge tier={summary.tier} />
                </div>

                <div className="mt-2 flex items-center gap-2">
                  <div
                    className="h-1.5 flex-1 border border-surface-hairline bg-surface-deep/80"
                    style={{
                      backgroundImage:
                        'repeating-linear-gradient(90deg, rgba(56,189,248,0.10) 0 3px, transparent 3px 6px)',
                    }}
                  >
                    <div
                      className="h-full transition-[width] duration-500"
                      style={{
                        width: `${summary.risk * 100}%`,
                        background: `linear-gradient(90deg, ${color}66, ${color})`,
                        boxShadow: `0 0 10px 0 ${color}`,
                      }}
                    />
                  </div>
                  <span
                    className="w-9 text-right font-display text-[13px] font-bold tabular-nums"
                    style={{ color, textShadow: `0 0 10px ${color}80` }}
                  >
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
      <dt className="font-mono text-[9px] uppercase tracking-[0.12em] text-slate-600">{label}</dt>
      <dd className="font-mono tabular-nums text-slate-300">{value}</dd>
    </div>
  );
}
