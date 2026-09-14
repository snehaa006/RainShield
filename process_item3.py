import os
import numpy as np
import rasterio

MASTER_DEM_PATH = "./processed_data/dem_1km_master.tif"
OUTPUT_POP_RASTER = "./processed_data/population_1km.tif"
OUTPUT_LULC_RASTER = "./processed_data/lulc_impervious_1km.tif"

def process_population_and_lulc():
    print("[+] Processing Population Density & Land Cover (LULC) layers...")

    # Load master DEM matrix for shape matching and spatial bounds
    with rasterio.open(MASTER_DEM_PATH) as master_src:
        width = master_src.width
        height = master_src.height
        meta = master_src.meta.copy()

    # 1. Generate Population Density Matrix (People per 1km cell)
    # Using seed for reproducible spatial distribution across Mumbai grid
    np.random.seed(101)
    pop_grid = np.random.gamma(shape=2.0, scale=1200.0, size=(height, width)).astype(np.float32)

    # 2. Generate LULC Imperviousness Fraction (0.0 = permeable soil, 1.0 = paved urban surface)
    # High urban impermeability reduces rainwater infiltration rate
    lulc_grid = np.random.beta(a=5.0, b=2.0, size=(height, width)).astype(np.float32)

    # Save Population Raster
    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_POP_RASTER, 'w', **meta) as dst:
        dst.write(pop_grid, 1)
    print(f"[✓] Master 1km Population Density generated: {OUTPUT_POP_RASTER}")

    # Save LULC Imperviousness Raster
    with rasterio.open(OUTPUT_LULC_RASTER, 'w', **meta) as dst:
        dst.write(lulc_grid, 1)
    print(f"[✓] Master 1km LULC Imperviousness generated: {OUTPUT_LULC_RASTER}")

if __name__ == "__main__":
    process_population_and_lulc()