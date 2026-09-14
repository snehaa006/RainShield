import os
import numpy as np
import rasterio

MASTER_DEM_PATH = "./processed_data/dem_1km_master.tif"
OUTPUT_CWC_RASTER = "./processed_data/cwc_river_hydrology_1km.tif"

# CWC & Municipal Gauge Monitoring Stations across Mumbai Rivers
CWC_GAUGE_STATIONS = [
    {"river": "Mithi River (Kurla)", "lat": 19.0650, "lon": 72.8790, "water_level_m": 4.2, "danger_level_m": 4.0},
    {"river": "Mithi River (Vihar Spillway)", "lat": 19.1300, "lon": 72.9050, "water_level_m": 3.8, "danger_level_m": 4.5},
    {"river": "Ulhas River (Kalyan)", "lat": 19.2433, "lon": 73.1350, "water_level_m": 11.5, "danger_level_m": 12.0},
    {"river": "Dahisar River (Bridge)", "lat": 19.2500, "lon": 72.8580, "water_level_m": 2.9, "danger_level_m": 3.2}
]

def process_river_hydrology():
    print("[+] Processing CWC & Local River Hydrology Gauge Streams...")

    with rasterio.open(MASTER_DEM_PATH) as master_src:
        width = master_src.width
        height = master_src.height
        meta = master_src.meta.copy()
        transform = master_src.transform

    # Create coordinate grids
    cols, rows = np.meshgrid(np.arange(width), np.arange(height))
    grid_lons, grid_lats = rasterio.transform.xy(transform, rows, cols)
    grid_lons = np.array(grid_lons)
    grid_lats = np.array(grid_lats)

    hydrology_risk_grid = np.zeros((height, width), dtype=np.float32)

    # Compute exponential decay risk buffer around river gauges based on danger ratio
    for station in CWC_GAUGE_STATIONS:
        st_lon, st_lat = station['lon'], station['lat']
        # Calculate water ratio relative to danger mark
        water_ratio = station['water_level_m'] / station['danger_level_m']
        
        # Euclidean spatial distance grid in degrees (~111km per deg)
        dist_deg = np.sqrt((grid_lons - st_lon)**2 + (grid_lats - st_lat)**2)
        dist_km = dist_deg * 111.0
        
        # Hydrological risk influence decays with distance from river channel
        influence = water_ratio * np.exp(-dist_km / 3.0)
        hydrology_risk_grid = np.maximum(hydrology_risk_grid, influence)

    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_CWC_RASTER, 'w', **meta) as dst:
        dst.write(hydrology_risk_grid.astype(np.float32), 1)

    print(f"[✓] Master 1km River Hydrology Raster generated: {OUTPUT_CWC_RASTER}")
    print(f"    -> Max River Overflow Risk Index: {hydrology_risk_grid.max():.2f} (Values > 1.0 indicate river bank breach)")

if __name__ == "__main__":
    process_river_hydrology()