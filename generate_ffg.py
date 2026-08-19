import os
import re
import datetime
import zipfile
import requests
import pygrib
import numpy as np
import scipy.ndimage as ndimage
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm

# ------------------------------------------------------------------------------
# 1. DOMAIN BOUNDS (Ohio Region)
# ------------------------------------------------------------------------------
WEST, SOUTH, EAST, NORTH = -85.0, 38.0, -80.0, 42.0

# ------------------------------------------------------------------------------
# 2. EXACT COLOR PALETTE & THRESHOLD BREAKS (Inches)
# ------------------------------------------------------------------------------
# 9-Tier Universal scale across 1-hr, 3-hr, and 6-hr durations
bounds = [0.0, 0.50, 0.75, 1.00, 1.50, 2.00, 3.00, 4.00, 5.00, 10.0]

# CVD-Safe Perceptually Uniform Sequential (Crimson -> Cream/Grey)
colors_rgb = [
    (103/255,   0/255,  13/255),  # < 0.50"       (Very Dark Crimson)
    (165/255,  15/255,  21/255),  # 0.50" - 0.75" (Deep Red)
    (203/255,  24/255,  29/255),  # 0.75" - 1.00" (Strong Red)
    (239/255,  59/255,  44/255),  # 1.00" - 1.50" (Vibrant Red)
    (251/255, 106/255,  74/255),  # 1.50" - 2.00" (Orange-Red)
    (252/255, 146/255, 114/255),  # 2.00" - 3.00" (Soft Orange/Peach)
    (254/255, 224/255, 210/255),  # 3.00" - 4.00" (Pale Peach)
    (255/255, 245/255, 240/255),  # 4.00" - 5.00" (Cream)
    (217/255, 217/255, 217/255)   # >= 5.00"      (Light Grey)
]

cmap = ListedColormap(colors_rgb)
norm = BoundaryNorm(bounds, cmap.N)

def download_latest_iem_grib(out_path="latest_ffg.grib2"):
    now = datetime.datetime.utcnow()
    headers = {'User-Agent': 'Custom-FFG-Generator/1.0'}
    
    for offset in [0, 1, 2]:
        dt = now - datetime.timedelta(days=offset)
        base_url = f"https://mesonet.agron.iastate.edu/archive/data/{dt.strftime('%Y/%m/%d')}/model/ffg/"
        print(f"Checking {base_url} ...")
        
        try:
            response = requests.get(base_url, headers=headers, timeout=15)
            if response.status_code != 200:
                continue
                
            matches = re.findall(r'href="([^"]*5kmffg_[^"]*\.grib2)"', response.text, re.IGNORECASE)
            
            if matches:
                latest_filename = sorted(list(set(matches)))[-1]
                file_url = base_url + latest_filename
                
                print(f"Found latest file: {latest_filename}")
                resp = requests.get(file_url, headers=headers, timeout=30)
                resp.raise_for_status()
                
                with open(out_path, 'wb') as f:
                    f.write(resp.content)
                print("Download complete.")
                return
                
        except Exception as e:
            print(f"Error while checking {base_url}: {e}")
            
    raise RuntimeError("Could not find any FFG GRIB2 files.")

def process_and_render_grid(target_grb, duration_hr):
    png_path = f"ffg_overlay_{duration_hr}hr.png"
    kml_path = f"doc_{duration_hr}hr.kml"
    output_kmz = f"Custom_FFG_{duration_hr}hr.kmz"

    data_full = target_grb.values
    lats_full, lons_full = target_grb.latlons()
    lons_full = np.where(lons_full > 180, lons_full - 360, lons_full)

    # Convert metric measurements to inches
    if getattr(target_grb, 'parameterUnits', '') == 'm':
        ffg_inches = data_full * 39.3701
    else:
        ffg_inches = data_full * 0.0393701

    if np.ma.isMaskedArray(ffg_inches):
        ffg_inches = np.ma.filled(ffg_inches, fill_value=np.nan)
        
    ffg_inches = np.where(ffg_inches <= 0.01, np.nan, ffg_inches)

    # Apply NaN-Aware Gaussian Smoothing (sigma=0.6)
    valid_mask = ~np.isnan(ffg_inches)
    data_filled = np.copy(ffg_inches)
    data_filled[~valid_mask] = 0.0

    sigma = 0.6 
    smoothed_data = ndimage.gaussian_filter(data_filled, sigma=sigma)
    smoothed_mask = ndimage.gaussian_filter(valid_mask.astype(float), sigma=sigma)

    ffg_smoothed = smoothed_data / np.clip(smoothed_mask, 1e-8, 1.0)
    ffg_smoothed[~valid_mask] = np.nan

    # Render Image Canvas
    fig, ax = plt.subplots(figsize=(16, 9), dpi=240)
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    ax.set_axis_off()

    ax.contourf(
        lons_full, lats_full, ffg_smoothed,
        levels=bounds,
        cmap=cmap,
        norm=norm,
        extend='max',
        antialiased=True
    )

    ax.set_xlim(WEST, EAST)
    ax.set_ylim(SOUTH, NORTH)

    plt.subplots_adjust(left=0, right=1, bottom=0, top=1)
    plt.savefig(png_path, format="png", transparent=True, dpi=240)
    plt.close()

    # Build KML GroundOverlay
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

    # Package KMZ
    with zipfile.ZipFile(output_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(png_path, arcname=png_path)
        kmz.write(kml_path, arcname="doc.kml")

    for p in [png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)
            
    print(f"Generated {output_kmz}")

def generate_all_kmzs():
    grib_path = "latest_ffg.grib2"
    download_latest_iem_grib(grib_path)

    grbs = pygrib.open(grib_path)
    
    # Extract 1hr, 3hr, and 6hr duration grids
    target_grids = {}
    for g in grbs:
        step = str(g.stepRange)
        if '1' in step and 1 not in target_grids:
            target_grids[1] = g
        elif '3' in step and 3 not in target_grids:
            target_grids[3] = g
        elif '6' in step and 6 not in target_grids:
            target_grids[6] = g

    for duration_hr, grid in target_grids.items():
        print(f"Processing {duration_hr}-hour grid...")
        process_and_render_grid(grid, duration_hr)

    grbs.close()
    if os.path.exists(grib_path):
        os.remove(grib_path)

if __name__ == "__main__":
    generate_all_kmzs()
