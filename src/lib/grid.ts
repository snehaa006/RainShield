import { REGION } from '@/lib/config';
import { clamp, fbm } from '@/lib/math';
import type { GridCellStatic, LandUse, Ward } from '@/types';

const SEED = 20260913;
const [west, south, east, north] = REGION.bounds;
const CELL_WIDTH = (east - west) / REGION.cols;
const CELL_HEIGHT = (north - south) / REGION.rows;

const WARD_NAMES = [
  'Andheri West',
  'Andheri East',
  'Jogeshwari',
  'Goregaon',
  'Malad',
  'Kurla',
  'Chembur',
  'Bandra East',
  'Santacruz',
  'Vile Parle',
  'Powai',
  'Ghatkopar',
];

const WARD_COLS = 3;
const WARD_ROWS = 4;

export const WARDS: Ward[] = buildWards();

/**
 * Static terrain, land-use and exposure layers for the demo region.
 *
 * In production these come from the fusion engine (SRTM/Cartosat DEM, Bhuvan
 * LULC, OSM infrastructure, gridded census). Here they are generated from
 * seeded noise so the demo is deterministic and needs no network access.
 */
export const GRID: GridCellStatic[] = buildGrid();

/** Cell footprint as a GeoJSON-ready ring. */
export function cellPolygon(cell: GridCellStatic): [number, number][] {
  const x = west + cell.col * CELL_WIDTH;
  const y = south + cell.row * CELL_HEIGHT;
  return [
    [x, y],
    [x + CELL_WIDTH, y],
    [x + CELL_WIDTH, y + CELL_HEIGHT],
    [x, y + CELL_HEIGHT],
    [x, y],
  ];
}

function buildGrid(): GridCellStatic[] {
  const cells: GridCellStatic[] = [];

  for (let row = 0; row < REGION.rows; row += 1) {
    for (let col = 0; col < REGION.cols; col += 1) {
      const nx = col / REGION.cols;
      const ny = row / REGION.rows;

      // A coastal plain rising to a low ridge inland, plus local relief.
      const ridge = Math.sin(ny * Math.PI) * 38;
      const elevation = clamp(
        2 + ridge * nx + fbm(nx * 6, ny * 6, SEED) * 30 - 6,
        0.5,
        90,
      );
      const slope = clamp(fbm(nx * 8, ny * 8, SEED + 11) * 14, 0.2, 14);

      // Drainage runs roughly north-south through the middle of the region.
      const creekX = 0.42 + 0.16 * Math.sin(ny * Math.PI * 1.6);
      const distanceToDrainage = clamp(
        Math.abs(nx - creekX) * 14 + fbm(nx * 5, ny * 5, SEED + 7) * 1.4,
        0.05,
        12,
      );

      const urbanisation = clamp(
        1 - Math.hypot(nx - 0.45, ny - 0.5) * 1.5 + fbm(nx * 4, ny * 4, SEED + 3) * 0.5,
      );

      cells.push({
        id: `c-${col}-${row}`,
        col,
        row,
        lon: west + (col + 0.5) * CELL_WIDTH,
        lat: south + (row + 0.5) * CELL_HEIGHT,
        wardId: wardIdFor(col, row),
        elevation: round(elevation, 1),
        slope: round(slope, 1),
        distanceToDrainage: round(distanceToDrainage, 2),
        landUse: landUseFor(urbanisation, elevation),
        population: Math.round(1200 + urbanisation * 38_000 * (0.6 + fbm(nx * 7, ny * 7, SEED + 5))),
        criticalInfraProximity: round(
          clamp(urbanisation * 0.7 + fbm(nx * 9, ny * 9, SEED + 13) * 0.5),
          2,
        ),
      });
    }
  }

  return cells;
}

function landUseFor(urbanisation: number, elevation: number): LandUse {
  if (elevation < 2.5) return 'water';
  if (urbanisation > 0.72) return 'urban-dense';
  if (urbanisation > 0.5) return 'urban';
  if (urbanisation > 0.3) return 'periurban';
  return 'vegetation';
}

function wardIndex(col: number, row: number): number {
  const wc = Math.min(WARD_COLS - 1, Math.floor((col / REGION.cols) * WARD_COLS));
  const wr = Math.min(WARD_ROWS - 1, Math.floor((row / REGION.rows) * WARD_ROWS));
  return wr * WARD_COLS + wc;
}

function wardIdFor(col: number, row: number): string {
  return `w-${wardIndex(col, row)}`;
}

function buildWards(): Ward[] {
  return WARD_NAMES.map((name, index) => {
    const wc = index % WARD_COLS;
    const wr = Math.floor(index / WARD_COLS);
    const x0 = west + (wc / WARD_COLS) * (east - west);
    const x1 = west + ((wc + 1) / WARD_COLS) * (east - west);
    const y0 = south + (wr / WARD_ROWS) * (north - south);
    const y1 = south + ((wr + 1) / WARD_ROWS) * (north - south);

    return {
      id: `w-${index}`,
      name,
      boundary: [
        [x0, y0],
        [x1, y0],
        [x1, y1],
        [x0, y1],
        [x0, y0],
      ] as [number, number][],
    };
  });
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
