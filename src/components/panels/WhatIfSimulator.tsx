import { compactNumber, metres, percent } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';
import { Slider } from '@/components/ui/Slider';

/**
 * Inject a hypothetical rainfall / drainage scenario and see the impact delta
 * against the unmodified forecast for the same horizon.
 */
export function WhatIfSimulator({ className = '' }: { className?: string }) {
  const { whatIf, setWhatIf, resetWhatIf, regionSummary, baselineSummary, isSimulating } =
    useDashboard();

  // The backend scores the same horizon with the sliders at their defaults, so
  // the deltas below compare like with like.
  const baseline = baselineSummary;

  return (
    <Panel
      title="What-if simulator"
      className={className}
      actions={
        <button
          type="button"
          className="btn"
          onClick={resetWhatIf}
          disabled={!isSimulating}
        >
          Reset
        </button>
      }
      bodyClassName="space-y-4 px-4 pb-4"
    >
      <Slider
        label="Additional rainfall"
        value={whatIf.extraRainfall}
        min={0}
        max={150}
        step={5}
        display={`+${whatIf.extraRainfall} mm`}
        onChange={(extraRainfall) => setWhatIf({ extraRainfall })}
        hint="Injected over the 3-hour accumulation window"
      />
      <Slider
        label="Soil saturation"
        value={whatIf.soilSaturation}
        min={0.5}
        max={1.5}
        step={0.05}
        display={`${whatIf.soilSaturation.toFixed(2)}×`}
        onChange={(soilSaturation) => setWhatIf({ soilSaturation })}
        hint="Antecedent wetness from preceding days of rain"
      />
      <Slider
        label="Drainage capacity"
        value={whatIf.drainageCapacity}
        min={0.3}
        max={1.2}
        step={0.05}
        display={`${percent(whatIf.drainageCapacity)}`}
        onChange={(drainageCapacity) => setWhatIf({ drainageCapacity })}
        hint="Fraction of design capacity — drops when inlets choke"
      />

      <div className="grid grid-cols-3 gap-2">
        <Delta
          label="Population at risk"
          base={baseline.populationAtRisk}
          next={regionSummary.populationAtRisk}
          format={compactNumber}
        />
        <Delta
          label="Area flooding"
          base={baseline.floodedArea}
          next={regionSummary.floodedArea}
          format={(value) => `${value} km²`}
        />
        <Delta
          label="Peak depth"
          base={baseline.peakDepth}
          next={regionSummary.peakDepth}
          format={metres}
        />
      </div>
    </Panel>
  );
}

function Delta({
  label,
  base,
  next,
  format,
}: {
  label: string;
  base: number;
  next: number;
  format: (value: number) => string;
}) {
  const change = next - base;
  const tone = change > 0 ? 'text-tier-critical' : change < 0 ? 'text-tier-normal' : 'text-slate-600';

  return (
    <div className="tile">
      <p className="text-[10px] leading-tight text-slate-500">{label}</p>
      <p className="mt-1 text-[14px] font-semibold tabular-nums text-white">{format(next)}</p>
      <p className={`text-[10px] tabular-nums ${tone}`}>
        {change === 0 ? 'no change' : `${change > 0 ? '+' : '−'}${format(Math.abs(change))}`}
      </p>
    </div>
  );
}
