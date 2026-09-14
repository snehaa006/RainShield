/**
 * Grid geometry, assembled from the backend's static layers.
 *
 * This used to generate terrain from seeded noise. It now builds the same
 * structures from `/api/region`, which serves the real SRTM/WorldPop/OSM layers
 * out of the Stage 1 tensor — the exact values the model was trained on.
 */

import { REGION } from '@/lib/config';
import type { RegionPayload } from '@/lib/api';
import type { GridCellStatic, LandUse, Ward } from '@/types';

/**
 * Flat index of a cell. Must match the backend, which ravels a (rows, cols)
 * array row-major with row 0 on the northern edge.
 */
export const cellIndex = (row: number, col: number): number => row * REGION.cols + col;

/** Cell footprint as a closed GeoJSON-ready ring. */
export function cellPolygon(row: number, col: number): [number, number][] {
  const [west, south, east, north] = REGION.bounds;
  const width = (east - west) / REGION.cols;
  const height = (north - south) / REGION.rows;

  const x0 = west + col * width;
  const x1 = x0 + width;
  const y1 = north - row * height; // row 0 is the northern edge
  const y0 = y1 - height;

  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
    [x0, y0],
  ];
}

/** Build the static cell list from the region payload. */
export function buildGrid(payload: RegionPayload): GridCellStatic[] {
  const { cells, wards, region } = payload;
  const out: GridCellStatic[] = [];

  for (let row = 0; row < region.rows; row += 1) {
    for (let col = 0; col < region.cols; col += 1) {
      const i = row * region.cols + col;
      out.push({
        id: `c-${col}-${row}`,
        row,
        col,
        lon: cells.lon[i],
        lat: cells.lat[i],
        wardId: wards[cells.wardIndex[i]]?.id ?? 'unassigned',
        elevation: cells.elevation[i],
        slope: cells.slope[i],
        landUse: cells.landUse[i] as LandUse,
        population: cells.population[i],
        criticalInfraProximity: cells.infraProximity[i],
      });
    }
  }
  return out;
}

/**
 * Build ward outlines by dissolving their member cells.
 *
 * The backend assigns each cell to its nearest ward centre, so a ward is a set
 * of grid cells rather than a polygon. Taking every cell edge that exactly one
 * of the ward's cells owns leaves only the outer boundary, and stitching those
 * edges end-to-end turns them into rings. Drawing the cells directly would
 * show all the interior edges instead.
 */
export function buildWards(payload: RegionPayload): Ward[] {
  const { cells, wards, region } = payload;
  const [west, south, east, north] = region.bounds;
  const width = (east - west) / region.cols;
  const height = (north - south) / region.rows;

  // Work in integer lattice coordinates so shared edges compare exactly.
  const key = (x: number, y: number) => `${x},${y}`;
  const toLngLat = (x: number, y: number): [number, number] => [
    west + x * width,
    north - y * height,
  ];

  return wards.map((ward, wardIdx) => {
    const edges = new Map<string, [number, number, number, number]>();

    for (let row = 0; row < region.rows; row += 1) {
      for (let col = 0; col < region.cols; col += 1) {
        if (cells.wardIndex[row * region.cols + col] !== wardIdx) continue;
        // Four edges of this cell, each as an ordered vertex pair.
        const corners: [number, number, number, number][] = [
          [col, row, col + 1, row],
          [col + 1, row, col + 1, row + 1],
          [col + 1, row + 1, col, row + 1],
          [col, row + 1, col, row],
        ];
        for (const edge of corners) {
          const [x1, y1, x2, y2] = edge;
          // An interior edge is traversed once in each direction; cancel both.
          const opposite = `${key(x2, y2)}|${key(x1, y1)}`;
          if (edges.has(opposite)) edges.delete(opposite);
          else edges.set(`${key(x1, y1)}|${key(x2, y2)}`, edge);
        }
      }
    }

    return {
      id: ward.id,
      name: ward.name,
      centre: [ward.lon, ward.lat] as [number, number],
      boundary: stitchRings(edges, toLngLat),
    };
  });
}

/** Chain boundary edges into closed rings, following each vertex to the next. */
function stitchRings(
  edges: Map<string, [number, number, number, number]>,
  toLngLat: (x: number, y: number) => [number, number],
): [number, number][][] {
  const next = new Map<string, [number, number, number, number][]>();
  for (const edge of edges.values()) {
    const from = `${edge[0]},${edge[1]}`;
    const list = next.get(from);
    if (list) list.push(edge);
    else next.set(from, [edge]);
  }

  const rings: [number, number][][] = [];
  const remaining = new Set(edges.values());

  while (remaining.size > 0) {
    const start = remaining.values().next().value as [number, number, number, number];
    const ring: [number, number][] = [toLngLat(start[0], start[1])];

    let edge: [number, number, number, number] | undefined = start;
    while (edge) {
      remaining.delete(edge);
      const candidates = next.get(`${edge[2]},${edge[3]}`);
      const following = candidates?.find((candidate) => remaining.has(candidate));
      ring.push(toLngLat(edge[2], edge[3]));
      if (!following) break;
      edge = following;
    }

    // Close the ring; drop degenerate fragments that cannot form a polygon.
    if (ring.length > 3) {
      const [firstLon, firstLat] = ring[0];
      const [lastLon, lastLat] = ring[ring.length - 1];
      if (firstLon !== lastLon || firstLat !== lastLat) ring.push(ring[0]);
      rings.push(ring);
    }
  }

  return rings;
}
