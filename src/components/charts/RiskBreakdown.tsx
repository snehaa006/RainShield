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
  const color = TIER_COLORS[tier];

  return (
    <div className="space-y-2">
      {keys.map((key) => {
        const contribution = risk.components[key] * RISK_WEIGHTS[key];
        return (
          <div key={key} className="space-y-1">
            <div className="flex items-baseline justify-between gap-2 text-[11px]">
              <span className="text-slate-400">
                {LABELS[key]}
                <span className="ml-1 font-mono text-hud/50">×{RISK_WEIGHTS[key]}</span>
              </span>
              <span className="font-mono tabular-nums text-slate-300">
                {percent(risk.components[key])} → {contribution.toFixed(3)}
              </span>
            </div>
            <div
              className="h-1.5 border border-surface-hairline bg-surface-deep/80"
              style={{
                backgroundImage:
                  'repeating-linear-gradient(90deg, rgba(56,189,248,0.10) 0 3px, transparent 3px 6px)',
              }}
            >
              <div
                className="h-full transition-[width] duration-500"
                style={{
                  // Scaled against the largest weight so bars stay comparable.
                  width: `${(contribution / RISK_WEIGHTS.rainfallSeverity) * 100}%`,
                  background: `linear-gradient(90deg, ${color}66, ${color})`,
                  boxShadow: `0 0 10px 0 ${color}`,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
