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
    cv2.rectangle(frame_chair, (260, 280), (380, 310), (40, 40, 160), -1)
    cv2.rectangle(frame_chair, (270, 210), (370, 280), (30, 30, 130), -1)
    cv2.line(frame_chair, (270, 310), (265, 390), (20, 20, 80), 6)
    cv2.line(frame_chair, (370, 310), (375, 390), (20, 20, 80), 6)
    cv2.line(frame_chair, (290, 310), (288, 370), (20, 20, 80), 4)
    cv2.line(frame_chair, (350, 310), (352, 370), (20, 20, 80), 4)
    cv2.imwrite(str(OUTPUT_DIR / "frame_02_chair.jpg"), frame_chair)

    # 3. Real Staircase with Perspective Riser Heights, Sawtooth Shading & Handrails
    frame_stairs = draw_base_hallway()
    step_y = [430, 375, 330, 295, 268]
    for i in range(len(step_y) - 1):
        y_bot = step_y[i]
        y_top = step_y[i+1]
        w_step_half = int(140 - i * 15)
        x_left = 320 - w_step_half
        x_right = 320 + w_step_half
        cv2.rectangle(frame_stairs, (x_left, y_top + 16), (x_right, y_bot), (225, 225, 225), -1)
        cv2.rectangle(frame_stairs, (x_left, y_top), (x_right, y_top + 16), (70, 70, 75), -1)
        cv2.line(frame_stairs, (x_left, y_top + 16), (x_right, y_top + 16), (40, 40, 40), 2)
    cv2.line(frame_stairs, (170, 440), (260, 260), (60, 60, 60), 3)
    cv2.line(frame_stairs, (470, 440), (380, 260), (60, 60, 60), 3)
    cv2.imwrite(str(OUTPUT_DIR / "frame_03_stairs.jpg"), frame_stairs)

    # 4. Realistic Pothole with Fractured Jagged Rim & Disordered Rough Texture
    frame_pothole = draw_base_hallway()
    np.random.seed(42)
    angles = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    r_base_x, r_base_y = 75, 32
    pts = []
    for a in angles:
        noise = np.random.uniform(0.75, 1.30)
        px = int(320 + r_base_x * np.cos(a) * noise)
        py = int(380 + r_base_y * np.sin(a) * noise)
        pts.append([px, py])
    poly_pts = np.array(pts, np.int32)
    cv2.fillPoly(frame_pothole, [poly_pts], (40, 40, 45))
    noise_patch = np.random.randint(-55, 55, (80, 180, 3), dtype=np.int16)
    p_roi = frame_pothole[340:420, 230:410].astype(np.int16)
    mask_patch = np.zeros((80, 180), dtype=np.uint8)
    shifted_poly = poly_pts - np.array([230, 340])
    cv2.fillPoly(mask_patch, [shifted_poly], 255)
    p_roi[mask_patch > 0] = np.clip(p_roi[mask_patch > 0] + noise_patch[mask_patch > 0], 10, 110)
    frame_pothole[340:420, 230:410] = p_roi.astype(np.uint8)
    cv2.polylines(frame_pothole, [poly_pts], True, (110, 110, 115), 3)
    cv2.imwrite(str(OUTPUT_DIR / "frame_04_pothole.jpg"), frame_pothole)

    # 5. Hallway with Close Wall (Dead-End)
    frame_wall = np.full((480, 640, 3), (210, 205, 200), dtype=np.uint8)
    cv2.putText(frame_wall, "DEAD END / WALL", (180, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (100, 100, 100), 2)
    cv2.imwrite(str(OUTPUT_DIR / "frame_05_wall.jpg"), frame_wall)

    # 6. Flat Pavement / Paver Blocks (Constant Line Spacing, Flat Ground)
    frame_pavers = draw_base_hallway()
    for y in range(210, 470, 24):
        cv2.line(frame_pavers, (int(640 * 0.20), y), (int(640 * 0.80), y), (130, 130, 130), 1)
        for x in range(int(640 * 0.25), int(640 * 0.75), 45):
            offset_x = (x + 22) if (y // 24) % 2 == 0 else x
            cv2.line(frame_pavers, (offset_x, y), (offset_x, min(475, y + 24)), (130, 130, 130), 1)
    cv2.imwrite(str(OUTPUT_DIR / "frame_06_paver_blocks.jpg"), frame_pavers)

    # 7. Floor Shadow (Dark illumination change with smooth boundary)
    frame_shadow = draw_base_hallway()
    shadow_overlay = frame_shadow.copy()
    cv2.ellipse(shadow_overlay, (320, 380), (85, 35), 15, 0, 360, (60, 60, 60), -1)
    cv2.addWeighted(shadow_overlay, 0.40, frame_shadow, 0.60, 0, frame_shadow)
    cv2.imwrite(str(OUTPUT_DIR / "frame_07_shadow.jpg"), frame_shadow)

    # 8. Two-Wheeler (Bicycle / Motorcycle silhouette in corridor)
    frame_two_wheeler = draw_base_hallway()
    cv2.circle(frame_two_wheeler, (260, 390), 28, (30, 30, 30), 5)
    cv2.circle(frame_two_wheeler, (370, 390), 28, (30, 30, 30), 5)
    cv2.line(frame_two_wheeler, (260, 390), (310, 330), (200, 30, 30), 6)
    cv2.line(frame_two_wheeler, (370, 390), (330, 390), (200, 30, 30), 6)
    cv2.line(frame_two_wheeler, (310, 330), (330, 390), (200, 30, 30), 6)
    cv2.line(frame_two_wheeler, (310, 330), (370, 310), (200, 30, 30), 6)
    cv2.line(frame_two_wheeler, (370, 390), (370, 310), (200, 30, 30), 6)
    cv2.line(frame_two_wheeler, (360, 305), (380, 305), (50, 50, 50), 6)
    cv2.line(frame_two_wheeler, (295, 325), (325, 325), (30, 30, 30), 8)
    cv2.imwrite(str(OUTPUT_DIR / "frame_08_two_wheeler.jpg"), frame_two_wheeler)

    # 9. Four-Wheeler (Car / Shuttle across corridor)
    frame_four_wheeler = draw_base_hallway()
    cv2.rectangle(frame_four_wheeler, (180, 260), (460, 380), (30, 90, 180), -1)
    cv2.rectangle(frame_four_wheeler, (230, 210), (410, 260), (30, 90, 180), -1)
    cv2.rectangle(frame_four_wheeler, (240, 220), (400, 255), (180, 220, 240), -1)
    cv2.circle(frame_four_wheeler, (220, 385), 24, (20, 20, 20), -1)
    cv2.circle(frame_four_wheeler, (420, 385), 24, (20, 20, 20), -1)
    cv2.imwrite(str(OUTPUT_DIR / "frame_09_four_wheeler.jpg"), frame_four_wheeler)

    # 10. Large Stone / Rock / Rubble on Paver Walkway (Protruding 3D contour with ground shadow)
    frame_stone = draw_base_hallway()
    for y in range(210, 470, 24):
        cv2.line(frame_stone, (int(640 * 0.20), y), (int(640 * 0.80), y), (145, 145, 145), 1)
    cv2.ellipse(frame_stone, (330, 395), (55, 12), 0, 0, 360, (50, 50, 50), -1)
    stone_pts = np.array([[285, 390], [295, 345], [325, 325], [365, 335], [380, 375], [365, 395], [315, 400]], np.int32)
    cv2.fillPoly(frame_stone, [stone_pts], (110, 110, 115))
    cv2.ellipse(frame_stone, (330, 350), (25, 12), -10, 0, 360, (150, 150, 155), -1)
    cv2.imwrite(str(OUTPUT_DIR / "frame_10_large_stone.jpg"), frame_stone)

    # 11. Tree with Trunk AND Foliage Canopy (complete tree structure)
    frame_tree = draw_base_hallway()
    # Tree trunk (vertical cylinder)
    cv2.rectangle(frame_tree, (285, 160), (355, 390), (45, 70, 110), -1)
    for bx in range(290, 350, 8):
        for by in range(170, 380, 20):
            cv2.line(frame_tree, (bx, by), (bx + np.random.randint(-2, 3), by + 16), (25, 45, 75), 2)
    # Raised root / planter ring at base
    cv2.ellipse(frame_tree, (320, 395), (65, 18), 0, 0, 360, (80, 100, 120), 4)
    cv2.ellipse(frame_tree, (320, 395), (55, 14), 0, 0, 360, (60, 50, 40), -1)
    # Green foliage canopy on top
    cv2.ellipse(frame_tree, (320, 130), (110, 65), 0, 0, 360, (35, 130, 45), -1)
    cv2.imwrite(str(OUTPUT_DIR / "frame_11_tree_trunk.jpg"), frame_tree)

    # 12. Tree with Leaves/Canopy Only (Trunk NOT visible, low-hanging branch/foliage in walking corridor)
    frame_leaves_only = draw_base_hallway()
    # Dense green foliage cluster hanging in corridor (canopy / low branches)
    cv2.ellipse(frame_leaves_only, (320, 170), (125, 75), 0, 0, 360, (30, 135, 40), -1)
    # Add leaf texture details
    for lx in range(230, 410, 18):
        for ly in range(120, 220, 18):
            cv2.circle(frame_leaves_only, (lx + np.random.randint(-5, 6), ly + np.random.randint(-5, 6)), 9, (25, 155, 55), -1)
    cv2.imwrite(str(OUTPUT_DIR / "frame_12_tree_leaves_only.jpg"), frame_leaves_only)

    print(f"Generated 12 test frames in: {OUTPUT_DIR}")


if __name__ == "__main__":
    generate_all_frames()
