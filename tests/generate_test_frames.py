"""Generates synthetic test frames for perception testing and offline demoing."""
from pathlib import Path
import cv2
import numpy as np


OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_frames"


def draw_base_hallway(w: int = 640, h: int = 480) -> np.ndarray:
    """Draws a perspective hallway with side walls, ceiling, and floor."""
    img = np.zeros((h, w, 3), dtype=np.uint8)

    # Floor (light gray)
    cv2.rectangle(img, (0, int(h * 0.4)), (w, h), (180, 180, 180), -1)
    # Ceiling (white/cream)
    cv2.rectangle(img, (0, 0), (w, int(h * 0.4)), (240, 240, 245), -1)

    # Left wall (beige)
    pts_left = np.array([[0, 0], [int(w * 0.25), int(h * 0.4)], [int(w * 0.25), h], [0, h]], np.int32)
    cv2.fillPoly(img, [pts_left], (195, 175, 155))

    # Right wall (beige)
    pts_right = np.array([[w, 0], [int(w * 0.75), int(h * 0.4)], [int(w * 0.75), h], [w, h]], np.int32)
    cv2.fillPoly(img, [pts_right], (195, 175, 155))

    # Corridor perspective lines
    cv2.line(img, (int(w * 0.25), int(h * 0.4)), (0, h), (140, 140, 140), 2)
    cv2.line(img, (int(w * 0.75), int(h * 0.4)), (w, h), (140, 140, 140), 2)
    cv2.line(img, (int(w * 0.25), int(h * 0.4)), (int(w * 0.75), int(h * 0.4)), (120, 120, 120), 2)

    return img


def generate_all_frames():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Clear Hallway
    frame_clear = draw_base_hallway()
    cv2.imwrite(str(OUTPUT_DIR / "frame_01_clear.jpg"), frame_clear)

    # 2. Hallway with Chair Obstacle (in walking lane)
    frame_chair = draw_base_hallway()
    # Draw a chair shape in the center-lane
    # Seat
    cv2.rectangle(frame_chair, (260, 280), (380, 310), (40, 40, 160), -1)
    # Backrest
    cv2.rectangle(frame_chair, (270, 210), (370, 280), (30, 30, 130), -1)
    # Legs
    cv2.line(frame_chair, (270, 310), (265, 390), (20, 20, 80), 6)
    cv2.line(frame_chair, (370, 310), (375, 390), (20, 20, 80), 6)
    cv2.line(frame_chair, (290, 310), (288, 370), (20, 20, 80), 4)
    cv2.line(frame_chair, (350, 310), (352, 370), (20, 20, 80), 4)
    cv2.imwrite(str(OUTPUT_DIR / "frame_02_chair.jpg"), frame_chair)

    # 3. Hallway with Stairs Pattern
    frame_stairs = draw_base_hallway()
    # Draw horizontal parallel lines representing staircase risers
    for y in range(250, 440, 28):
        cv2.line(frame_stairs, (180, y), (460, y), (50, 50, 50), 3)
        cv2.line(frame_stairs, (180, y + 4), (460, y + 4), (220, 220, 220), 2)
    cv2.imwrite(str(OUTPUT_DIR / "frame_03_stairs.jpg"), frame_stairs)

    # 4. Hallway with Pothole / Ground Depression
    frame_pothole = draw_base_hallway()
    # Draw a dark ellipse in the walking lane on the floor
    cv2.ellipse(frame_pothole, (320, 380), (75, 30), 0, 0, 360, (35, 35, 40), -1)
    cv2.ellipse(frame_pothole, (320, 380), (80, 34), 0, 0, 360, (90, 90, 95), 2)
    cv2.imwrite(str(OUTPUT_DIR / "frame_04_pothole.jpg"), frame_pothole)

    # 5. Hallway with Close Wall (Dead-End)
    frame_wall = np.full((480, 640, 3), (210, 205, 200), dtype=np.uint8)
    cv2.putText(frame_wall, "DEAD END / WALL", (180, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (100, 100, 100), 2)
    cv2.imwrite(str(OUTPUT_DIR / "frame_05_wall.jpg"), frame_wall)

    print(f"Generated 5 test frames in: {OUTPUT_DIR}")


if __name__ == "__main__":
    generate_all_frames()
