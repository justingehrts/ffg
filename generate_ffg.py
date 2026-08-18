import os
import re
import datetime
import zipfile
import requests
import pygrib
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from pyproj import Transformer

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
    now = datetime.datetime.utcnow()
    headers = {'User-Agent': 'Custom-FFG-Generator/1.0'}
    
    for offset in [0, 1, 2]:
        dt = now - datetime.timedelta(days=offset)
        base_url = f"https://mesonet.agron.iastate.edu/archive/data/{dt.strftime('%Y/%m/%d')}/model/ffg/"
        
        try:
            response = requests.get(base_url, headers=headers, timeout=15)
            if response.status_code != 200:
                continue
                
            matches = re.findall(r'href="([^"]*5kmffg_[^"]*\.grib2)"', response.text, re.IGNORECASE)
            if matches:
                latest_filename = sorted(list(set(matches)))[-1]
                file_url = base_url + latest_filename
                
                resp = requests.get(file_url, headers=headers, timeout=30)
                resp.raise_for_status()
                
                with open(out_path, 'wb') as f:
                    f.write(resp.content)
                return
        except Exception as e:
            print(f"Checking {base_url} failed: {e}")
            
    raise RuntimeError("Could not find any FFG GRIB2 files in the archive.")

def generate_kmz(output_kmz="Custom_FFG_1hr.kmz"):
    grib_path = "latest_ffg.grib2"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    download_latest_iem_grib(grib_path)

    grbs = pygrib.open(grib_path)
    target_grb = None
    for g in grbs:
        if '1' in str(g.stepRange):
            target_grb = g
            break
    if not target_grb:
        target_grb = grbs.message(1)

    # 1. Read Raw Array & Lat/Lon Geometries
    data_full = target_grb.values.astype(float)
    lats_full, lons_full = target_grb.latlons()
    lons_full = np.where(lons_full > 180, lons_full - 360, lons_full)
    grbs.close()

    # 2. Mask Nodata Values (> 900) before unit conversion
    data_full[data_full > 900] = np.nan
    data_full[data_full <= 0] = np.nan

    # Convert mm (kg/m^2) to Inches
    ffg_inches = data_full * 0.0393701

    # 3. Render Canvas with Matplotlib
    fig, ax = plt.subplots(figsize=(16, 9), dpi=240)
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    ax.set_axis_off()

    # Use contourf instead of pcolormesh to create smooth, broadcast-ready isopleths
    # rather than rendering the jagged 5km data blocks.
    ax.contourf(
        lons_full, lats_full, ffg_inches,
        levels=bounds,
        cmap=cmap,
        norm=norm,
        extend='max',
        antialiased=True
    )

    # Crop precisely to bounding box
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

    with zipfile.ZipFile(output_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(png_path, arcname=png_path)
        kmz.write(kml_path, arcname="doc.kml")

    for p in [grib_path, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz("Custom_FFG_1hr.kmz")
