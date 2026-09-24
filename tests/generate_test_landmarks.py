"""
Generates synthetic benchmark landmark signboard images in data/landmarks/
for Phase 3 EasyOCR and localization testing.
"""
from pathlib import Path
import cv2
import numpy as np


LANDMARKS_DIR = Path(__file__).parent.parent / "data" / "landmarks"


def draw_signboard(
    sign_text: str,
    subtitle: str = "",
    bg_color=(235, 235, 240),
    sign_bg=(25, 25, 25),
    text_color=(255, 255, 255),
    w: int = 640,
    h: int = 480
) -> np.ndarray:
    """Creates a realistic scene with a signboard mounted in the upper portion."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = bg_color

    # Add architectural wall texture/structure
    cv2.rectangle(img, (0, 0), (w, int(h * 0.7)), (210, 205, 200), -1)
    cv2.rectangle(img, (0, int(h * 0.7)), (w, h), (160, 160, 160), -1) # floor/ground
    cv2.line(img, (0, int(h * 0.7)), (w, int(h * 0.7)), (120, 120, 120), 2)

    # Pillars on sides
    cv2.rectangle(img, (20, 40), (80, int(h * 0.7)), (185, 180, 175), -1)
    cv2.rectangle(img, (w - 80, 40), (w - 20, int(h * 0.7)), (185, 180, 175), -1)

    # Signboard coordinates in upper third
    pad_x = 100
    sign_x1, sign_y1 = pad_x, 70
    sign_x2, sign_y2 = w - pad_x, 190

    # Drop shadow behind sign
    cv2.rectangle(img, (sign_x1 + 6, sign_y1 + 6), (sign_x2 + 6, sign_y2 + 6), (130, 130, 130), -1)
    # Signboard background
    cv2.rectangle(img, (sign_x1, sign_y1), (sign_x2, sign_y2), sign_bg, -1)
    # Border
    cv2.rectangle(img, (sign_x1, sign_y1), (sign_x2, sign_y2), (200, 180, 50), 3)

    # Main text sizing and centering
    font = cv2.FONT_HERSHEY_DUPLEX
    font_scale = 1.1
    thickness = 2
    (tw, th), baseline = cv2.getTextSize(sign_text, font, font_scale, thickness)

    text_x = sign_x1 + (sign_x2 - sign_x1 - tw) // 2
    text_y = sign_y1 + 60

    cv2.putText(img, sign_text, (text_x, text_y), font, font_scale, text_color, thickness, cv2.LINE_AA)

    # Subtitle if present
    if subtitle:
        sub_font_scale = 0.55
        (sub_w, sub_h), _ = cv2.getTextSize(subtitle, cv2.FONT_HERSHEY_SIMPLEX, sub_font_scale, 1)
        sub_x = sign_x1 + (sign_x2 - sign_x1 - sub_w) // 2
        sub_y = text_y + 35
        cv2.putText(img, subtitle, (sub_x, sub_y), cv2.FONT_HERSHEY_SIMPLEX, sub_font_scale, (200, 200, 200), 1, cv2.LINE_AA)

    return img


def generate_all_landmarks():
    """Generates all 5 campus landmark images matching campus_graph.json."""
    LANDMARKS_DIR.mkdir(parents=True, exist_ok=True)

    landmarks = [
        ("golden_gate.jpg", "GOLDEN GATE", "MAIN CAMPUS ENTRANCE", (20, 40, 20)),
        ("atc_building.jpg", "ATC BUILDING", "ACADEMIC & TECHNOLOGY COMPLEX", (25, 25, 60)),
        ("plus_point.jpg", "PLUS POINT", "CAMPUS CENTER & CAFE", (60, 30, 20)),
        ("silveria_hall.jpg", "SILVERIA HALL", "MAIN AUDITORIUM", (40, 20, 50)),
        ("admin_building.jpg", "ADMINISTRATIVE BUILDING", "ADMINISTRATIVE OFFICES", (30, 30, 30)),
    ]

    for filename, title, subtitle, bg in landmarks:
        filepath = LANDMARKS_DIR / filename
        img = draw_signboard(title, subtitle=subtitle, sign_bg=bg)
        cv2.imwrite(str(filepath), img)
        print(f"Generated benchmark landmark: {filepath.name}")


if __name__ == "__main__":
    generate_all_landmarks()
