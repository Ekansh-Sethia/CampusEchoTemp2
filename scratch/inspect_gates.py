import cv2
import easyocr
from pathlib import Path

reader = easyocr.Reader(['en'], gpu=False)
for name in ["GreenGate_ag1.jpg", "GreenGate_ag2.jpg", "PNBGate_ag2.jpg", "PNBGate_ag3.jpg"]:
    p = Path("GS Photos") / name
    img = cv2.imread(str(p))
    results = reader.readtext(img)
    texts = [(text, conf) for (bbox, text, conf) in results if conf > 0.2]
    print(f"[{name}]: {texts}")
