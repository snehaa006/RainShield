import { CONFIDENCE_COLORS, TIER_COLORS } from '@/lib/config';
import { clockAt, compactNumber, duration, fullNumber, metres, percent } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';
import { Meter } from '@/components/ui/Meter';
import { Panel } from '@/components/ui/Panel';
import { TierBadge } from '@/components/ui/TierBadge';

/** Alert intelligence: why this ward is alerting and how much time is left. */
export function AlertPanel() {
  const { selectedWard, wardSummaries, selectWard } = useDashboard();
  const ward = selectedWard ?? wardSummaries[0];

  if (!ward) return null;

  return (
    <Panel
      title="Alert intelligence"
      actions={
        selectedWard ? (
          <button type="button" className="chip" onClick={() => selectWard(null)}>
            Reset
          </button>
        ) : (
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">
            Top ward
          </span>
        )
      }
      bodyClassName="space-y-4 p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-2xl font-bold uppercase tracking-[0.08em]
            text-cyan-50 neon-text">
            {ward.ward.name}
          </h3>
          <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">
            {ward.floodedCellCount} of {ward.cellCount} km² cells flooding
          </p>
        </div>
        <TierBadge tier={ward.tier} size="md" pulse={ward.tier === 'CRITICAL'} />
      </div>

      <div className="space-y-3">
        <Meter
          label="Flood probability"
          value={ward.peakFloodProbability}
          display={percent(ward.peakFloodProbability)}
          color={TIER_COLORS[ward.tier]}
        />
        <Meter
          label="Expected water depth"
          value={Math.min(1, ward.peakWaterDepth / 1.5)}
          display={metres(ward.peakWaterDepth)}
          color="#22d3ee"
          hint={depthContext(ward.peakWaterDepth)}
        />
        <Meter
          label="Composite risk"
          value={ward.risk}
          display={ward.risk.toFixed(2)}
          color={TIER_COLORS[ward.tier]}
        />
      </div>

      <dl className="grid grid-cols-3 gap-3 border-t border-surface-hairline pt-3">
        <Field label="Time to inundation" value={duration(ward.timeToInundation)}
          hint={ward.timeToInundation !== null ? `~${clockAt(ward.timeToInundation)} IST` : 'no onset'} />
        <Field label="Population at risk" value={compactNumber(ward.populationAtRisk)}
          hint={fullNumber(ward.populationAtRisk)} />
        <Field
          label="Ensemble confidence"
          value={ward.confidence}
          hint="model agreement"
          color={CONFIDENCE_COLORS[ward.confidence]}
        />
      </dl>
    </Panel>
  );
}

function Field({
  label,
  value,
  hint,
  color,
}: {
  label: string;
  value: string;
  hint: string;
  color?: string;
}) {
  return (
    <div>
      <dt className="stat-label">{label}</dt>
      <dd
        className="font-display text-base font-bold tabular-nums"
        style={{
          color: color ?? '#cffafe',
          textShadow: `0 0 12px ${(color ?? '#22d3ee')}80`,
        }}
      >
        {value}
      </dd>
      <dd className="font-mono text-[10px] tracking-wide text-slate-500">{hint}</dd>
    </div>
  );
}

function depthContext(depth: number): string {
  if (depth >= 1.0) return 'Above vehicle bonnet height — roads impassable';
  if (depth >= 0.6) return 'Knee-deep — pedestrian movement unsafe';
  if (depth >= 0.3) return 'Ankle to shin deep — two-wheelers stall';
  if (depth >= 0.15) return 'Surface ponding on low-lying roads';
  return 'Below nuisance-flooding threshold';
}
