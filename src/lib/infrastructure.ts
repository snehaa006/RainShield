
import { mulberry32 } from '@/lib/math';
import type { RegionDescriptor, ScoredCell } from '@/types';

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

/**
 * OSM-derived critical assets, laid out inside a region's extent.
 *
 * Seeded on the region id so each region gets a stable set of its own rather
 * than every region inheriting the first one's coordinates.
 */
const CACHE = new Map<string, InfraAsset[]>();

export function infrastructureFor(region: RegionDescriptor | null): InfraAsset[] {
  if (!region) return [];
  const cached = CACHE.get(region.id);
  if (cached) return cached;
  const built = buildInfrastructure(region);
  CACHE.set(region.id, built);
  return built;
}

/** Assets whose cell is expected to flood, ordered by severity. */
export function exposedAssets(
  cells: ScoredCell[],
  region: RegionDescriptor | null,
): (InfraAsset & { depth: number })[] {
  if (!region) return [];
  const byKey = new Map(cells.map((c) => [`${c.col}:${c.row}`, c]));
  const [west, south, east, north] = region.bounds;
  const cellWidth = (east - west) / region.cols;
  const cellHeight = (north - south) / region.rows;

  return infrastructureFor(region).map((asset) => {
    const col = Math.floor((asset.lon - west) / cellWidth);
    const row = Math.floor((asset.lat - south) / cellHeight);
    const cell = byKey.get(`${col}:${row}`);
    return { ...asset, depth: cell?.waterDepth ?? 0 };
  })
    .filter((asset) => asset.depth >= 0.15)
    .sort((a, b) => b.depth - a.depth);
}

function buildInfrastructure(region: RegionDescriptor): InfraAsset[] {
  // Seed from the region id so two regions do not share a layout.
  const random = mulberry32(
    [...region.id].reduce((acc, ch) => (acc * 31 + ch.charCodeAt(0)) >>> 0, 4242),
  );
  const [west, south, east, north] = region.bounds;
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
