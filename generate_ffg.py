import os
import zipfile
import urllib.request
from datetime import datetime, timezone
import pygrib
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
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

def download_latest_ffg(duration_hr="01", grib_path="latest_ffg.grib2"):
    """Fetches the latest GRIB2 FFG file from NOAA NOMADS or IEM Archive."""
    # Attempt NOAA NOMADS current day run first
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    
    # Standard NOAA NOMADS URL for National FFG
    urls = [
        f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/ffg/prod/ffg.{date_str}/ffg_{duration_hr}h.grib2",
        f"https://mesonet.agron.iastate.edu/data/model/ffg/ffg_{duration_hr}h.grib2",
        f"https://noaa-nws-ffg-pds.s3.amazonaws.com/ffg_{duration_hr}h.grib2"
    ]

    download_success = False
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response, open(grib_path, 'wb') as out_file:
                out_file.write(response.read())
            if os.path.exists(grib_path) and os.path.getsize(grib_path) > 1000:
                print(f"Successfully downloaded GRIB2 from: {url}")
                download_success = True
                break
        except Exception as e:
            print(f"Attempt failed for {url}: {e}")
            continue

    if not download_success:
        raise RuntimeError("Could not download FFG GRIB2 data from any NOAA/IEM mirror source.")

def generate_kmz(duration_hr="01", output_kmz="Custom_FFG_1hr.kmz"):
    grib_path = "latest_ffg.grib2"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    download_latest_ffg(duration_hr, grib_path)

    grbs = pygrib.open(grib_path)
    grb = grbs.message(1)
    
    data = grb.values
    lats, lons = grb.latlons()
    
    # Normalize longitudes to [-180, 180]
    lons = np.where(lons > 180, lons - 360, lons)

    # Convert mm to inches if needed (check unit attribute if available)
    units = getattr(grb, 'units', 'mm')
    if 'mm' in str(units).lower() or data.max() > 50:
        ffg_inches = data * 0.0393701
    else:
        ffg_inches = data

    fig = plt.figure(figsize=(16, 9), dpi=240)
    ax = plt.axes([0, 0, 1, 1], projection=ccrs.PlateCarree())
    ax.patch.set_alpha(0)
    fig.patch.set_alpha(0)
    ax.set_axis_off()

    ax.pcolormesh(
        lons, lats, ffg_inches,
        cmap=cmap,
        norm=norm,
        transform=ccrs.PlateCarree(),
        shading='auto'
    )

    ax.set_extent([WEST, EAST, SOUTH, NORTH], crs=ccrs.PlateCarree())

    plt.savefig(png_path, format="png", transparent=True, dpi=240)
    plt.close()

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

    for p in [grib_path, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz("01", "Custom_FFG_1hr.kmz")
