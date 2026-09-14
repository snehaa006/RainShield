import { useEffect, useRef, useState } from 'react';
import maplibregl, { type Map as MapLibreMap } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { REGION } from '@/lib/config';
import { cellPolygon } from '@/lib/grid';
import { INFRASTRUCTURE, INFRA_ICONS, INFRA_LABELS } from '@/lib/infrastructure';
import { useDashboard } from '@/hooks/useDashboard';
import { BASE_STYLE } from '@/components/map/mapStyle';
import { paintCell } from '@/components/map/layerPaint';
import type { Ward } from '@/types';

const GRID_SOURCE = 'grid';
const WARD_SOURCE = 'wards';

export function FloodMap() {
  const { cells, wards, activeLayer, showInfrastructure, selectedWardId, selectCell, selectWard } =
    useDashboard();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const labelsRef = useRef<maplibregl.Marker[]>([]);
  // `ready` is state rather than a ref because the data effects below have to
  // re-run once the style finishes loading: cells and wards now arrive from the
  // API and routinely beat the map to it.
  const [ready, setReady] = useState(false);

  // Latest handlers, so the map's event listeners are only bound once.
  const handlers = useRef({ selectCell, selectWard });
  handlers.current = { selectCell, selectWard };

  useEffect(() => {
    if (!containerRef.current) return undefined;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASE_STYLE,
      center: REGION.centre,
      zoom: 10.4,
      maxBounds: expand(REGION.bounds, 0.35),
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');

    // Fill the panel with the region rather than sitting at a fixed zoom, so a
    // wide container shows a correspondingly larger grid.
    map.fitBounds(REGION.bounds, { padding: 32, duration: 0 });

    map.on('load', () => {
      map.addSource(GRID_SOURCE, { type: 'geojson', data: emptyCollection() });
      map.addSource(WARD_SOURCE, { type: 'geojson', data: emptyCollection() });

      map.addLayer({
        id: 'grid-fill',
        type: 'fill',
        source: GRID_SOURCE,
        paint: { 'fill-color': ['get', 'color'], 'fill-opacity': ['get', 'opacity'] },
      });
      map.addLayer({
        id: 'grid-outline',
        type: 'line',
        source: GRID_SOURCE,
        paint: { 'line-color': '#0f172a', 'line-width': 0.3, 'line-opacity': 0.5 },
      });
      map.addLayer({
        id: 'ward-fill',
        type: 'fill',
        source: WARD_SOURCE,
        paint: {
          'fill-color': '#38bdf8',
          'fill-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 0.12, 0],
        },
      });
      map.addLayer({
        id: 'ward-outline',
        type: 'line',
        source: WARD_SOURCE,
        paint: {
          'line-color': '#64748b',
          'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2, 0.8],
          'line-opacity': 0.8,
        },
      });

      map.on('click', 'grid-fill', (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        handlers.current.selectCell(feature.properties?.id as string);
        handlers.current.selectWard(feature.properties?.wardId as string);
      });
      map.on('mouseenter', 'grid-fill', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'grid-fill', () => {
        map.getCanvas().style.cursor = '';
      });

      setReady(true);
    });

    return () => {
      setReady(false);
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      labelsRef.current.forEach((marker) => marker.remove());
      labelsRef.current = [];
      map.remove();
      mapRef.current = null;
    };
    // The map is created once; data updates flow through the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push new model output / layer selection into the grid source.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    refreshGrid(map, cells, activeLayer);
  }, [ready, cells, activeLayer]);

  // Ward outlines arrive with /api/region, so they are pushed in once available.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || wards.length === 0) return;
    const source = map.getSource(WARD_SOURCE) as maplibregl.GeoJSONSource | undefined;
    source?.setData(wardCollection(wards));

    labelsRef.current.forEach((marker) => marker.remove());
    labelsRef.current = wards.map((ward) => {
      const element = document.createElement('span');
      element.className =
        'pointer-events-none select-none text-[11px] font-medium text-slate-400 ' +
        '[text-shadow:0_1px_2px_#0b1220]';
      element.textContent = ward.name;
      return new maplibregl.Marker({ element }).setLngLat(ward.centre).addTo(map);
    });
  }, [ready, wards]);

  // Highlight the selected ward.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    wards.forEach((ward, index) => {
      map.setFeatureState(
        { source: WARD_SOURCE, id: index },
        { selected: ward.id === selectedWardId },
      );
    });
  }, [ready, wards, selectedWardId]);

  // Infrastructure overlay as DOM markers — few enough that symbols are overkill.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
    if (!showInfrastructure) return;

    markersRef.current = INFRASTRUCTURE.map((asset) => {
      const element = document.createElement('div');
      element.className =
        'flex h-5 w-5 items-center justify-center rounded-full border border-slate-300/70 ' +
        'bg-slate-900/85 text-[10px] text-slate-200 shadow';
      element.textContent = INFRA_ICONS[asset.type];
      element.title = `${asset.name} — ${INFRA_LABELS[asset.type]}`;
      return new maplibregl.Marker({ element }).setLngLat([asset.lon, asset.lat]).addTo(map);
    });
  }, [showInfrastructure]);

  return <div ref={containerRef} className="h-full w-full" />;
}

function refreshGrid(
  map: MapLibreMap,
  cells: ReturnType<typeof useDashboard>['cells'],
  layer: ReturnType<typeof useDashboard>['activeLayer'],
) {
  const source = map.getSource(GRID_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;

  source.setData({
    type: 'FeatureCollection',
    features: cells.map((cell, index) => ({
      type: 'Feature',
      id: index,
      geometry: { type: 'Polygon', coordinates: [cellPolygon(cell.row, cell.col)] },
      properties: {
        id: cell.id,
        wardId: cell.wardId,
        rainfall: cell.rainfallIntensity,
        floodProbability: cell.floodProbability,
        depth: cell.waterDepth,
        risk: cell.risk.total,
        tier: cell.tier,
        population: cell.population,
        ...paintCell(cell, layer),
      },
    })),
  });
}

function wardCollection(wards: Ward[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: wards.map((ward, index) => ({
      type: 'Feature',
      id: index,
      // A ward is a set of grid cells, so its outline can be several rings.
      geometry: { type: 'MultiPolygon', coordinates: ward.boundary.map((ring) => [ring]) },
      properties: { id: ward.id, name: ward.name },
    })),
  };
}

const emptyCollection = (): GeoJSON.FeatureCollection => ({
  type: 'FeatureCollection',
  features: [],
});

function expand(
  [west, south, east, north]: [number, number, number, number],
  padding: number,
): [number, number, number, number] {
  return [west - padding, south - padding, east + padding, north + padding];
}
