import os
import zipfile
import urllib.request
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import rasterio

# ------------------------------------------------------------------------------
# 1. DOMAIN BOUNDS & RESOLUTION (Ohio Region)
# ------------------------------------------------------------------------------
WEST, SOUTH, EAST, NORTH = -85.0, 38.0, -80.0, 42.0
IMAGE_RES = "3840,2160"

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

def download_raw_numeric_raster(duration_layer="show:0", tif_path="raw_ffg.tif"):
    """Downloads raw 32-bit floating-point numerical grid directly from NOAA's active ImageServer."""
    base_url = "https://mapservices.weather.noaa.gov/raster/rest/services/precip/rfc_gridded_ffg/MapServer/export"
    
    params = [
        f"bbox={WEST},{SOUTH},{EAST},{NORTH}",
        "bboxSR=4326",
        "imageSR=4326",
        f"size={IMAGE_RES}",
        "format=tiff",  # Request raw GeoTIFF data values instead of PNG
        "transparent=true",
        f"layers={duration_layer}",
        "f=image"
    ]
    
    export_url = f"{base_url}?" + "&".join(params)
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    req = urllib.request.Request(export_url, headers=headers)
    
    with urllib.request.urlopen(req, timeout=30) as response, open(tif_path, 'wb') as out_file:
        out_file.write(response.read())

def generate_kmz(duration_layer="show:0", duration_hr="01", output_kmz="Custom_FFG_1hr.kmz"):
    tif_path = "raw_ffg.tif"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    # 1. Fetch raw 32-bit float raster grid from NOAA
    download_raw_numeric_raster(duration_layer, tif_path)

    # 2. Open TIFF numerical array directly into memory
    with rasterio.open(tif_path) as src:
        data = src.read(1).astype(float)
        
        # Handle nodata / zero masking
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        data[data <= 0] = np.nan

        # Convert values to inches if provided in millimeters
        if np.nanmax(data) > 50:
            ffg_inches = data * 0.0393701
        else:
            ffg_inches = data

    # 3. Render clean, discrete color array (Zero anti-aliasing / zero edge artifacts)
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

    plt.subplots_adjust(left=0, right=0, bottom=0, top=0)
    plt.savefig(png_path, format="png", transparent=True, dpi=240)
    plt.close()

    # 4. Create GroundOverlay KML
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

    # Cleanup temporary local artifacts
    for p in [tif_path, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz(duration_layer="show:0", duration_hr="01", output_kmz="Custom_FFG_1hr.kmz")
