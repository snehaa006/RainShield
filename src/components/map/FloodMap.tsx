import { useEffect, useRef, useState } from 'react';
import maplibregl, { type Map as MapLibreMap } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { cellPolygon } from '@/lib/grid';
import { infrastructureFor, INFRA_ICONS, INFRA_LABELS } from '@/lib/infrastructure';
import { useDashboard } from '@/hooks/useDashboard';
import { BASE_STYLE } from '@/components/map/mapStyle';
import { paintCell } from '@/components/map/layerPaint';
import type { Ward } from '@/types';

const GRID_SOURCE = 'grid';
const WARD_SOURCE = 'wards';

export function FloodMap() {
  const {
    cells,
    wards,
    region,
    activeLayer,
    showInfrastructure,
    stations,
    selectedWardId,
    selectCell,
    selectWard,
  } = useDashboard();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const labelsRef = useRef<maplibregl.Marker[]>([]);
  // True once the user has driven the camera themselves, after which a resize
  // must not reset their view.
  const userMovedRef = useRef(false);
  // `ready` is state rather than a ref because the data effects below have to
  // re-run once the style finishes loading: cells and wards now arrive from the
  // API and routinely beat the map to it.
  const [ready, setReady] = useState(false);

  // Latest handlers, so the map's event listeners are only bound once.
  const handlers = useRef({ selectCell, selectWard });
  handlers.current = { selectCell, selectWard };

  // The map cannot be created until the region is known — its centre, extent
  // and pan limits all come from it, and they differ per region.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !region) return undefined;

    const map = new maplibregl.Map({
      container,
      style: BASE_STYLE,
      center: region.centre,
      zoom: 10.4,
      maxBounds: expand(region.bounds, 0.6),
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');

    /**
     * Fit the region to whatever size the panel actually is.
     *
     * MapLibre measures its container when it is constructed. In a flex/grid
     * board that size is not final yet — often it is zero — so fitting straight
     * away computed a camera for a viewport that never existed, and the grid
     * ended up small and jammed against one edge of a much wider canvas. It
     * never recovered, because nothing told the map the container had grown.
     */
    const fit = () => {
      const { clientWidth, clientHeight } = container;
      if (clientWidth < 1 || clientHeight < 1) return;
      // Drop the floor from the previous fit first. Keeping it meant a panel
      // that got *smaller* could not zoom out far enough to show the whole
      // region again, and silently cropped its north and south edges instead.
      map.setMinZoom(0);
      map.resize();
      map.fitBounds(region.bounds, { padding: 24, duration: 0 });
      // The fitted view is now the zoomed-out limit, so panning cannot wander
      // off the region and the zoom control has a sensible bottom stop.
      map.setMinZoom(map.getZoom() - 0.4);
    };

    // Re-fit while the user has not taken control of the camera; once they pan
    // or zoom themselves, a resize should keep their view, not yank it back.
    const observer = new ResizeObserver(() => {
      if (userMovedRef.current) map.resize();
      else fit();
    });
    observer.observe(container);

    const markUserMoved = (event: { originalEvent?: unknown }) => {
      if (event.originalEvent) userMovedRef.current = true;
    };
    map.on('dragstart', markUserMoved);
    map.on('zoomstart', markUserMoved);
    map.on('rotatestart', markUserMoved);

    userMovedRef.current = false;
    fit();

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
      observer.disconnect();
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      labelsRef.current.forEach((marker) => marker.remove());
      labelsRef.current = [];
      map.remove();
      mapRef.current = null;
    };
    // Rebuilt only when the region changes — a different region means a
    // different centre, extent and pan limit, which the constructor fixes at
    // creation. Ordinary data updates flow through the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [region?.id]);

  // Push new model output / layer selection into the grid source.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !region) return;
    refreshGrid(map, cells, activeLayer, region);
  }, [ready, cells, activeLayer, region]);

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

    markersRef.current = infrastructureFor(region, stations).map((asset) => {
      const element = document.createElement('div');
      element.className =
        'flex h-5 w-5 items-center justify-center rounded-full border border-slate-300/70 ' +
        'bg-slate-900/85 text-[10px] text-slate-200 shadow';
      element.textContent = INFRA_ICONS[asset.type];
      element.title = `${asset.name} — ${INFRA_LABELS[asset.type]}`;
      return new maplibregl.Marker({ element }).setLngLat([asset.lon, asset.lat]).addTo(map);
    });
  }, [showInfrastructure, region, stations, ready]);

  return <div ref={containerRef} className="h-full w-full" />;
}

function refreshGrid(
  map: MapLibreMap,
  cells: ReturnType<typeof useDashboard>['cells'],
  layer: ReturnType<typeof useDashboard>['activeLayer'],
  region: NonNullable<ReturnType<typeof useDashboard>['region']>,
) {
  const source = map.getSource(GRID_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;

  source.setData({
    type: 'FeatureCollection',
    features: cells.map((cell, index) => ({
      type: 'Feature',
      id: index,
      geometry: { type: 'Polygon', coordinates: [cellPolygon(cell.row, cell.col, region)] },
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

/**
 * Pan limits around a region, as a fraction of its own span.
 *
 * This used to add a flat 0.35 degrees — about 39 km — on every side of every
 * region regardless of how big the region was. Scaling with the region keeps
 * the limit proportionate, and keeps maxBounds from over-constraining the
 * minimum zoom on a wide panel.
 */
function expand(
  [west, south, east, north]: [number, number, number, number],
  fraction: number,
): [number, number, number, number] {
  const padX = (east - west) * fraction;
  const padY = (north - south) * fraction;
  return [west - padX, south - padY, east + padX, north + padY];
}
