import { DEPTH_RAMP, RAINFALL_RAMP, TIER_COLORS } from '@/lib/config';
import { sampleRamp } from '@/lib/math';
import type { LayerId, ScoredCell } from '@/types';

interface LayerPaint {
  color: string;
  opacity: number;
}

/** Colour and opacity for one cell under the active map layer. */
export function paintCell(cell: ScoredCell, layer: LayerId): LayerPaint {
  switch (layer) {
    case 'rainfall':
      return {
        color: sampleRamp(RAINFALL_RAMP, cell.rainfallIntensity),
        opacity: cell.rainfallIntensity < 1 ? 0 : 0.18 + Math.min(0.6, cell.rainfallIntensity / 110),
      };
    case 'flood':
      return {
        color: sampleRamp(DEPTH_RAMP, cell.waterDepth),
        opacity: cell.floodProbability < 0.25 ? 0 : 0.2 + cell.floodProbability * 0.6,
      };
    case 'risk':
    default:
      return {
        color: TIER_COLORS[cell.tier],
        opacity: cell.tier === 'NORMAL' ? 0.14 : 0.22 + cell.risk.total * 0.55,
      };
  }
}

export const LAYER_OPTIONS: { id: LayerId; label: string }[] = [
  { id: 'risk', label: 'Composite risk' },
  { id: 'rainfall', label: 'Rainfall intensity' },
  { id: 'flood', label: 'Flood depth' },
];
