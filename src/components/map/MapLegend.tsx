import { DEPTH_RAMP, RAINFALL_RAMP, TIER_COLORS, TIER_LABELS } from '@/lib/config';
import { useDashboard } from '@/hooks/useDashboard';
import type { AlertTier } from '@/types';

const TIERS: AlertTier[] = ['NORMAL', 'WATCH', 'WARNING', 'CRITICAL'];

export function MapLegend() {
  const { activeLayer } = useDashboard();

  return (
    <div className="pointer-events-auto w-56 border border-surface-border bg-surface-deep/85 p-3
      backdrop-blur-md clip-notch shadow-[0_0_24px_-10px_rgba(34,211,238,0.8)]">
      {activeLayer === 'risk' ? (
        <>
          <p className="stat-label mb-2 text-hud/70">Warning tier</p>
          <ul className="space-y-1.5">
            {TIERS.map((tier) => (
              <li
                key={tier}
                className="flex items-center gap-2 font-mono text-[11px] uppercase
                  tracking-[0.1em] text-slate-300"
              >
                <span
                  className="h-2.5 w-2.5 rotate-45"
                  style={{
                    backgroundColor: TIER_COLORS[tier],
                    boxShadow: `0 0 8px 0 ${TIER_COLORS[tier]}`,
                  }}
                />
                {TIER_LABELS[tier]}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <Ramp
          label={activeLayer === 'rainfall' ? 'Rainfall intensity' : 'Water depth'}
          unit={activeLayer === 'rainfall' ? 'mm/hr' : 'm'}
          stops={activeLayer === 'rainfall' ? RAINFALL_RAMP : DEPTH_RAMP}
        />
      )}
    </div>
  );
}

function Ramp({
  label,
  unit,
  stops,
}: {
  label: string;
  unit: string;
  stops: { value: number; color: string }[];
}) {
  const gradient = stops
    .map((stop, i) => `${stop.color} ${(i / (stops.length - 1)) * 100}%`)
    .join(', ');

  return (
    <>
      <p className="stat-label mb-2 text-hud/70">
        {label} <span className="text-slate-600">({unit})</span>
      </p>
      <div
        className="h-2.5 border border-surface-hairline"
        style={{
          background: `linear-gradient(90deg, ${gradient})`,
          boxShadow: '0 0 14px -4px rgba(34, 211, 238, 0.9)',
        }}
      />
      <div className="mt-1 flex justify-between font-mono text-[10px] tabular-nums text-slate-500">
        <span>{stops[0].value}</span>
        <span>{stops[Math.floor(stops.length / 2)].value}</span>
        <span>{stops.at(-1)!.value}+</span>
      </div>
    </>
  );
}
