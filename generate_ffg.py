import os
import re
import datetime
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

def download_latest_iem_grib(out_path="latest_ffg.grib2"):
    """Scrapes the IEM academic archive to dynamically find and download the latest NWS FFG run."""
    now = datetime.datetime.utcnow()
    headers = {'User-Agent': 'Custom-FFG-Generator/1.0'}
    
    # Iterate through today and the past two days to ensure we find the latest file
    for offset in [0, 1, 2]:
        dt = now - datetime.timedelta(days=offset)
        base_url = f"https://mesonet.agron.iastate.edu/archive/data/{dt.strftime('%Y/%m/%d')}/model/ffg/"
        print(f"Checking {base_url} ...")
        
        try:
            response = requests.get(base_url, headers=headers, timeout=15)
            if response.status_code != 200:
                continue
                
            # Regex to match the official 5km gridded FFG files
            matches = re.findall(r'href="([^"]*5kmffg_[^"]*\.grib2)"', response.text, re.IGNORECASE)
            
            if matches:
                # Alphabetical sort guarantees the latest timestamp is at the end of the list
                latest_filename = sorted(list(set(matches)))[-1]
                file_url = base_url + latest_filename
                
                print(f"Found latest file: {latest_filename}")
                print(f"Downloading from {file_url}...")
                
                resp = requests.get(file_url, headers=headers, timeout=30)
                resp.raise_for_status()
                
                with open(out_path, 'wb') as f:
                    f.write(resp.content)
                print("Download complete.")
                return
                
        except Exception as e:
            print(f"Error while checking {base_url}: {e}")
            
    raise RuntimeError("Could not find any FFG GRIB2 files in the IEM archive for the past 3 days.")

def generate_kmz(output_kmz="Custom_FFG_1hr.kmz"):
    grib_path = "latest_ffg.grib2"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    # 1. Download Dynamic GRIB2 from IEM
    download_latest_iem_grib(grib_path)

    # 2. Extract Raw Numerical Grid
    grbs = pygrib.open(grib_path)
    
    # 5kmffg files usually contain multiple hour steps; find the 1-hour grid
    target_grb = None
    for g in grbs:
        print(f"Discovered Grid: {g.name}, stepRange: {g.stepRange}, units: {g.parameterUnits}")
        if '1' in str(g.stepRange):
            target_grb = g
            break
            
    if not target_grb:
        target_grb = grbs.message(1) # Safe fallback

    # Load the entire 2D grid instead of subsetting, which prevents flattening 
    # non-regular grids into 1D arrays. Matplotlib will handle the geographic crop.
    data_full = target_grb.values
    lats_full, lons_full = target_grb.latlons()
    
    # Ensure longitudes are on a -180 to 180 scale
    lons_full = np.where(lons_full > 180, lons_full - 360, lons_full)
    
    grbs.close()

    # Convert native metric measurements to inches
    if getattr(target_grb, 'parameterUnits', '') == 'm':
        ffg_inches = data_full * 39.3701
    else:
        # FFG defaults to kg m-2 (millimeters)
        ffg_inches = data_full * 0.0393701

    # Flatten out masked arrays and explicitly set zeros to NaN for transparency
    if np.ma.isMaskedArray(ffg_inches):
        ffg_inches = np.ma.filled(ffg_inches, fill_value=np.nan)
        
    ffg_inches = np.where(ffg_inches <= 0.01, np.nan, ffg_inches)

    # 3. Render Custom Image Canvas
    fig, ax = plt.subplots(figsize=(16, 9), dpi=240)
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    ax.set_axis_off()

    ax.pcolormesh(
        lons_full, lats_full, ffg_inches,
        cmap=cmap,
        norm=norm,
        shading='auto'
    )

    # Crop the render strictly to the Ohio bounds
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

    # 5. Package KMZ
    with zipfile.ZipFile(output_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(png_path, arcname=png_path)
        kmz.write(kml_path, arcname="doc.kml")

    # Cleanup temporary workspace
    for p in [grib_path, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz("Custom_FFG_1hr.kmz")
