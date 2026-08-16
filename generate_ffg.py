import os
import zipfile
import urllib.request
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

def fetch_iem_grid(duration_hr="1"):
    """Fetches raw FFG numerical grid from Iowa State IEM web API."""
    url = f"https://mesonet.agron.iastate.edu/cgi-bin/wms/ffg.cgi?VER={duration_hr}&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=ffg_{duration_hr}h&STYLES=&SRS=EPSG:4326&BBOX={WEST},{SOUTH},{EAST},{NORTH}&WIDTH=1920&HEIGHT=1080&FORMAT=image/png"
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(url, headers=headers)
    
    png_path = "iem_raw.png"
    with urllib.request.urlopen(req, timeout=30) as response, open(png_path, 'wb') as out_file:
        out_file.write(response.read())
        
    return png_path

def generate_kmz(duration_hr="1", output_kmz="Custom_FFG_1hr.kmz"):
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    # Download clean WMS raster layer from IEM
    raw_png = fetch_iem_grid(duration_hr)

    # Read image array directly
    img = plt.imread(raw_png)
    
    # Extract alpha channel to preserve transparency outside the data coverage
    if img.shape[2] == 4:
        alpha = img[:, :, 3]
    else:
        alpha = np.ones((img.shape[0], img.shape[1]))

    # Convert RGB array to grayscale luminance proxy to extract relative guidance steps
    # IEM outputs a clean 8-bit indexed palette without background maps
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    
    # Build clean transparent RGBA canvas
    h, w = r.shape
    recolored = np.zeros((h, w, 4))

    # Map IEM indexed values directly to target RGB array
    # Mask out non-data pixels (where alpha == 0 or white background)
    valid_data = (alpha > 0) & ~((r > 0.95) & (g > 0.95) & (b > 0.95))

    # Map data array
    recolored[valid_data, 0] = 199/255  # Red
    recolored[valid_data, 1] = 106/255  # Green
    recolored[valid_data, 2] = 158/255  # Blue
    recolored[valid_data, 3] = alpha[valid_data]  # Alpha

    # Save clean overlay
    plt.imsave(png_path, recolored)

    # 3. Write GroundOverlay KML
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

    # 4. Package into KMZ
    with zipfile.ZipFile(output_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(png_path, arcname=png_path)
        kmz.write(kml_path, arcname="doc.kml")

    for p in [raw_png, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz(duration_hr="1", output_kmz="Custom_FFG_1hr.kmz")
