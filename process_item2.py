import os
import requests
import numpy as np
import rasterio

# Mumbai Bounding Box: [min_lat, min_lon, max_lat, max_lon]
BBOX = [18.85, 72.75, 19.25, 73.10]
MASTER_DEM_PATH = "./processed_data/dem_1km_master.tif"
OUTPUT_INFRA_RASTER = "./processed_data/infra_density_1km.tif"

def fetch_osm_infrastructure():
    print("[+] Fetching Infrastructure from OpenStreetMap via Overpass API...")
    
    # Primary and Backup Overpass Endpoints
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    
    query = f"""
    [out:json][timeout:60];
    (
      node["amenity"="hospital"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
      node["amenity"="school"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
      way["highway"="primary"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
      way["highway"="trunk"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
      way["bridge"="yes"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
    );
    out body;
    >;
    out skel qt;
    """
    
    headers = {
        'User-Agent': 'RainShieldAI_SIH2026/1.0 (contact: hydro_nex_sih@example.com)'
    }

    for url in endpoints:
        try:
            response = requests.post(url, data={'data': query}, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                print(f"    -> Retreived {len(data['elements'])} spatial infrastructure elements.")
                return data
            else:
                print(f"    [!] Endpoint {url} returned status code {response.status_code}. Trying backup...")
        except Exception as e:
            print(f"    [!] Connection error for {url}: {e}. Trying backup...")

    raise RuntimeError("All Overpass API endpoints failed. Check connection or retry.")

def map_infra_to_1km_grid(osm_data):
    print("[+] Mapping infrastructure elements onto 1km Master Grid...")
    
    geometries = []
    for elem in osm_data.get('elements', []):
        if 'lat' in elem and 'lon' in elem:
            geometries.append({'type': 'Point', 'coordinates': [elem['lon'], elem['lat']]})

    with rasterio.open(MASTER_DEM_PATH) as master_src:
        transform = master_src.transform
        width = master_src.width
        height = master_src.height
        meta = master_src.meta.copy()

    infra_grid = np.zeros((height, width), dtype=np.float32)

    for geom in geometries:
        lon, lat = geom['coordinates']
        col, row = ~transform * (lon, lat)
        col, row = int(col), int(row)
        
        if 0 <= row < height and 0 <= col < width:
            infra_grid[row, col] += 1.0

    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_INFRA_RASTER, 'w', **meta) as dst:
        dst.write(infra_grid, 1)

    print(f"[✓] Master 1km Infrastructure Raster generated: {OUTPUT_INFRA_RASTER}")

if __name__ == "__main__":
    raw_osm = fetch_osm_infrastructure()
    map_infra_to_1km_grid(raw_osm)