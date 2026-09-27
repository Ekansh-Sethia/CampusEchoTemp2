import cv2
from pathlib import Path

# Print basic stats for all 28 images
photos_dir = Path("GS Photos")
images = sorted(list(photos_dir.glob("*.jpg")))
print(f"Total images: {len(images)}")

groups = {}
for img in images:
    name = img.stem
    prefix = name.split("_")[0]
    groups.setdefault(prefix, []).append(img.name)

for prefix, files in sorted(groups.items()):
    print(f"{prefix} ({len(files)} images): {files}")
