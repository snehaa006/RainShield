import os
import geopandas as gpd
import numpy as np
import rasterio
from _paths import PROCESSED_DIR, RAW_DIR

MASTER_DEM_PATH = str(PROCESSED_DIR / "dem_1km_master.tif")
GEOJSON_PATH = str(RAW_DIR / "real_mumbai_osm.geojson")
OUTPUT_INFRA_RASTER = str(PROCESSED_DIR / "infra_density_1km.tif")

def process_downloaded_osm_geojson():
    print(f"[+] Reading 100% REAL OpenStreetMap file: {GEOJSON_PATH}")
    
    if not os.path.exists(GEOJSON_PATH):
        raise FileNotFoundError(f"[!] Please download real_mumbai_osm.geojson from Overpass Turbo and place it in ./raw_data_feeds/")

    # Read authentic downloaded GeoJSON vector dataset
    gdf = gpd.read_file(GEOJSON_PATH)
    print(f"    -> Successfully loaded {len(gdf)} real physical infrastructure features!")

    with rasterio.open(MASTER_DEM_PATH) as master_src:
        transform = master_src.transform
        width = master_src.width
        height = master_src.height
        meta = master_src.meta.copy()

    infra_grid = np.zeros((height, width), dtype=np.float32)

    # Compute centroids for real roads, hospitals, schools, and bridges
    for geom in gdf.geometry:
        if geom is not None:
            centroid = geom.centroid
            lon, lat = centroid.x, centroid.y
            
            # Map physical Lon/Lat to raster row/column matrix indices
            col, row = ~transform * (lon, lat)
            col, row = int(col), int(row)
            
            if 0 <= row < height and 0 <= col < width:
                infra_grid[row, col] += 1.0

    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_INFRA_RASTER, 'w', **meta) as dst:
        dst.write(infra_grid, 1)

    print(f"[✓] 100% Real Infrastructure Master Raster generated: {OUTPUT_INFRA_RASTER}")
    print(f"    -> Total real features rasterized across grid: {int(infra_grid.sum())}")

if __name__ == "__main__":
    process_downloaded_osm_geojson()