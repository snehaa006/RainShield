import { CONFIDENCE_COLORS, TIER_COLORS } from '@/lib/config';
import { clockAt, compactNumber, duration, fullNumber, metres, percent } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';
import { Meter } from '@/components/ui/Meter';
import { Panel } from '@/components/ui/Panel';
import { TierBadge } from '@/components/ui/TierBadge';

/** Alert intelligence: why this ward is alerting and how much time is left. */
export function AlertPanel({ className = '' }: { className?: string }) {
  const { selectedWard, wardSummaries, selectWard } = useDashboard();
  const ward = selectedWard ?? wardSummaries[0];

  if (!ward) return null;

  return (
    <Panel
      title="Alert intelligence"
      className={className}
      actions={
        selectedWard ? (
          <button type="button" className="btn" onClick={() => selectWard(null)}>
            Top ward
          </button>
        ) : (
          <span className="text-[11px] text-slate-500">Highest risk</span>
        )
      }
      bodyClassName="space-y-4 px-4 pb-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[22px] font-semibold leading-tight tracking-tight text-white">
            {ward.ward.name}
          </h3>
          <p className="text-[11px] text-slate-500">
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
          color="#0a84ff"
          hint={depthContext(ward.peakWaterDepth)}
        />
        <Meter
          label="Composite risk"
          value={ward.risk}
          display={ward.risk.toFixed(2)}
          color={TIER_COLORS[ward.tier]}
        />
      </div>

      <dl className="grid grid-cols-3 gap-2">
        <Field
          label="Time to inundation"
          value={duration(ward.timeToInundation)}
          hint={ward.timeToInundation !== null ? `~${clockAt(ward.timeToInundation)} IST` : 'no onset'}
        />
        <Field
          label="Population at risk"
          value={compactNumber(ward.populationAtRisk)}
          hint={fullNumber(ward.populationAtRisk)}
        />
        <Field
          label="Confidence"
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
    <div className="tile">
      <dt className="text-[10px] leading-tight text-slate-500">{label}</dt>
      <dd className="mt-1 text-[14px] font-semibold tabular-nums" style={{ color: color ?? '#fff' }}>
        {value}
      </dd>
      <dd className="text-[10px] text-slate-600">{hint}</dd>
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
