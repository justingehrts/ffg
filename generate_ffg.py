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
# 2. EXACT COLOR MAPPING TABLE (NOAA Standard RGB -> Your Custom RGB)
# ------------------------------------------------------------------------------
# Key: NOAA Default RGB | Value: Target Custom RGB
PALETTE_MAP = [
    # Index 1  | < 0.25"   (NOAA: 115,0,0     -> Custom: 125,1,18)
    ((115, 0, 0),     (125, 1, 18)),
    # Index 2  | 0.25"-0.50" (NOAA: 230,0,0     -> Custom: 154,42,77)
    ((230, 0, 0),     (154, 42, 77)),
    # Index 3  | 0.50"-0.75" (NOAA: 255,115,0   -> Custom: 179,74,120)
    ((255, 115, 0),   (179, 74, 120)),
    # Index 4  | 0.75"-1.00" (NOAA: 255,170,0   -> Custom: 179,74,120)
    ((255, 170, 0),   (179, 74, 120)),
    # Index 5  | 1.00"-1.50" (NOAA: 255,255,0   -> Custom: 199,106,158))
    ((255, 255, 0),   (199, 106, 158)),
    # Index 6  | 1.50"-2.00" (NOAA: 170,255,0   -> Custom: 214,138,190))
    ((170, 255, 0),   (214, 138, 190)),
    # Index 7  | 2.00"-2.50" (NOAA: 0,255,0     -> Custom: 225,168,217))
    ((0, 255, 0),     (225, 168, 217)),
    # Index 8  | 2.50"-3.00" (NOAA: 0,255,194   -> Custom: 225,168,217))
    ((0, 255, 194),   (225, 168, 217)),
    # Index 9  | 3.00"-4.00" (NOAA: 0,194,255   -> Custom: 233,196,238))
    ((0, 194, 255),   (233, 196, 238)),
    # Index 10 | 4.00"-5.00" (NOAA: 0,102,255   -> Custom: 239,221,250))
    ((0, 102, 255),   (239, 221, 250)),
    # Index 11 | >= 5.00"    (NOAA: 0,0,255     -> Custom: 242,240,246))
    ((0, 0, 255),     (242, 240, 246)),
]

def generate_kmz(duration_layer="show:0", duration_hr="01", output_kmz="Custom_FFG_1hr.kmz"):
    raw_img_path = "raw_ffg.png"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    # 1. Download export from NOAA REST service
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

    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(export_url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response, open(raw_img_path, 'wb') as out_file:
        out_file.write(response.read())

    # 2. Process image with Pillow and NumPy
    img = Image.open(raw_img_path).convert("RGBA")
    arr = np.array(img)

    r = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    b = arr[:, :, 2].astype(int)
    a = arr[:, :, 3]

    # Mask non-transparent pixels
    opaque_mask = a > 0
    new_arr = np.zeros_like(arr)

    if np.any(opaque_mask):
        # Flatten pixels for vectorized distance matching
        r_flat = r[opaque_mask]
        g_flat = g[opaque_mask]
        b_flat = b[opaque_mask]

        src_colors = np.array([pair[0] for pair in PALETTE_MAP])  # Shape: (N, 3)
        tgt_colors = np.array([pair[1] for pair in PALETTE_MAP])  # Shape: (N, 3)

        pixels = np.column_stack((r_flat, g_flat, b_flat))  # Shape: (P, 3)

        # Compute 3D Euclidean RGB distances between pixels and target palette
        distances = np.linalg.norm(pixels[:, np.newaxis, :] - src_colors[np.newaxis, :, :], axis=2)
        closest_indices = np.argmin(distances, axis=1)
        min_distances = np.min(distances, axis=1)

        # Only recolor pixels within distance threshold (tolSq <= 30^2)
        valid_match = min_distances <= 30
        matched_targets = tgt_colors[closest_indices]

        # Construct recolored canvas array
        recolored_pixels = np.zeros((len(r_flat), 4), dtype=np.uint8)
        recolored_pixels[valid_match, :3] = matched_targets[valid_match]
        recolored_pixels[valid_match, 3] = a[opaque_mask][valid_match]

        new_arr[opaque_mask] = recolored_pixels

    # Save recolored overlay
    final_img = Image.fromarray(new_arr, mode="RGBA")
    final_img.save(png_path, format="PNG")

    # 3. Create GroundOverlay KML
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

    # Cleanup temporary local artifacts
    for p in [raw_img_path, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz(duration_layer="show:0", duration_hr="01", output_kmz="Custom_FFG_1hr.kmz")
