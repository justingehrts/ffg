import os
import zipfile
import urllib.request
from datetime import datetime, timezone, timedelta
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import rasterio
from rasterio.mask import mask
from shapely.geometry import box

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

def download_geotiff(duration_hr="01", tif_path="latest_ffg.tif"):
    """Fetches raw GeoTIFF grid from NOAA NWS Open Data buckets."""
    now = datetime.now(timezone.utc)
    dates_to_check = [now, now - timedelta(days=1)]
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    download_success = False

    for dt in dates_to_check:
        date_str = dt.strftime("%Y%m%d")
        
        urls = [
            f"https://noaa-nws-ffg-pds.s3.amazonaws.com/ffg_{date_str}/ffg_{duration_hr}h_{date_str}.tif",
            f"https://water.weather.gov/precip/pds/ffg/ffg_{duration_hr}h.tif",
            f"https://mesonet.agron.iastate.edu/data/raster/ffg/ffg_{duration_hr}h.tif"
        ]

        for url in urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as response, open(tif_path, 'wb') as out_file:
                    out_file.write(response.read())
                
                if os.path.exists(tif_path) and os.path.getsize(tif_path) > 5000:
                    print(f"Successfully retrieved GeoTIFF from: {url}")
                    download_success = True
                    break
            except Exception as e:
                print(f"Failed attempt for {url}: {e}")
                continue
        
        if download_success:
            break

    if not download_success:
        raise RuntimeError("Unable to download FFG GeoTIFF data from NOAA sources.")

def generate_kmz(duration_hr="01", output_kmz="Custom_FFG_1hr.kmz"):
    tif_path = "latest_ffg.tif"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    download_geotiff(duration_hr, tif_path)

    # Open GeoTIFF grid with rasterio
    with rasterio.open(tif_path) as src:
        # Crop data array directly to Ohio bounding box
        bbox_geom = [box(WEST, SOUTH, EAST, NORTH)]
        out_image, out_transform = mask(src, bbox_geom, crop=True)
        data = out_image[0].astype(float)
        
        # Mask out-of-bounds/nodata pixels
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        data[data <= 0] = np.nan

        # Convert mm to inches if dataset is in millimeters
        if np.nanmax(data) > 50:
            ffg_inches = data * 0.0393701
        else:
            ffg_inches = data

    # Render clean raster overlay with exact color thresholds
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

    # Generate GroundOverlay KML
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

    # Package into KMZ
    with zipfile.ZipFile(output_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(png_path, arcname=png_path)
        kmz.write(kml_path, arcname="doc.kml")

    for p in [tif_path, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz(duration_hr="01", output_kmz="Custom_FFG_1hr.kmz")
