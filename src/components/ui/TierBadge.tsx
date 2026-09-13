import { TIER_COLORS, TIER_LABELS } from '@/lib/config';
import type { AlertTier } from '@/types';

interface TierBadgeProps {
  tier: AlertTier;
  size?: 'sm' | 'md';
  pulse?: boolean;
}

export function TierBadge({ tier, size = 'sm', pulse = false }: TierBadgeProps) {
  const color = TIER_COLORS[tier];
  const padding = size === 'md' ? 'px-3 py-1 text-[13px]' : 'px-2 py-0.5 text-[11px]';

  return (
    <span
      className={`clip-bevel inline-flex items-center gap-1.5 font-display font-semibold uppercase
        tracking-[0.16em] ${padding}`}
      style={{
        color,
        backgroundColor: `${color}1f`,
        border: `1px solid ${color}66`,
        boxShadow: `0 0 14px -3px ${color}, inset 0 0 12px -8px ${color}`,
        textShadow: `0 0 10px ${color}99`,
      }}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${pulse ? 'animate-hud-pulse' : ''}`}
        style={{ backgroundColor: color, boxShadow: `0 0 8px 1px ${color}` }}
      />
      {TIER_LABELS[tier]}
    </span>
  );
}
