import os
import zipfile
import urllib.request
import urllib.parse
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import rasterio

# ------------------------------------------------------------------------------
# 1. DOMAIN BOUNDS (Ohio Region)
# ------------------------------------------------------------------------------
WEST, SOUTH, EAST, NORTH = -85.0, 38.0, -80.0, 42.0

# ------------------------------------------------------------------------------
# 2. EXACT PALETTE BREAKS (Inches)
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

def generate_kmz(output_kmz="Custom_FFG_1hr.kmz"):
    raw_tif = "raw_ffg.tif"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    # Query NOAA Raster MapServer for Layer 0 (1-Hour FFG) exporting raw TIFF float values
    base_url = "https://mapservices.weather.noaa.gov/raster/rest/services/precip/rfc_gridded_ffg/MapServer/export"
    params = {
        "bbox": f"{WEST},{SOUTH},{EAST},{NORTH}",
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": "1920,1080",
        "format": "tiff",  # Request raw raster values
        "transparent": "true",
        "layers": "show:0",
        "f": "image"
    }

    export_url = f"{base_url}?" + urllib.parse.urlencode(params)
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    req = urllib.request.Request(export_url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response, open(raw_tif, 'wb') as out_file:
        out_file.write(response.read())

    # Read numerical array directly with rasterio
    with rasterio.open(raw_tif) as src:
        data = src.read(1).astype(float)
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        data[data <= 0] = np.nan

        # Convert mm to inches if needed
        if np.nanmax(data) > 50:
            ffg_inches = data * 0.0393701
        else:
            ffg_inches = data

    # Plot directly with matplotlib using your exact custom color mapping
    fig, ax = plt.subplots(figsize=(16, 9), dpi=240)
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    ax.set_axis_off()

    ax.imshow(
        ffg_inches,
        cmap=cmap,
        norm=norm,
        extent=[WEST, EAST, SOUTH, NORTH],
        origin='upper',
        interpolation='nearest'
    )

    ax.set_xlim(WEST, EAST)
    ax.set_ylim(SOUTH, NORTH)

    plt.subplots_adjust(left=0, right=1, bottom=0, top=1)
    plt.savefig(png_path, format="png", transparent=True, dpi=240)
    plt.close()

    # Create GroundOverlay KML
    kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Folder>
    <name>Custom Flash Flood Guidance</name>
    <GroundOverlay>
      <name>1-Hour FFG</name>
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

    with zipfile.ZipFile(output_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(png_path, arcname=png_path)
        kmz.write(kml_path, arcname="doc.kml")

    for p in [raw_tif, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz("Custom_FFG_1hr.kmz")
