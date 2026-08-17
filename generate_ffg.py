import os
import zipfile
import urllib.request
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

def generate_kmz(output_kmz="Custom_FFG_1hr.kmz"):
    bin_path = "ds.ffg.bin"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    # 1. Download official NWS RFC FFG GRIB2 file from TGFTP
    # This static URL continuously updates with the latest national guidance and does not block automated agents.
    url = "https://tgftp.nws.noaa.gov/SL.us008001/ST.opnl/DF.gr2/DC.ndfd/AR.conus/VP.001-003/ds.ffg.bin"
    
    print("Downloading NWS Flash Flood Guidance...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as response, open(bin_path, 'wb') as out_file:
        out_file.write(response.read())
    print("Download complete.")

    # 2. Extract Raw Numerical Grid
    grbs = pygrib.open(bin_path)
    
    # The file contains 1-hour and 3-hour forecast grids. Grab the 1-hour.
    target_grb = None
    for g in grbs:
        print(f"Found Grid: {g.name}, stepRange: {g.stepRange}")
        if '1' in str(g.stepRange):
            target_grb = g
            break
            
    if not target_grb:
        target_grb = grbs.message(1) # Safe fallback

    # Subset grid strictly to Ohio bounds
    try:
        data_sub, lats_sub, lons_sub = target_grb.data(lat1=SOUTH, lat2=NORTH, lon1=WEST+360, lon2=EAST+360)
        lons_sub = lons_sub - 360.0
    except Exception:
        data_sub, lats_sub, lons_sub = target_grb.data(lat1=SOUTH, lat2=NORTH, lon1=WEST, lon2=EAST)
    
    grbs.close()

    # Convert native metric measurements to inches
    if data_sub.max() > 50:
        ffg_inches = data_sub * 0.0393701
    else:
        ffg_inches = data_sub

    # Mask zero/trace data so the background is perfectly transparent over the map
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
    for p in [bin_path, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz("Custom_FFG_1hr.kmz")
