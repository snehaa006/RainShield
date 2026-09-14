import os
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
import numpy as np

MASTER_DEM_PATH = "./processed_data/dem_1km_master.tif"
REAL_POP_INPUT = "./raw_data_feeds/real_india_pop.tif"
OUTPUT_POP_RASTER = "./processed_data/population_1km.tif"

def process_real_worldpop_data():
    print(f"[+] Processing 100% REAL WorldPop 1km density raster: {REAL_POP_INPUT}")

    with rasterio.open(MASTER_DEM_PATH) as master_src:
        target_crs = master_src.crs
        target_transform = master_src.transform
        width = master_src.width
        height = master_src.height
        meta = master_src.meta.copy()

    with rasterio.open(REAL_POP_INPUT) as pop_src:
        real_pop_grid = np.zeros((height, width), dtype=np.float32)

        reproject(
            source=rasterio.band(pop_src, 1),
            destination=real_pop_grid,
            src_transform=pop_src.transform,
            src_crs=pop_src.crs,
            dst_transform=target_transform,
            dst_crs=target_crs,
            resampling=Resampling.bilinear
        )

    real_pop_grid = np.clip(real_pop_grid, 0, None)

    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_POP_RASTER, 'w', **meta) as dst:
        dst.write(real_pop_grid, 1)

    print(f"[✓] 100% Real Master 1km Population Density saved: {OUTPUT_POP_RASTER}")
    print(f"    -> Total real estimated population in master grid: {int(real_pop_grid.sum()):,} people")

if __name__ == "__main__":
    process_real_worldpop_data()