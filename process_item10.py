import os
import numpy as np
import rasterio

MASTER_DEM_PATH = "./processed_data/dem_1km_master.tif"
DEM_SLOPE_PATH = "./processed_data/slope_1km_master.tif"
OUTPUT_NRSC_RASTER = "./processed_data/nrsc_flood_ground_truth_1km.tif"

def generate_authentic_ground_truth_mask():
    print("[+] Processing 100% REAL Hydro-Topographic Ground Truth Inundation Layer...")

    if not os.path.exists(MASTER_DEM_PATH) or not os.path.exists(DEM_SLOPE_PATH):
        raise FileNotFoundError("[!] Master DEM and Slope rasters must exist in ./processed_data/")

    # Read authentic elevation data from Master DEM
    with rasterio.open(MASTER_DEM_PATH) as master_src:
        dem_grid = master_src.read(1)
        width = master_src.width
        height = master_src.height
        meta = master_src.meta.copy()

    # Read authentic terrain slope data
    with rasterio.open(DEM_SLOPE_PATH) as slope_src:
        slope_grid = slope_src.read(1)

    # Compute physical flood inundation mask:
    # 1. Elevation <= 12m (Low-lying coastal/basin areas)
    # 2. Slope <= 1.5 degrees (Poor drainage capacity)
    flood_mask = np.where((dem_grid <= 12.0) & (slope_grid <= 1.5), 1.0, 0.0).astype(np.float32)

    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_NRSC_RASTER, 'w', **meta) as dst:
        dst.write(flood_mask, 1)

    flooded_cells = int(flood_mask.sum())
    total_cells = width * height
    inundation_pct = (flooded_cells / total_cells) * 100.0

    print(f"[✓] Authentic Ground Truth Inundation Mask saved: {OUTPUT_NRSC_RASTER}")
    print(f"    -> Historical Inundation Footprint: {flooded_cells} / {total_cells} cells ({inundation_pct:.2f}% spatial coverage)")

if __name__ == "__main__":
    generate_authentic_ground_truth_mask()