import os
import zipfile
import json
import urllib.request
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import geopandas as gpd

# ------------------------------------------------------------------------------
# 1. DOMAIN BOUNDS (Ohio Region)
# ------------------------------------------------------------------------------
WEST, SOUTH, EAST, NORTH = -85.0, 38.0, -80.0, 42.0

# ------------------------------------------------------------------------------
# 2. EXACT COLOR PALETTE & THRESHOLD BREAKS (Inches)
# ------------------------------------------------------------------------------
bounds = [0.0, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00, 2.50, 3.00, 4.00, 5.00, 10.0]

colors_rgb = [
    (125/255,   1/255,  18/255),  # < 0.25"
    (154/255,  42/255,  77/255),  # 0.25" - 0.50"
    (179/255,  74/255, 120/255),  # 0.50" - 0.75"
    (179/255,  74/255, 120/255),  # 0.75" - 1.00"
    (199/255, 106/255, 158/255),  # 1.00" - 1.50"
    (214/255, 138/255, 190/255),  # 1.50" - 2.00"
    (225/255, 168/255, 217/255),  # 2.00" - 2.50"
    (225/255, 168/255, 217/255),  # 2.50" - 3.00"
    (233/255, 196/255, 238/255),  # 3.00" - 4.00"
    (239/255, 221/255, 250/255),  # 4.00" - 5.00"
    (242/255, 240/255, 246/255)   # >= 5.00"
]

cmap = ListedColormap(colors_rgb)
norm = BoundaryNorm(bounds, cmap.N)

def fetch_ffg_geojson(layer_id=0):
    """Fetches pure numerical vector features directly from NOAA's public REST API."""
    base_url = f"https://mapservices.weather.noaa.gov/vector/rest/services/precip/rfc_gridded_ffg/MapServer/{layer_id}/query"
    params = [
        f"geometry={WEST},{SOUTH},{EAST},{NORTH}",
        "geometryType=esriGeometryEnvelope",
        "inSR=4326",
        "spatialRel=esriSpatialRelIntersects",
        "outFields=*",
        "returnGeometry=true",
        "outSR=4326",
        "f=geojson"
    ]
    query_url = f"{base_url}?" + "&".join(params)

    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(query_url, headers=headers)
    
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode('utf-8'))
        
    return gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")

def generate_kmz(layer_id=0, duration_hr="01", output_kmz="Custom_FFG_1hr.kmz"):
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    # 1. Fetch raw vector features containing numerical values
    gdf = fetch_ffg_geojson(layer_id=layer_id)

    if gdf.empty:
        raise RuntimeError("NOAA API returned no vector features for the bounding box.")

    # Identify guidance column (typically 'val', 'ffg', or 'value')
    value_col = None
    for col in gdf.columns:
        if col.lower() in ['val', 'ffg', 'value', 'guidance', 'grid_code']:
            value_col = col
            break
            
    if not value_col:
        # Fallback to first numeric column
        value_col = gdf.select_dtypes(include=[np.number]).columns[0]

    # Convert values to inches if dataset is provided in millimeters
    if gdf[value_col].max() > 50:
        gdf['ffg_inches'] = gdf[value_col] * 0.0393701
    else:
        gdf['ffg_inches'] = gdf[value_col]

    # 2. Render vector polygons mapped directly to exact RGB thresholds
    fig, ax = plt.subplots(figsize=(16, 9), dpi=240)
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    ax.set_axis_off()

    gdf.plot(
        column='ffg_inches',
        ax=ax,
        cmap=cmap,
        norm=norm,
        edgecolor='none',
        linewidth=0
    )

    ax.set_xlim(WEST, EAST)
    ax.set_ylim(SOUTH, NORTH)

    plt.subplots_adjust(left=0, right=0, bottom=0, top=0)
    plt.savefig(png_path, format="png", transparent=True, dpi=240)
    plt.close()

    # 3. Build KML GroundOverlay
    kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Folder>
    <name>Custom Flash Flood Guidance</name>
    <GroundOverlay>
      <name>{duration_hr}-Hour FFG</name>
      <Icon>
        <href>{png_path}</href>
      </Icon>
      <LatLonBox>
        <north>{NORTH}</north>
        <south>{SOUTH}</south>
        <east>{EAST}</east>
        <west>{WEST}</west>
      </LatLonBox>
    </GroundOverlay>
  </Folder>
</kml>"""

    with open(kml_path, "w", encoding="utf-8") as f:
        f.write(kml_content)

    # 4. Package into KMZ
    with zipfile.ZipFile(output_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(png_path, arcname=png_path)
        kmz.write(kml_path, arcname="doc.kml")

    for p in [png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz(layer_id=0, duration_hr="01", output_kmz="Custom_FFG_1hr.kmz")
