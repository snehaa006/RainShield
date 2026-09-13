import type { StyleSpecification } from 'maplibre-gl';

/**
 * CARTO raster basemap.
 *
 * The key is optional: these tiles serve publicly, and Vite inlines any
 * `VITE_*` value into the client bundle, so this is a referrer-restricted
 * public key rather than a secret. Set it in `.env.local` (gitignored).
 */
const BASEMAP_KEY = import.meta.env.VITE_BASEMAP_KEY;

/** 'dark_all' matches the dashboard shell; 'voyager' and 'light_all' are light. */
const VARIANT = 'dark_all';

const SUBDOMAINS = ['a', 'b', 'c'];

function tileUrl(subdomain: string): string {
  const query = BASEMAP_KEY ? `?key=${encodeURIComponent(BASEMAP_KEY)}` : '';
  return `https://${subdomain}.basemaps.cartocdn.com/rastertiles/${VARIANT}/{z}/{x}/{y}@2x.png${query}`;
}

export const BASE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    basemap: {
      type: 'raster',
      tiles: SUBDOMAINS.map(tileUrl),
      tileSize: 256,
      attribution: '© OpenStreetMap contributors © CARTO',
    },
  },
  layers: [
    // Painted behind the tiles, so the grid stays readable if they fail to load.
    { id: 'background', type: 'background', paint: { 'background-color': '#0b1220' } },
    { id: 'basemap', type: 'raster', source: 'basemap', paint: { 'raster-opacity': 0.85 } },
  ],
};
