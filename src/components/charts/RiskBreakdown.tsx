import { RISK_WEIGHTS, TIER_COLORS } from '@/lib/config';
import { percent } from '@/lib/format';
import type { RiskScore } from '@/types';

const LABELS: Record<keyof RiskScore['components'], string> = {
  rainfallSeverity: 'Rainfall severity',
  floodProbability: 'Flood probability',
  waterDepth: 'Water depth',
  populationExposure: 'Population exposure',
  criticalInfra: 'Critical infrastructure',
};

/** Weighted contribution of each term to a cell's composite risk score. */
export function RiskBreakdown({ risk, tier }: { risk: RiskScore; tier: keyof typeof TIER_COLORS }) {
  const keys = Object.keys(LABELS) as (keyof RiskScore['components'])[];

  return (
    <div className="space-y-2">
      {keys.map((key) => {
        const contribution = risk.components[key] * RISK_WEIGHTS[key];
        return (
          <div key={key} className="space-y-1">
            <div className="flex items-baseline justify-between gap-2 text-[11px]">
              <span className="text-slate-400">
                {LABELS[key]}
                <span className="ml-1 text-slate-600">×{RISK_WEIGHTS[key]}</span>
              </span>
              <span className="tabular-nums text-slate-300">
                {percent(risk.components[key])} → {contribution.toFixed(3)}
              </span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full"
                style={{
                  // Scaled against the largest weight so bars stay comparable.
                  width: `${(contribution / RISK_WEIGHTS.rainfallSeverity) * 100}%`,
                  backgroundColor: TIER_COLORS[tier],
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
