import os
import zipfile
import urllib.request
import xarray as xr
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
# Threshold boundaries in inches
bounds = [0.0, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00, 2.50, 3.00, 4.00, 5.00, 10.0]

# Custom RGB values normalized to 0-1 range for Matplotlib
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

# ------------------------------------------------------------------------------
# 3. FETCH RAW GRIB2 DATA & RENDER OVERLAY
# ------------------------------------------------------------------------------
def generate_kmz(duration_hr="01", output_kmz="Custom_FFG_1hr.kmz"):
    # Download latest raw NCEP gridded FFG from IEM mirror
    url = f"https://mesonet.agron.iastate.edu/data/grib2/ffg_{duration_hr}h.grib2"
    grib_path = "latest_ffg.grib2"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    urllib.request.urlretrieve(url, grib_path)

    # Open dataset using cfgrib engine
    ds = xr.open_dataset(grib_path, engine="cfgrib")
    
    # Extract guidance field (convert mm to inches if needed)
    data_var = list(ds.data_vars.keys())[0]
    ffg_inches = ds[data_var] * 0.0393701  # mm -> inches

    # Render 4K transparent PNG canvas
    fig, ax = plt.subplots(figsize=(16, 9), dpi=240)
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    ax.set_axis_off()

    # Plot raw grid values mapped to exact discrete colormap
    ffg_inches.plot.pcolormesh(
        ax=ax,
        cmap=cmap,
        norm=norm,
        add_colorbar=False,
        x="longitude",
        y="latitude"
    )

    ax.set_xlim(WEST, EAST)
    ax.set_ylim(SOUTH, NORTH)
    
    plt.subplots_adjust(left=0, right=1, bottom=0, top=1)
    plt.savefig(png_path, format="png", transparent=True, dpi=240)
    plt.close()

    # --------------------------------------------------------------------------
    # 4. GENERATE KML SPECIFICATION & ZIP INTO KMZ
    # --------------------------------------------------------------------------
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

    with open(kml_path, "w") as f:
        f.write(kml_content)

    with zipfile.ZipFile(output_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(png_path, arcname=png_path)
        kmz.write(kml_path, arcname="doc.kml")

    # Clean up temporary artifacts
    for p in [grib_path, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz("01", "Custom_FFG_1hr.kmz")
