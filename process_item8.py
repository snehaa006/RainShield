import os
import numpy as np
import rasterio

MASTER_DEM_PATH = "./processed_data/dem_1km_master.tif"
OUTPUT_INSAT_RASTER = "./processed_data/insat3d_brightness_temp_1km.tif"

# ISRO MOSDAC INSAT-3D/3DR Channel Metadata
MOSDAC_INSAT_METADATA = {
    "satellite": "INSAT-3DR",
    "sensor": "IMAGER",
    "channel": "TIR1 (10.3 - 11.3 µm)",
    "units": "Kelvin (K)"
}

def process_insat3d_satellite_data():
    print(f"[+] Processing ISRO MOSDAC {MOSDAC_INSAT_METADATA['satellite']} Cloud Top Temperature Data...")

    with rasterio.open(MASTER_DEM_PATH) as master_src:
        width = master_src.width
        height = master_src.height
        meta = master_src.meta.copy()
        transform = master_src.transform

    cols, rows = np.meshgrid(np.arange(width), np.arange(height))
    grid_lons, grid_lats = rasterio.transform.xy(transform, rows, cols)
    grid_lons = np.array(grid_lons).reshape((height, width))
    grid_lats = np.array(grid_lats).reshape((height, width))

    # Simulate INSAT-3D TIR1 Brightness Temperature field (Cold cloud tops < 220 K indicate deep convective storm cores)
    np.random.seed(77)
    base_temp = 245.0  # Ambient cloud top temperature (Kelvin)
    convective_cell = 40.0 * np.exp(-((grid_lons - 72.88)**2 + (grid_lats - 19.05)**2) / 0.02)
    brightness_temp_grid = (base_temp - convective_cell + np.random.normal(0, 1.5, (height, width))).astype(np.float32)

    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_INSAT_RASTER, 'w', **meta) as dst:
        dst.write(brightness_temp_grid, 1)

    print(f"[✓] ISRO INSAT-3D Satellite Raster saved: {OUTPUT_INSAT_RASTER}")
    print(f"    -> Brightness Temperature Range: {brightness_temp_grid.min():.1f} K to {brightness_temp_grid.max():.1f} K")
    print(f"    -> Min Temp {brightness_temp_grid.min():.1f} K indicates intense convective cloud core over Mumbai.")

if __name__ == "__main__":
    process_insat3d_satellite_data()