import { compactNumber, duration, metres, mmPerHour } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';

export function MetricsStrip() {
  const { regionSummary, isSimulating } = useDashboard();

  const metrics = [
    { label: 'Peak risk score', value: regionSummary.peakRisk.toFixed(2), hint: 'composite, 0–1' },
    { label: 'Peak rainfall', value: mmPerHour(regionSummary.peakRainfall), hint: 'nowcast max' },
    { label: 'Peak depth', value: metres(regionSummary.peakDepth), hint: 'standing water' },
    {
      label: 'Population at risk',
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
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border
      border-surface-border bg-surface-border sm:grid-cols-3 xl:grid-cols-6">
      {metrics.map((metric) => (
        <div key={metric.label} className="bg-surface-raised px-4 py-3">
          <p className="stat-label">{metric.label}</p>
          <p className="stat-value mt-0.5">{metric.value}</p>
          <p className="text-[11px] text-slate-500">{metric.hint}</p>
        </div>
      ))}
      {isSimulating && (
        <p className="col-span-full bg-sky-500/10 px-4 py-1.5 text-[11px] text-sky-300">
          Simulated scenario — figures include what-if adjustments, not the live forecast.
        </p>
      )}
    </div>
  );
}
