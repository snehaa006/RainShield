import { compactNumber, duration, metres, mmPerHour } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';

/** Compact KPI row for the map and risk views. */
export function MetricsStrip() {
  const { regionSummary, isSimulating } = useDashboard();

  const metrics = [
    { label: 'Peak risk', value: regionSummary.peakRisk.toFixed(2), hint: 'composite, 0–1' },
    { label: 'Peak rainfall', value: mmPerHour(regionSummary.peakRainfall), hint: 'nowcast max' },
    { label: 'Peak depth', value: metres(regionSummary.peakDepth), hint: 'standing water' },
    {
      label: 'People at risk',
      value: compactNumber(regionSummary.populationAtRisk),
      hint: 'probability-weighted',
    },
    {
      label: 'Area flooding',
      value: `${regionSummary.floodedArea} km²`,
      hint: 'cells with P ≥ 0.5',
    },
    { label: 'Lead time', value: duration(regionSummary.leadTime), hint: 'to first inundation' },
  ];

  return (
    <div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        {metrics.map((metric) => (
          <div key={metric.label} className="panel px-3 py-2.5">
            <p className="text-[11px] text-slate-500">{metric.label}</p>
            <p className="mt-1 text-[19px] font-semibold leading-none tabular-nums tracking-tight
              text-white">
              {metric.value}
            </p>
            <p className="mt-1 text-[10px] text-slate-600">{metric.hint}</p>
          </div>
        ))}
      </div>

      {isSimulating && (
        <p className="mt-2 flex items-center gap-2 rounded-[10px] bg-accent-soft px-3 py-1.5
          text-[11px] text-accent">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          Simulated scenario — figures include what-if adjustments, not the live forecast.
        </p>
      )}
    </div>
  );
}
