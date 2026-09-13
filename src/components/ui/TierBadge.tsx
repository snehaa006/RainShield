import { TIER_COLORS, TIER_LABELS } from '@/lib/config';
import type { AlertTier } from '@/types';

interface TierBadgeProps {
  tier: AlertTier;
  size?: 'sm' | 'md';
  pulse?: boolean;
}

export function TierBadge({ tier, size = 'sm', pulse = false }: TierBadgeProps) {
  const color = TIER_COLORS[tier];
  const padding = size === 'md' ? 'px-2.5 py-1 text-[12px]' : 'px-2 py-0.5 text-[10px]';

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold ${padding}`}
      style={{ color, backgroundColor: `${color}1a` }}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${pulse ? 'animate-soft-pulse' : ''}`}
        style={{ backgroundColor: color }}
      />
      {TIER_LABELS[tier]}
    </span>
  );
}
