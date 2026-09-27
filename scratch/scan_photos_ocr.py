import cv2
import json
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Run EasyOCR on selected photos to see detected text and signs
import easyocr

reader = easyocr.Reader(['en'], gpu=False)
photos_dir = Path("GS Photos")

images_to_scan = [
    "Atc.jpg", "BMDept.jpg", "EIDept.jpg", "NCC.jpg",
    "goldenGate_ag1.jpg", "GreenGate_ag1.jpg", "PNBGate_ag1.jpg",
    "LT_ag1.jpg", "PlusPoint_ag1.jpg", "Cafe_ag1.jpg", "Volleyball_ag1.jpg"
]

print("Scanning sample images for sign text...\n")
for name in images_to_scan:
    p = photos_dir / name
    if not p.exists(): continue
    img = cv2.imread(str(p))
    if img is None: continue
    
    # Resize for faster OCR scan
    h, w = img.shape[:2]
    scale = 1200 / max(h, w)
    resized = cv2.resize(img, (int(w*scale), int(h*scale)))
    
    results = reader.readtext(resized)
    detected_texts = [text for (bbox, text, conf) in results if conf > 0.25 and len(text.strip()) > 2]
    print(f"[{name}]: {detected_texts}")
