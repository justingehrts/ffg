import os
import re
import zipfile
import requests
import pygrib
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

def download_latest_wpc_grib(duration_hr="01", out_path="latest_ffg.grib2"):
    """Scrapes the WPC FTP/HTTP directory to dynamically find and download the latest run."""
    base_url = "https://ftp.wpc.ncep.noaa.gov/ffg/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    print(f"Scraping {base_url} for the latest {duration_hr}-hour FFG GRIB2...")
    response = requests.get(base_url, headers=headers, timeout=15)
    response.raise_for_status()

    # Regex to extract any file containing '01h' and ending in '.grib2'
    pattern = rf'href="([^"]*?01[hH][^"]*?\.grib2)"'
    matches = re.findall(pattern, response.text, re.IGNORECASE)

    if not matches:
        raise RuntimeError(f"No GRIB2 files found matching {duration_hr}H in {base_url}")

    # Sorting alphabetically naturally places the most recent timestamp string at the end
    latest_filename = sorted(list(set(matches)))[-1]
    file_url = base_url + latest_filename

    print(f"Found latest file: {latest_filename}")
    print(f"Downloading from {file_url}...")
    
    resp = requests.get(file_url, headers=headers, timeout=30)
    resp.raise_for_status()
    
    with open(out_path, 'wb') as f:
        f.write(resp.content)
    print("Download complete.")

def generate_kmz(duration_hr="01", output_kmz="Custom_FFG_1hr.kmz"):
    grib_path = "latest_ffg.grib2"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    # 1. Download Dynamic GRIB2
    download_latest_wpc_grib(duration_hr, grib_path)

    # 2. Extract Raw Numerical Grid
    grbs = pygrib.open(grib_path)
    grb = grbs.message(1)
    
    # Subset grid strictly to Ohio bounds
    try:
        data_sub, lats_sub, lons_sub = grb.data(lat1=SOUTH, lat2=NORTH, lon1=WEST+360, lon2=EAST+360)
        lons_sub = lons_sub - 360.0
    except Exception:
        data_sub, lats_sub, lons_sub = grb.data(lat1=SOUTH, lat2=NORTH, lon1=WEST, lon2=EAST)
    
    grbs.close()

    # Convert millimeters to inches if necessary
    if data_sub.max() > 50:
        ffg_inches = data_sub * 0.0393701
    else:
        ffg_inches = data_sub

    # Mask zero or trace data so the background is perfectly transparent
    ffg_inches = np.where(ffg_inches <= 0.01, np.nan, ffg_inches)

    # 3. Render Custom Image Canvas
    fig, ax = plt.subplots(figsize=(16, 9), dpi=240)
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    ax.set_axis_off()

    ax.pcolormesh(
        lons_sub, lats_sub, ffg_inches,
        cmap=cmap,
        norm=norm,
        shading='auto'
    )

    ax.set_xlim(WEST, EAST)
    ax.set_ylim(SOUTH, NORTH)

    plt.subplots_adjust(left=0, right=1, bottom=0, top=1)
    plt.savefig(png_path, format="png", transparent=True, dpi=240)
    plt.close()

    # 4. Build KML GroundOverlay
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

    # 5. Package KMZ
    with zipfile.ZipFile(output_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(png_path, arcname=png_path)
        kmz.write(kml_path, arcname="doc.kml")

    # Cleanup temporary workspace
    for p in [grib_path, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz("01", "Custom_FFG_1hr.kmz")
