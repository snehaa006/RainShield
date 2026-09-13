import { REGION } from '@/lib/config';
import { mulberry32 } from '@/lib/math';
import type { ScoredCell } from '@/types';

export type InfraType = 'hospital' | 'school' | 'bridge' | 'shelter' | 'pumping-station';

export interface InfraAsset {
  id: string;
  name: string;
  type: InfraType;
  lon: number;
  lat: number;
}

export const INFRA_LABELS: Record<InfraType, string> = {
  hospital: 'Hospital',
  school: 'School',
  bridge: 'Bridge / underpass',
  shelter: 'Relief shelter',
  'pumping-station': 'Pumping station',
};

export const INFRA_ICONS: Record<InfraType, string> = {
  hospital: '✚',
  school: '✎',
  bridge: '⌇',
  shelter: '⌂',
  'pumping-station': '⚙',
};

/** OSM-derived critical assets. Seeded so the demo region is stable. */
export const INFRASTRUCTURE: InfraAsset[] = buildInfrastructure();

/** Assets whose cell is expected to flood, ordered by severity. */
export function exposedAssets(cells: ScoredCell[]): (InfraAsset & { depth: number })[] {
  const byKey = new Map(cells.map((c) => [`${c.col}:${c.row}`, c]));
  const [west, south, east, north] = REGION.bounds;
  const cellWidth = (east - west) / REGION.cols;
  const cellHeight = (north - south) / REGION.rows;

  return INFRASTRUCTURE.map((asset) => {
    const col = Math.floor((asset.lon - west) / cellWidth);
    const row = Math.floor((asset.lat - south) / cellHeight);
    const cell = byKey.get(`${col}:${row}`);
    return { ...asset, depth: cell?.waterDepth ?? 0 };
  })
    .filter((asset) => asset.depth >= 0.15)
    .sort((a, b) => b.depth - a.depth);
}

function buildInfrastructure(): InfraAsset[] {
  const random = mulberry32(4242);
  const [west, south, east, north] = REGION.bounds;
  const plan: { type: InfraType; count: number; prefix: string }[] = [
    { type: 'hospital', count: 6, prefix: 'Civic Hospital' },
    { type: 'school', count: 9, prefix: 'Municipal School' },
    { type: 'bridge', count: 7, prefix: 'Underpass' },
    { type: 'shelter', count: 5, prefix: 'Relief Centre' },
    { type: 'pumping-station', count: 4, prefix: 'Pumping Station' },
  ];

  return plan.flatMap(({ type, count, prefix }) =>
    Array.from({ length: count }, (_, i) => ({
      id: `${type}-${i}`,
      name: `${prefix} ${i + 1}`,
      type,
      lon: west + random() * (east - west),
      lat: south + random() * (north - south),
    })),
  );
}
