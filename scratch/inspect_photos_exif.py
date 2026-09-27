import json
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import sys

sys.stdout.reconfigure(encoding='utf-8')

photos_dir = Path("GS Photos")
images = sorted(list(photos_dir.glob("*.jpg")))
print(f"Total images found: {len(images)}\n")

def get_exif_gps(image):
    exif_data = image._getexif()
    if not exif_data:
        return None
    gps_info = {}
    for tag_id, value in exif_data.items():
        tag = TAGS.get(tag_id, tag_id)
        if tag == "GPSInfo":
            for t in value:
                sub_tag = GPSTAGS.get(t, t)
                gps_info[sub_tag] = value[t]
    if "GPSLatitude" in gps_info and "GPSLongitude" in gps_info:
        lat = gps_info["GPSLatitude"]
        lon = gps_info["GPSLongitude"]
        lat_ref = gps_info.get("GPSLatitudeRef", "N")
        lon_ref = gps_info.get("GPSLongitudeRef", "E")
        
        lat_dec = float(lat[0]) + float(lat[1])/60.0 + float(lat[2])/3600.0
        if lat_ref == "S": lat_dec = -lat_dec
        lon_dec = float(lon[0]) + float(lon[1])/60.0 + float(lon[2])/3600.0
        if lon_ref == "W": lon_dec = -lon_dec
        return lat_dec, lon_dec
    return None

results = []
for img_path in images:
    try:
        with Image.open(img_path) as img:
            gps = get_exif_gps(img)
            results.append((img_path.name, img.size, gps))
    except Exception as e:
        results.append((img_path.name, None, str(e)))

print(f"{'Image Name':<25} | {'Dimensions':<12} | {'GPS Coordinates'}")
print("-" * 65)
for name, size, gps in results:
    gps_str = f"Lat: {gps[0]:.6f}, Lon: {gps[1]:.6f}" if gps else "No GPS EXIF"
    print(f"{name:<25} | {str(size):<12} | {gps_str}")
