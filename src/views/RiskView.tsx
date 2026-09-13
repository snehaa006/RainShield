import { RISK_WEIGHTS } from '@/lib/config';
import { percent } from '@/lib/format';
import { MetricsStrip } from '@/components/panels/MetricsStrip';
import { NowcastTimeline } from '@/components/panels/NowcastTimeline';
import { WhatIfSimulator } from '@/components/panels/WhatIfSimulator';
import { CellInspector } from '@/components/panels/CellInspector';
import { RainfallTrend } from '@/components/charts/RainfallTrend';
import { Panel } from '@/components/ui/Panel';

const WEIGHT_LABELS: Record<keyof typeof RISK_WEIGHTS, string> = {
  rainfallSeverity: 'Rainfall severity',
  floodProbability: 'Flood probability',
  waterDepth: 'Water depth',
  populationExposure: 'Population exposure',
  criticalInfra: 'Critical infrastructure',
};

/** Model workbench: tune the scenario, read the weights, inspect one cell. */
export function RiskView() {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <MetricsStrip />
      <NowcastTimeline />

      <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[360px_minmax(0,1fr)]">
        {/* Controls and reference on the left, output on the right. */}
        <div className="flex min-h-0 flex-col gap-3 overflow-y-auto scroll-thin xl:pr-0.5">
          <WhatIfSimulator />
          <WeightsPanel />
        </div>

        <div className="flex min-h-0 flex-col gap-3">
          <CellInspector className="max-h-[55%] shrink-0" />
          <RainfallTrend className="min-h-[220px] flex-1" />
        </div>
      </div>
    </div>
  );
}

/** The composite score is a weighted sum — show the weights behind it. */
function WeightsPanel() {
  const keys = Object.keys(RISK_WEIGHTS) as (keyof typeof RISK_WEIGHTS)[];

  return (
    <Panel title="Composite risk weights">
      <ul className="space-y-2">
        {keys.map((key) => (
          <li key={key} className="flex items-center gap-3">
            <span className="w-36 shrink-0 text-[12px] text-slate-300">{WEIGHT_LABELS[key]}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.08]">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${(RISK_WEIGHTS[key] / 0.35) * 100}%` }}
              />
            </div>
            <span className="w-9 text-right text-[12px] tabular-nums text-slate-400">
              {percent(RISK_WEIGHTS[key])}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
        Each 1 km cell scores 0–1 on every term; the weighted sum sets its warning tier. Weights
        are tunable against past events.
      </p>
    </Panel>
  );
}
