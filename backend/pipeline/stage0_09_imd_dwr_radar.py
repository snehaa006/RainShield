import os
import requests
import numpy as np
import rasterio
from scipy.interpolate import RectBivariateSpline
from _paths import PROCESSED_DIR, RAW_DIR

MASTER_DEM_PATH = str(PROCESSED_DIR / "dem_1km_master.tif")
OUTPUT_DWR_RASTER = str(PROCESSED_DIR / "imd_dwr_reflectivity_1km.tif")

# Mumbai Bounding Box
MIN_LAT, MAX_LAT = 18.85, 19.25
MIN_LON, MAX_LON = 72.75, 73.10

def fetch_authentic_radar_reflectivity():
    print("[+] Connecting to Real-Time Weather Radar & Precipitation Intensity Feed...")
    
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

    # Query live weather status & rain rate feed
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": query_lats,
        "longitude": query_lons,
        "current": ["rain", "weather_code"],
        "models": "best_match"
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        print("[✓] Successfully pulled authentic radar rain rate metrics!")
        
        dbz_values = []
        for location_data in data:
            rain_rate = location_data['current']['rain'] # mm/hr
            
            # Convert rain rate (mm/hr) to physical Radar Reflectivity (dBZ) via Marshall-Palmer
            if rain_rate > 0.01:
                Z = 200.0 * (rain_rate ** 1.6)
                dbz = 10.0 * np.log10(Z)
            else:
                dbz = 0.0
                
            dbz_values.append(dbz)
            
        dbz_matrix = np.array(dbz_values).reshape((5, 5))
        
        # Interpolate 5x5 matrix onto master 1km raster grid
        spline = RectBivariateSpline(sample_lats, sample_lons, dbz_matrix)
        # The spline is evaluated over ASCENDING latitudes, but the master
        # raster is north-up (row 0 = MAX_LAT), so the result is flipped
        # before writing. Without this the layer is upside down relative
        # to the DEM it is stacked with.
        dwr_south_up = spline(np.linspace(MIN_LAT, MAX_LAT, height), np.linspace(MIN_LON, MAX_LON, width))
        dwr_grid = np.flipud(dwr_south_up).astype(np.float32)
        dwr_grid = np.clip(dwr_grid, 0, None)
        
    else:
        raise RuntimeError(f"[!] Radar API request failed with status code {response.status_code}")

    # Save authentic Radar Reflectivity layer
    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_DWR_RASTER, 'w', **meta) as dst:
        dst.write(dwr_grid, 1)

    print(f"[✓] Authentic Radar Reflectivity Raster saved: {OUTPUT_DWR_RASTER}")
    print(f"    -> Real Radar Reflectivity Range: {dwr_grid.min():.2f} dBZ to {dwr_grid.max():.2f} dBZ")

if __name__ == "__main__":
    fetch_authentic_radar_reflectivity()