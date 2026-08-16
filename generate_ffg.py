import os
import zipfile
import urllib.request
from PIL import Image
import numpy as np

# ------------------------------------------------------------------------------
# 1. DOMAIN BOUNDS & RESOLUTION (Ohio Region)
# ------------------------------------------------------------------------------
WEST, SOUTH, EAST, NORTH = -85.0, 38.0, -80.0, 42.0
IMAGE_RES = "3840,2160"

# ------------------------------------------------------------------------------
# 2. EXACT COLOR SWAP MAP (NOAA Default RGB -> Your Custom RGB)
# ------------------------------------------------------------------------------
PALETTE_MAP = {
    # NOAA Default RGB tuple : Custom RGB tuple
    (115, 0, 0):    (125, 1, 18),    # < 0.25"
    (230, 0, 0):    (154, 42, 77),   # 0.25"-0.50"
    (255, 115, 0):  (179, 74, 120),  # 0.50"-0.75"
    (255, 170, 0):  (179, 74, 120),  # 0.75"-1.00"
    (255, 255, 0):  (199, 106, 158), # 1.00"-1.50"
    (170, 255, 0):  (214, 138, 190), # 1.50"-2.00"
    (0, 255, 0):    (225, 168, 217), # 2.00"-2.50"
    (0, 255, 194):  (225, 168, 217), # 2.50"-3.00"
    (0, 194, 255):  (233, 196, 238), # 3.00"-4.00"
    (0, 102, 255):  (239, 221, 250), # 4.00"-5.00"
    (0, 0, 255):    (242, 240, 246), # >= 5.00"
    (0, 153, 0):    (125, 1, 18),    # Boundary green shadow
    (0, 128, 0):    (125, 1, 18)     # Boundary green shadow
}

def generate_kmz(duration_layer="show:0", output_kmz="Custom_FFG_1hr.kmz"):
    raw_png = "raw_ffg.png"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    # Construct NOAA MapServer export URL for 1-hour FFG
    base_url = "https://mapservices.weather.noaa.gov/raster/rest/services/precip/rfc_gridded_ffg/MapServer/export"
    params = [
        f"bbox={WEST},{SOUTH},{EAST},{NORTH}",
        "bboxSR=4326",
        "imageSR=4326",
        f"size={IMAGE_RES}",
        "format=png32",
        "transparent=true",
        f"layers={duration_layer}",
        "f=image"
    ]
    export_url = f"{base_url}?" + "&".join(params)

    # Download raw image from NOAA REST service
    req = urllib.request.Request(export_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as response, open(raw_png, 'wb') as out_file:
        out_file.write(response.read())

    # Open image and process pixels using NumPy for exact color mapping
    img = Image.open(raw_png).convert("RGBA")
    arr = np.array(img)

    # Vectorized color replacement with tolerance matching for edges
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
    
    # Start with transparent mask for empty background
    new_arr = np.zeros_like(arr)

    # Map each target color based on Euclidean distance / exact match
    for src_rgb, tgt_rgb in PALETTE_MAP.items():
        # Match pixels within tolerance window of NOAA's standard colors
        mask = (
            (np.abs(r.astype(int) - src_rgb[0]) < 25) &
            (np.abs(g.astype(int) - src_rgb[1]) < 25) &
            (np.abs(b.astype(int) - src_rgb[2]) < 25) &
            (a > 0)
        )
        new_arr[mask, 0] = tgt_rgb[0]
        new_arr[mask, 1] = tgt_rgb[1]
        new_arr[mask, 2] = tgt_rgb[2]
        new_arr[mask, 3] = a[mask]  # Preserve original alpha/transparency

    # Save recolored overlay
    final_img = Image.fromarray(new_arr, mode="RGBA")
    final_img.save(png_path, format="PNG")

    # Generate KML markup
    kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Folder>
    <name>Custom Flash Flood Guidance</name>
    <GroundOverlay>
      <name>Flash Flood Guidance</name>
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

    # Package into KMZ archive
    with zipfile.ZipFile(output_kmz, "w", zipfile.ZIP_DEFLATED) as kmz:
        kmz.write(png_path, arcname=png_path)
        kmz.write(kml_path, arcname="doc.kml")

    # Cleanup temporary local artifacts
    for p in [raw_png, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz("show:0", "Custom_FFG_1hr.kmz")
