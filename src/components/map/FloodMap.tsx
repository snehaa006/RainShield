import { useEffect, useRef } from 'react';
import maplibregl, { type Map as MapLibreMap } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { REGION } from '@/lib/config';
import { toGeoJson } from '@/lib/forecast';
import { WARDS } from '@/lib/grid';
import { INFRASTRUCTURE, INFRA_ICONS, INFRA_LABELS } from '@/lib/infrastructure';
import { useDashboard } from '@/hooks/useDashboard';
import { BASE_STYLE } from '@/components/map/mapStyle';
import { paintCell } from '@/components/map/layerPaint';

const GRID_SOURCE = 'grid';
const WARD_SOURCE = 'wards';

export function FloodMap() {
  const { cells, activeLayer, showInfrastructure, selectedWardId, selectCell, selectWard } =
    useDashboard();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const readyRef = useRef(false);

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
      map.addSource(WARD_SOURCE, { type: 'geojson', data: wardCollection() });

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
      addWardLabels(map);

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

      readyRef.current = true;
      map.getSource(GRID_SOURCE) && refreshGrid(map, cells, activeLayer);
    });

    return () => {
      readyRef.current = false;
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
    // The map is created once; data updates flow through the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push new model output / layer selection into the grid source.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    refreshGrid(map, cells, activeLayer);
  }, [cells, activeLayer]);

  // Highlight the selected ward.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    WARDS.forEach((ward, index) => {
      map.setFeatureState(
        { source: WARD_SOURCE, id: index },
        { selected: ward.id === selectedWardId },
      );
    });
  }, [selectedWardId]);

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

  const data = toGeoJson(cells);
  data.features.forEach((feature, index) => {
    const paint = paintCell(cells[index], layer);
    feature.properties = { ...feature.properties, ...paint };
  });
  source.setData(data);
}

/** Ward names as DOM labels — avoids shipping a glyph server for symbol layers. */
function addWardLabels(map: MapLibreMap) {
  WARDS.forEach((ward) => {
    const element = document.createElement('span');
    element.className =
      'pointer-events-none select-none text-[11px] font-medium text-slate-400 ' +
      '[text-shadow:0_1px_2px_#0b1220]';
    element.textContent = ward.name;
    new maplibregl.Marker({ element }).setLngLat(centroid(ward.boundary)).addTo(map);
  });
}

function centroid(ring: [number, number][]): [number, number] {
  // The ring is closed, so the repeated final vertex is dropped before averaging.
  const points = ring.slice(0, -1);
  const sum = points.reduce<[number, number]>(
    (acc, [lon, lat]) => [acc[0] + lon, acc[1] + lat],
    [0, 0],
  );
  return [sum[0] / points.length, sum[1] / points.length];
}

function wardCollection(): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: WARDS.map((ward, index) => ({
      type: 'Feature',
      id: index,
      geometry: { type: 'Polygon', coordinates: [ward.boundary] },
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
