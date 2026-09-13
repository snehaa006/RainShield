import type { StyleSpecification } from 'maplibre-gl';

/**
 * CARTO raster basemap.
 *
 * CARTO has required an API key on these tiles since Aug 2026 — without one
 * they are served with an "API KEY REQUIRED" watermark. Keys are free up to
 * 5M tile requests/month: https://carto.com/basemaps/apikey
 *
 * Vite inlines any `VITE_*` value into the client bundle, so this is a
 * referrer-restricted public key, not a secret. Set it in `.env.local`.
 */
const BASEMAP_KEY = import.meta.env.VITE_BASEMAP_KEY;

/**
 * Style path. Note the paths are not uniform: the voyager styles are nested
 * under `rastertiles/`, while the light and dark ones sit at the root.
 *
 * Valid values: 'dark_all', 'dark_nolabels', 'light_all', 'light_nolabels',
 * 'rastertiles/voyager', 'rastertiles/voyager_nolabels'.
 */
const STYLE = 'dark_all';

const SUBDOMAINS = ['a', 'b', 'c', 'd'];

function tileUrl(subdomain: string): string {
  const query = BASEMAP_KEY ? `?key=${encodeURIComponent(BASEMAP_KEY)}` : '';
  return `https://${subdomain}.basemaps.cartocdn.com/${STYLE}/{z}/{x}/{y}@2x.png${query}`;
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
