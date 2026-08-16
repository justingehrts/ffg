import os
import gzip
import zipfile
import boto3
from botocore import UNSIGNED
from botocore.config import Config
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

def download_latest_mrms_from_aws(duration_hr="01", gz_path="latest_ffg.grib2.gz"):
    """Fetches the latest MRMS FFG GRIB2 file anonymously from NOAA's AWS Open Data bucket."""
    # Connect to S3 anonymously (no AWS credentials required)
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    bucket_name = 'noaa-mrms-pds'
    prefix = f'CONUS/FlashFloodGuidance_{duration_hr}H/'

    # Paginate through the bucket directory to get all available files
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
    
    all_keys = []
    for page in pages:
        if 'Contents' in page:
            for obj in page['Contents']:
                if obj['Key'].endswith('.grib2.gz'):
                    all_keys.append(obj['Key'])
                    
    if not all_keys:
        raise RuntimeError(f"No GRIB2 files found in AWS S3 bucket s3://{bucket_name}/{prefix}")
        
    # MRMS keys are time-stamped (e.g., MRMS_FlashFloodGuidance_01H_..._20260816-180000.grib2.gz)
    # Sorting alphabetically naturally places the absolute newest file at the very end of the list
    latest_key = sorted(all_keys)[-1]
    
    print(f"Downloading {latest_key} from AWS Open Data...")
    s3.download_file(bucket_name, latest_key, gz_path)
    print("Download complete.")

def generate_kmz(duration_hr="01", output_kmz="Custom_FFG_1hr.kmz"):
    gz_path = "latest_ffg.grib2.gz"
    grib_path = "latest_ffg.grib2"
    png_path = "ffg_overlay.png"
    kml_path = "doc.kml"

    # 1. Download & Decompress FFG Data
    download_latest_mrms_from_aws(duration_hr, gz_path)

    with gzip.open(gz_path, 'rb') as f_in, open(grib_path, 'wb') as f_out:
        f_out.write(f_in.read())

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

    # Convert millimeters to inches (MRMS is stored natively in mm)
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
    for p in [gz_path, grib_path, png_path, kml_path]:
        if os.path.exists(p):
            os.remove(p)

if __name__ == "__main__":
    generate_kmz("01", "Custom_FFG_1hr.kmz")
