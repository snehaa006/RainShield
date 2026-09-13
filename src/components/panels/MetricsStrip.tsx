import { compactNumber, duration, metres, mmPerHour } from '@/lib/format';
import { useDashboard } from '@/hooks/useDashboard';

/** Headline KPI tiles — big glowing numerals across the top of the board. */
export function MetricsStrip() {
  const { regionSummary, isSimulating } = useDashboard();

  const metrics = [
    {
      label: 'Peak risk score',
      value: regionSummary.peakRisk.toFixed(2),
      hint: 'composite, 0–1',
      accent: '#f97316',
    },
    {
      label: 'Peak rainfall',
      value: mmPerHour(regionSummary.peakRainfall),
      hint: 'nowcast max',
      accent: '#22d3ee',
    },
    {
      label: 'Peak depth',
      value: metres(regionSummary.peakDepth),
      hint: 'standing water',
      accent: '#38bdf8',
    },
    {
      label: 'Population at risk',
      value: compactNumber(regionSummary.populationAtRisk),
      hint: 'probability-weighted',
      accent: '#eab308',
    },
    {
      label: 'Area flooding',
      value: `${regionSummary.floodedArea} km²`,
      hint: 'cells with P ≥ 0.5',
      accent: '#a78bfa',
    },
    {
      label: 'Lead time',
      value: duration(regionSummary.leadTime),
      hint: 'to first inundation',
      accent: '#34d399',
    },
  ];

  return (
    <div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        {metrics.map((metric) => (
          <div
            key={metric.label}
            className="group relative overflow-hidden border border-surface-border
              bg-surface-raised px-3 py-2.5 backdrop-blur-md transition-all duration-300
              clip-notch hover:border-hud/50"
            style={{
              backgroundImage: `linear-gradient(150deg, ${metric.accent}1f 0%, rgba(8,20,36,0) 55%)`,
            }}
          >
            {/* Accent spine down the left edge. */}
            <span
              className="absolute inset-y-0 left-0 w-[3px]"
              style={{
                backgroundColor: metric.accent,
                boxShadow: `0 0 12px 0 ${metric.accent}`,
              }}
            />
            <p className="stat-label">{metric.label}</p>
            <p
              className="mt-1 font-display text-[21px] font-bold leading-none tabular-nums
                2xl:text-[26px]"
              style={{ color: metric.accent, textShadow: `0 0 18px ${metric.accent}80` }}
            >
              {metric.value}
            </p>
            <p className="mt-1 font-mono text-[10px] tracking-wide text-slate-500">{metric.hint}</p>
          </div>
        ))}
      </div>

      {isSimulating && (
        <p className="mt-2 flex items-center gap-2 border border-hud/40 bg-hud/10 px-3 py-1.5
          font-mono text-[10px] uppercase tracking-[0.14em] text-cyan-200 clip-bevel">
          <span className="h-1.5 w-1.5 animate-hud-pulse rounded-full bg-hud" />
          Simulated scenario — figures include what-if adjustments, not the live forecast.
        </p>
      )}
    </div>
  );
}
