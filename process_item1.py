import os
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

INPUT_DEM = "./raw_data_feeds/dem_30m.tif"
OUTPUT_1KM_DEM = "./processed_data/dem_1km_master.tif"
OUTPUT_1KM_SLOPE = "./processed_data/slope_1km_master.tif"

os.makedirs("./processed_data", exist_ok=True)

def process_elevation_and_slope(input_path, dem_out_path, slope_out_path):
    target_crs = "EPSG:4326"
    target_res = 0.008983  # ~1 km grid cell in EPSG:4326

    # 1. Reproject DEM and resample to 1km master grid
    with rasterio.open(input_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, target_crs, src.width, src.height, *src.bounds,
            resolution=(target_res, target_res)
        )
        
        kwargs = src.meta.copy()
        kwargs.update({
            'crs': target_crs,
            'transform': transform,
            'width': width,
            'height': height,
            'dtype': 'float32'
        })

        dem_data = np.zeros((height, width), dtype=np.float32)

        with rasterio.open(dem_out_path, 'w', **kwargs) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=dem_data,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=target_crs,
                resampling=Resampling.bilinear
            )
            dst.write(dem_data, 1)

    print(f"[✓] Master 1km DEM generated: {dem_out_path} | Grid Shape: {dem_data.shape}")

    # 2. Compute Physical Slope (%)
    dy, dx = np.gradient(dem_data)
    cell_size_m = 1000.0  # ~1km spatial grid cell size
    slope = np.sqrt((dx / cell_size_m)**2 + (dy / cell_size_m)**2) * 100.0

    with rasterio.open(slope_out_path, 'w', **kwargs) as dst:
        dst.write(slope.astype(np.float32), 1)

    print(f"[✓] Master 1km Slope generated: {slope_out_path}")

if __name__ == "__main__":
    process_elevation_and_slope(INPUT_DEM, OUTPUT_1KM_DEM, OUTPUT_1KM_SLOPE)