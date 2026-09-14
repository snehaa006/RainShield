import os
import requests
import numpy as np
import geopandas as gpd
from shapely.geometry import shape
import rasterio

# Mumbai Bounding Box: [min_lat, min_lon, max_lat, max_lon]
BBOX = [18.85, 72.75, 19.25, 73.10]
MASTER_DEM_PATH = "./processed_data/dem_1km_master.tif"
OUTPUT_INFRA_RASTER = "./processed_data/infra_density_1km.tif"

def fetch_osm_infrastructure():
    print("[+] Fetching Infrastructure from OpenStreetMap via Overpass API...")
    overpass_url = "http://overpass-api.de/api/interpreter"
    
    # Overpass QL Query for critical infrastructure
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
    
    response = requests.post(overpass_url, data={'data': query})
    if response.status_code == 200:
        data = response.json()
        print(f"    -> Retreived {len(data['elements'])} spatial infrastructure elements.")
        return data
    else:
        raise RuntimeError(f"Overpass API error: {response.status_code}")

def map_infra_to_1km_grid(osm_data):
    print("[+] Mapping infrastructure elements onto 1km Master Grid...")
    
    # Extract geometries from OSM JSON elements
    geometries = []
    for elem in osm_data.get('elements', []):
        if 'lat' in elem and 'lon' in elem:
            geometries.append({'type': 'Point', 'coordinates': [elem['lon'], elem['lat']]})

    # Load master DEM to align spatial resolution and bounding transform
    with rasterio.open(MASTER_DEM_PATH) as master_src:
        transform = master_src.transform
        width = master_src.width
        height = master_src.height
        meta = master_src.meta.copy()

    # Create 2D array matrix for Infrastructure Density
    infra_grid = np.zeros((height, width), dtype=np.float32)

    # Calculate infrastructure feature counts per 1km grid cell
    for geom in geometries:
        lon, lat = geom['coordinates']
        # Convert Lon/Lat coordinates to grid cell matrix indices (row, col)
        col, row = ~transform * (lon, lat)
        col, row = int(col), int(row)
        
        if 0 <= row < height and 0 <= col < width:
            infra_grid[row, col] += 1.0  # Increment cell count

    meta.update({'dtype': 'float32', 'count': 1})
    with rasterio.open(OUTPUT_INFRA_RASTER, 'w', **meta) as dst:
        dst.write(infra_grid, 1)

    print(f"[✓] Master 1km Infrastructure Raster generated: {OUTPUT_INFRA_RASTER}")

if __name__ == "__main__":
    raw_osm = fetch_osm_infrastructure()
    map_infra_to_1km_grid(raw_osm)