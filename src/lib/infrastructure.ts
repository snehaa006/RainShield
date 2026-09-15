
import { mulberry32 } from '@/lib/math';
import type { PumpStationInfo, RegionDescriptor, ScoredCell } from '@/types';

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

/**
 * Critical assets to draw over a region.
 *
 * `stations` are the real ones the API serves, and they replace what used to
 * be four invented "Pumping Station 1..4" at random coordinates. Those were
 * drawn over real terrain next to real hospitals, which is exactly how an
 * invented asset ends up being read as a surveyed one. The remaining
 * categories are still laid out procedurally and still labelled generically;
 * they are placeholders for an OSM extract, not claims about specific
 * buildings.
 */
export function infrastructureFor(
  region: RegionDescriptor | null,
  stations: PumpStationInfo[] = [],
): InfraAsset[] {
  if (!region) return [];
  const key = `${region.id}:${stations.length}`;
  const cached = CACHE.get(key);
  if (cached) return cached;
  const built = [...buildInfrastructure(region), ...stationAssets(stations)];
  CACHE.set(key, built);
  return built;
}

function stationAssets(stations: PumpStationInfo[]): InfraAsset[] {
  return stations.map((station) => ({
    id: `pump-${station.id}`,
    name: station.name,
    type: 'pumping-station' as const,
    lon: station.lon,
    lat: station.lat,
  }));
}

/** Assets whose cell is expected to flood, ordered by severity. */
export function exposedAssets(
  cells: ScoredCell[],
  region: RegionDescriptor | null,
  stations: PumpStationInfo[] = [],
): (InfraAsset & { depth: number })[] {
  if (!region) return [];
  const byKey = new Map(cells.map((c) => [`${c.col}:${c.row}`, c]));
  const [west, south, east, north] = region.bounds;
  const cellWidth = (east - west) / region.cols;
  const cellHeight = (north - south) / region.rows;

  return infrastructureFor(region, stations).map((asset) => {
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
