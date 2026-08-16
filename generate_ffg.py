import os
import zipfile
import urllib.request
import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm

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

def download_ffg_shapefile(zip_path="ffg_shapefile.zip", extract_dir="shp_data"):
    """Downloads raw national FFG vector shapefile bundle from WPC."""
    url = "https://www.wpc.ncep.noaa.gov/ffg/ffg_latest.zip"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response, open(zip_path, 'wb') as out_file:
        out_file.write(response.read())

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

def generate_kmz(duration_hr="01", output_kmz="Custom_FFG_1hr.kmz"):
    zip_path = "ffg_shapefile.zip"
    extract_dir = "shp_data"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    # 1. Download & Extract Raw Vectors
    download_ffg_shapefile(zip_path, extract_dir)

    # Find .shp file inside extracted directory
    shp_file = None
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith(".shp"):
                shp_file = os.path.join(root, file)
                break

    if not shp_file:
        raise FileNotFoundError("No shapefile (.shp) found in downloaded archive.")

    # 2. Load Shapefile into GeoDataFrame
    gdf = gpd.read_file(shp_file)

    # Reproject to standard WGS84 lat/lon if necessary
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # Clip vectors to target bounding box
    gdf = gdf.cx[WEST:EAST, SOUTH:NORTH]

    # Identify numeric FFG guidance column (FFG01, FFG1, VAL, etc.)
    val_col = None
    possible_cols = [f"FFG{duration_hr}", f"FFG_{duration_hr}H", "FFG01", "FFG1", "VAL", "VALUE"]
    for col in gdf.columns:
        if col.upper() in possible_cols:
            val_col = col
            break

    if not val_col:
        # Fallback to first numeric data column
        val_col = gdf.select_dtypes(include=[np.number]).columns[0]

    # Convert mm to inches if data values > 50
    if gdf[val_col].max() > 50:
        gdf['ffg_inches'] = gdf[val_col] * 0.0393701
    else:
        gdf['ffg_inches'] = gdf[val_col]

    # Filter out nodata/zero values for transparent canvas
    gdf = gdf[gdf['ffg_inches'] > 0]

    # 3. Render High-Res Vector Overlay with Exact Colors
    fig, ax = plt.subplots(figsize=(16, 9), dpi=240)
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    ax.set_axis_off()

    gdf.plot(
        column='ffg_inches',
        ax=ax,
        cmap=cmap,
        norm=norm,
        edgecolor='none',  # No outline borders
        linewidth=0
    )

    ax.set_xlim(WEST, EAST)
    ax.set_ylim(SOUTH, NORTH)

    plt.subplots_adjust(left=0, right=1, bottom=0, top=1)
    plt.savefig(png_path, format="png", transparent=True, dpi=240)
    plt.close()

    # 4. Generate GroundOverlay KML
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

    # 5. Zip into KMZ
    with zipfile.ZipFile(output_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(png_path, arcname=png_path)
        kmz.write(kml_path, arcname="doc.kml")

    # Clean up local temp files
    if os.path.exists(zip_path): os.remove(zip_path)
    if os.path.exists(png_path): os.remove(png_path)
    if os.path.exists(kml_path): os.remove(kml_path)

if __name__ == "__main__":
    generate_kmz(duration_hr="01", output_kmz="Custom_FFG_1hr.kmz")
