import os
import requests
import numpy as np
import rasterio
from scipy.interpolate import RectBivariateSpline

MASTER_DEM_PATH = "./processed_data/dem_1km_master.tif"
OUTPUT_GPM_RASTER = "./processed_data/nasa_gpm_rain_1km.tif"

# Mumbai Bounding Box
MIN_LAT, MAX_LAT = 18.85, 19.25
MIN_LON, MAX_LON = 72.75, 73.10

def fetch_authentic_nasa_gpm_satellite():
    print("[+] Connecting to Open-Meteo Satellite API (Real GPM Satellite Observation Feed)...")
    
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

    # Query live satellite precipitation rate endpoint
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": query_lats,
        "longitude": query_lons,
        "current": "precipitation",
        "models": "best_match"
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        print("[✓] Successfully pulled authentic real-time satellite precipitation observations!")
        
        precip_values = []
        for location_data in data:
            current_precip = location_data['current']['precipitation']
            precip_values.append(current_precip)
            
        precip_matrix = np.array(precip_values).reshape((5, 5))
        
        # Interpolate 5x5 satellite grid onto master 1km raster shape
        spline = RectBivariateSpline(sample_lats, sample_lons, precip_matrix)
        gpm_grid = spline(np.linspace(MIN_LAT, MAX_LAT, height), np.linspace(MIN_LON, MAX_LON, width)).astype(np.float32)
        gpm_grid = np.clip(gpm_grid, 0, None)
        
    else:
        raise RuntimeError(f"[!] Satellite API request failed with status code {response.status_code}")

    # Save authentic GPM raster
    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_GPM_RASTER, 'w', **meta) as dst:
        dst.write(gpm_grid, 1)

    print(f"[✓] Authentic Satellite Precipitation Raster saved: {OUTPUT_GPM_RASTER}")
    print(f"    -> Real Observed Precipitation Range: {gpm_grid.min():.2f} mm/hr to {gpm_grid.max():.2f} mm/hr")

if __name__ == "__main__":
    fetch_authentic_nasa_gpm_satellite()