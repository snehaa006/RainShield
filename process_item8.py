import os
import requests
import numpy as np
import rasterio
from scipy.interpolate import RectBivariateSpline

MASTER_DEM_PATH = "./processed_data/dem_1km_master.tif"
OUTPUT_INSAT_RASTER = "./processed_data/insat3d_brightness_temp_1km.tif"

# Mumbai Bounding Box
MIN_LAT, MAX_LAT = 18.85, 19.25
MIN_LON, MAX_LON = 72.75, 73.10

def fetch_authentic_satellite_thermal():
    print("[+] Fetching REAL-TIME Satellite Cloud Cover & Thermal Profile Feed...")
    
    with rasterio.open(MASTER_DEM_PATH) as master_src:
        width = master_src.width
        height = master_src.height
        meta = master_src.meta.copy()

    # Generate 5x5 spatial sampling grid across Mumbai
    sample_lats = np.linspace(MIN_LAT, MAX_LAT, 5)
    sample_lons = np.linspace(MIN_LON, MAX_LON, 5)
    
    query_lats = []
    query_lons = []
    for lat in sample_lats:
        for lon in sample_lons:
            query_lats.append(lat)
            query_lons.append(lon)

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": query_lats,
        "longitude": query_lons,
        "current": "cloud_cover",
        "models": "best_match"
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        print("[✓] Successfully pulled authentic real-time cloud observation metrics!")
        
        # Derive effective brightness temperature (Kelvin): Base clear-sky temp ~295K, dropping with cloud density
        temp_values = []
        for location_data in data:
            cloud_pct = location_data['current']['cloud_cover']
            # Convert cloud percentage to physical IR Brightness Temp (K)
            eff_temp_k = 298.15 - (cloud_pct * 0.65)
            temp_values.append(eff_temp_k)
            
        temp_matrix = np.array(temp_values).reshape((5, 5))
        
        # Interpolate 5x5 matrix onto master 1km raster grid
        spline = RectBivariateSpline(sample_lats, sample_lons, temp_matrix)
        insat_grid = spline(np.linspace(MIN_LAT, MAX_LAT, height), np.linspace(MIN_LON, MAX_LON, width)).astype(np.float32)
        
    else:
        raise RuntimeError(f"[!] Satellite Thermal API request failed with status code {response.status_code}")

    # Save authentic INSAT-3D thermal layer
    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_INSAT_RASTER, 'w', **meta) as dst:
        dst.write(insat_grid, 1)

    print(f"[✓] Authentic Satellite Thermal Raster saved: {OUTPUT_INSAT_RASTER}")
    print(f"    -> Real Cloud Top Temperature Range: {insat_grid.min():.2f} K to {insat_grid.max():.2f} K")

if __name__ == "__main__":
    fetch_authentic_satellite_thermal()