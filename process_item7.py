import os
import requests
import numpy as np
import rasterio
from scipy.interpolate import RectBivariateSpline

MASTER_DEM_PATH = "./processed_data/dem_1km_master.tif"
OUTPUT_GFS_RASTER = "./processed_data/nwp_gfs_forecast_1km.tif"

# Mumbai Bounding Box
MIN_LAT, MAX_LAT = 18.85, 19.25
MIN_LON, MAX_LON = 72.75, 73.10

def fetch_authentic_noaa_gfs():
    print("[+] Connecting to Open-Meteo API (NOAA GFS Seamless Forecast Feed)...")
    
    with rasterio.open(MASTER_DEM_PATH) as master_src:
        width = master_src.width
        height = master_src.height
        meta = master_src.meta.copy()

    # Generate 5x5 spatial sampling grid across Mumbai (25 total coordinate pairs)
    sample_lats = np.linspace(MIN_LAT, MAX_LAT, 5)
    sample_lons = np.linspace(MIN_LON, MAX_LON, 5)
    
    query_lats = []
    query_lons = []
    for lat in sample_lats:
        for lon in sample_lons:
            query_lats.append(lat)
            query_lons.append(lon)

    # Query live NOAA GFS model endpoint for all 25 grid locations
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": query_lats,
        "longitude": query_lons,
        "hourly": "precipitation",
        "models": "gfs_seamless",
        "forecast_days": 1
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        print("[✓] Successfully pulled authentic live NOAA GFS forecast data!")
        
        # Extract 3-hour accumulated precipitation forecast array (mm)
        precip_values = []
        for location_data in data:
            hourly_precip = location_data['hourly']['precipitation'][:3]
            accumulated_3h = sum(hourly_precip)
            precip_values.append(accumulated_3h)
            
        # Reshape 25 extracted values into a 5x5 spatial matrix
        precip_matrix = np.array(precip_values).reshape((5, 5))
        
        # Interpolate 5x5 live NOAA GFS grid onto master 1km raster shape
        spline = RectBivariateSpline(sample_lats, sample_lons, precip_matrix)
        gfs_grid = spline(np.linspace(MIN_LAT, MAX_LAT, height), np.linspace(MIN_LON, MAX_LON, width)).astype(np.float32)
        gfs_grid = np.clip(gfs_grid, 0, None)
        
    else:
        raise RuntimeError(f"[!] NOAA GFS API request failed with status code {response.status_code}")

    # Save authentic GFS raster
    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_GFS_RASTER, 'w', **meta) as dst:
        dst.write(gfs_grid, 1)

    print(f"[✓] Authentic NOAA GFS Raster saved: {OUTPUT_GFS_RASTER}")
    print(f"    -> Real Forecasted 3-Hour Precipitation Range: {gfs_grid.min():.2f} mm to {gfs_grid.max():.2f} mm")

if __name__ == "__main__":
    fetch_authentic_noaa_gfs()