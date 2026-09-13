/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** CARTO basemap API key. Optional — the public raster tiles work without one. */
  readonly VITE_BASEMAP_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
