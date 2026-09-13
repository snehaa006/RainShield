import { useMemo } from 'react';
import { DEFAULT_WHAT_IF } from '@/lib/config';
import { getForecast } from '@/lib/forecast';
import { compactNumber, metres, percent } from '@/lib/format';
import { summariseRegion } from '@/lib/riskEngine';
import { useDashboard } from '@/hooks/useDashboard';
import { Panel } from '@/components/ui/Panel';
import { Slider } from '@/components/ui/Slider';

/**
 * Inject a hypothetical rainfall / drainage scenario and see the impact delta
 * against the unmodified forecast for the same horizon.
 */
export function WhatIfSimulator() {
  const { scenario, lead, whatIf, setWhatIf, resetWhatIf, regionSummary, isSimulating } =
    useDashboard();

  const baseline = useMemo(
    () => summariseRegion(getForecast(scenario, lead, DEFAULT_WHAT_IF)),
    [scenario, lead],
  );

  return (
    <Panel
      title="What-if simulator"
      actions={
        <button
          type="button"
          className="chip"
          onClick={resetWhatIf}
          disabled={!isSimulating}
        >
          Reset
        </button>
      }
      bodyClassName="space-y-4 p-4"
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

      <div className="grid grid-cols-3 gap-2 border-t border-surface-border pt-3">
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
  const tone = change > 0 ? 'text-rose-400' : change < 0 ? 'text-emerald-400' : 'text-slate-500';

  return (
    <div>
      <p className="stat-label">{label}</p>
      <p className="text-sm font-semibold tabular-nums text-slate-100">{format(next)}</p>
      <p className={`text-[11px] tabular-nums ${tone}`}>
        {change === 0 ? 'no change' : `${change > 0 ? '+' : '−'}${format(Math.abs(change))}`}
      </p>
    </div>
  );
}
