import os
import numpy as np
import rasterio
from sklearn.preprocessing import MinMaxScaler

PROCESSED_DIR = "./processed_data"
OUTPUT_TENSOR_PATH = "./processed_data/rainshield_stage1_tensor.npz"

FEATURE_FILES = [
    "dem_1km_master.tif",             # Feature 0: Elevation (m)
    "slope_1km_master.tif",           # Feature 1: Terrain Slope (deg)
    "infrastructure_1km.tif",        # Feature 2: Building/Road Count
    "population_1km.tif",            # Feature 3: Population Density
    "imd_aws_rain_1km.tif",           # Feature 4: IMD AWS Rain (mm/hr)
    "cwc_river_hydrology_1km.tif",   # Feature 5: River Overflow Index
    "nasa_gpm_rain_1km.tif",          # Feature 6: NASA GPM Rain (mm/hr)
    "nwp_gfs_forecast_1km.tif",       # Feature 7: NOAA GFS Forecast (mm)
    "insat3d_brightness_temp_1km.tif",# Feature 8: Cloud Temp (K)
    "imd_dwr_reflectivity_1km.tif"    # Feature 9: Radar Reflectivity (dBZ)
]

TARGET_FILE = "nrsc_flood_ground_truth_1km.tif" # Ground Truth Target (0 or 1)

def execute_stage1_aggregation():
    print("[+] Step 1: Reading and stacking raw 2D rasters into 3D Data Cube...")
    
    feature_layers = []
    for file_name in FEATURE_FILES:
        path = os.path.join(PROCESSED_DIR, file_name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"[!] Missing raster layer: {path}")
        
        with rasterio.open(path) as src:
            data = src.read(1)
            feature_layers.append(data)

    # Stack features into 3D Spatial Tensor: Shape (10 channels, 45 rows, 39 cols)
    X_tensor = np.stack(feature_layers, axis=0).astype(np.float32)
    
    # Read Target Ground Truth Mask: Shape (45 rows, 39 cols)
    target_path = os.path.join(PROCESSED_DIR, TARGET_FILE)
    with rasterio.open(target_path) as src:
        Y_tensor = src.read(1).astype(np.float32)

    num_channels, height, width = X_tensor.shape
    total_pixels = height * width
    print(f"[✓] 3D Data Cube stacked: {X_tensor.shape} ({total_pixels} total spatial cells)")

    print("[+] Step 2: Unrolling 3D grid into 2D tabular matrix & scaling features...")
    
    # Reshape (10, 45, 39) -> Transpose to (45, 39, 10) -> Flatten to (1755, 10)
    X_raw_flat = X_tensor.transpose(1, 2, 0).reshape(total_pixels, num_channels)
    Y_flat = Y_tensor.reshape(total_pixels)

    # Apply MinMaxScaler [0.0, 1.0] across all 10 features independently
    scaler = MinMaxScaler(feature_range=(0.0, 1.0))
    X_scaled_flat = scaler.fit_transform(X_raw_flat)

    print(f"[✓] Tabular Feature Matrix created: Shape {X_scaled_flat.shape}")
    print(f"[✓] Target Label Vector created: Shape {Y_flat.shape}")

    print("[+] Step 3: Serializing data cube & scaled matrices to binary storage...")
    
    np.savez_compressed(
        OUTPUT_TENSOR_PATH,
        X_tensor=X_tensor,           # Raw 3D spatial tensor (10, 45, 39)
        Y_tensor=Y_tensor,           # Raw 2D target mask (45, 39)
        X_matrix=X_scaled_flat,      # Scaled 2D tabular matrix (1755, 10)
        Y_target=Y_flat,             # Flattened target vector (1755,)
        feature_names=np.array(FEATURE_FILES)
    )

    print(f"[✓] Stage 1 Compilation Complete! Saved to: {OUTPUT_TENSOR_PATH}")
    print(f"    -> Ready for Stage 2 Machine Learning ingestion.")

if __name__ == "__main__":
    execute_stage1_aggregation()