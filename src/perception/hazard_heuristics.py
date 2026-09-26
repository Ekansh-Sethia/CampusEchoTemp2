"""Heuristic computer vision detectors for campus environmental hazards:
stairs, potholes, walls, large stones/rubble, trees (via leaf/foliage density and trunk),
and architectural pillars/gates.
"""
from typing import List, Optional, Tuple
import cv2
import numpy as np
from .models import DetectedObstacle
from .distance import DistanceEstimator
from .shadow_filter import ShadowLightAnalyzer


class EnvironmentalHazardDetector:
    """
    Detects campus hazards not covered or under-represented in standard COCO:
    stairs, potholes, walls, large stones/rubble, trees (foliage + trunk),
    and architectural pillars/gates.
    """

    def __init__(
        self,
        distance_estimator: Optional[DistanceEstimator] = None,
        shadow_analyzer: Optional[ShadowLightAnalyzer] = None
    ):
        self.distance_estimator = distance_estimator or DistanceEstimator()
        self.shadow_analyzer = shadow_analyzer or ShadowLightAnalyzer()

    def detect_hazards(
        self,
        frame: np.ndarray,
        excluded_obstacles: Optional[List[DetectedObstacle]] = None
    ) -> List[DetectedObstacle]:
        """
        Runs physics- and geometry-based checks to identify environmental obstacles.
        Guarantees that floor hazards are never detected on human bodies or vehicles.
        """
        hazards: List[DetectedObstacle] = []
        h, w = frame.shape[:2]

        # Construct exclusion mask for detected people, furniture, and vehicles
        exclusion_mask = np.zeros((h, w), dtype=np.uint8)
        if excluded_obstacles:
            for obs in excluded_obstacles:
                if obs.label in (
                    "person", "chair", "couch", "bench", "dining table", "backpack",
                    "two_wheeler", "four_wheeler", "bicycle", "motorcycle", "car", "bus", "truck"
                ):
                    xmin, ymin, xmax, ymax = obs.bbox
                    pad_x = int((xmax - xmin) * 0.08)
                    pad_y = int((ymax - ymin) * 0.08)
                    x1 = max(0, xmin - pad_x)
                    y1 = max(0, ymin - pad_y)
                    x2 = min(w, xmax + pad_x)
                    y2 = min(h, ymax + pad_y)
                    cv2.rectangle(exclusion_mask, (x1, y1), (x2, y2), 255, -1)

        # 1. Detect Stairs (perspective step progression, riser/tread shading, side railings)
        stair_obs = self._detect_stairs(frame, h, w, exclusion_mask)
        if stair_obs:
            hazards.append(stair_obs)
            sx1, sy1, sx2, sy2 = stair_obs.bbox
            cv2.rectangle(exclusion_mask, (sx1, sy1), (sx2, sy2), 255, -1)

        # 2. Detect Trees (via leaf/foliage density and/or trunk structure)
        tree_obs = self._detect_trees(frame, h, w, exclusion_mask)
        if tree_obs:
            hazards.extend(tree_obs)
            for tr in tree_obs:
                tx1, ty1, tx2, ty2 = tr.bbox
                cv2.rectangle(exclusion_mask, (tx1, ty1), (tx2, ty2), 255, -1)

        # 3. Detect Architectural Pillars / Columns in corridor
        pillar_obs = self._detect_pillars(frame, h, w, exclusion_mask)
        if pillar_obs:
            hazards.extend(pillar_obs)
            for pl in pillar_obs:
                px1, py1, px2, py2 = pl.bbox
                cv2.rectangle(exclusion_mask, (px1, py1), (px2, py2), 255, -1)

        # 4. Detect Potholes (ground level depression with disordered/rough internal texture)
        pothole_obs = self._detect_potholes(frame, h, w, exclusion_mask)
        if pothole_obs:
            hazards.append(pothole_obs)
            px1, py1, px2, py2 = pothole_obs.bbox
            cv2.rectangle(exclusion_mask, (px1, py1), (px2, py2), 255, -1)

        # 5. Detect Large Stones / Rock / Rubble (isolated 3D protrusion vs flat paver blocks)
        stone_obs = self._detect_stones(frame, h, w, exclusion_mask)
        if stone_obs:
            hazards.extend(stone_obs)
            for st in stone_obs:
                stx1, sty1, stx2, sty2 = st.bbox
                cv2.rectangle(exclusion_mask, (stx1, sty1), (stx2, sty2), 255, -1)

        # 6. Detect Imminent Wall / Dead-End (large planar occlusion)
        wall_obs = self._detect_wall(frame, h, w)
        if wall_obs:
            hazards.append(wall_obs)

        return hazards

    def _detect_stairs(
        self,
        frame: np.ndarray,
        h: int,
        w: int,
        exclusion_mask: np.ndarray
    ) -> Optional[DetectedObstacle]:
        """
        Detects real staircases while strictly rejecting flat pavements, paver blocks, and floor tiles.
        """
        roi_ymin = int(h * 0.40)
        roi = frame[roi_ymin:h, :]
        roi_mask = exclusion_mask[roi_ymin:h, :]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray[roi_mask > 0] = 128
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        edges = cv2.Canny(blurred, 50, 140, apertureSize=3)
        edges[roi_mask > 0] = 0

        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=55,
            minLineLength=int(w * 0.22),
            maxLineGap=20
        )

        if lines is None:
            return None

        horizontal_lines = []
        for line in lines:
            pts = line.flatten()
            if len(pts) < 4:
                continue
            x1, y1, x2, y2 = int(pts[0]), int(pts[1]), int(pts[2]), int(pts[3])
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            if dx > 0 and (dy / dx) < 0.15:
                y_abs = roi_ymin + (y1 + y2) // 2
                x_min = min(x1, x2)
                x_max = max(x1, x2)
                horizontal_lines.append((y_abs, x_min, x_max, x_max - x_min))

        if len(horizontal_lines) < 4:   # Was 3 — require ≥4 distinct step edges
            return None

        horizontal_lines.sort(key=lambda s: s[0], reverse=True)

        clustered_steps = []
        current_cluster = [horizontal_lines[0]]
        for step in horizontal_lines[1:]:
            if abs(step[0] - current_cluster[-1][0]) <= 10:
                current_cluster.append(step)
            else:
                avg_y = int(np.mean([s[0] for s in current_cluster]))
                min_x = min(s[1] for s in current_cluster)
                max_x = max(s[2] for s in current_cluster)
                clustered_steps.append((avg_y, min_x, max_x, max_x - min_x))
                current_cluster = [step]

        if current_cluster:
            avg_y = int(np.mean([s[0] for s in current_cluster]))
            min_x = min(s[1] for s in current_cluster)
            max_x = max(s[2] for s in current_cluster)
            clustered_steps.append((avg_y, min_x, max_x, max_x - min_x))

        if len(clustered_steps) < 4:   # Was 3 — four distinct risers minimum
            return None

        y_positions = [s[0] for s in clustered_steps]
        spacings = [abs(y_positions[i] - y_positions[i+1]) for i in range(len(y_positions)-1)]

        mean_spacing = float(np.mean(spacings))
        std_spacing = float(np.std(spacings))

        # Rejection: Constant Spacing Check (Paver blocks / flat tile seams)
        # Raised mean_spacing threshold to 20 px — a realistic step height viewed at ≤6m
        if mean_spacing < 20 or (std_spacing / (mean_spacing + 1e-5)) < 0.15:
            return None

        # Rejection: Sawtooth Shading Check
        sawtooth_transitions = 0
        for i in range(len(clustered_steps) - 1):
            y_lower = clustered_steps[i][0] - roi_ymin
            y_upper = clustered_steps[i+1][0] - roi_ymin
            mid_y = (y_lower + y_upper) // 2

            riser_band = gray[max(0, y_lower - 4):min(gray.shape[0], y_lower + 4), :]
            tread_plane = gray[max(0, mid_y - 4):min(gray.shape[0], mid_y + 4), :]

            if riser_band.size > 0 and tread_plane.size > 0:
                contrast = abs(float(np.mean(tread_plane)) - float(np.mean(riser_band)))
                if contrast >= 20.0:   # Was 14 — real risers cast noticeably stronger shade
                    sawtooth_transitions += 1

        if sawtooth_transitions < 3:   # Was 2 — demand at least 3 strong riser/tread transitions
            return None

        railings_found = False
        diag_lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 45, minLineLength=50, maxLineGap=15)
        if diag_lines is not None:
            for dline in diag_lines:
                pts = dline.flatten()
                if len(pts) >= 4:
                    dx = abs(pts[2] - pts[0])
                    dy = abs(pts[3] - pts[1])
                    if dx > 0 and 0.35 <= (dy / dx) <= 2.2:
                        railings_found = True
                        break

        confidence = 0.65
        if sawtooth_transitions >= 3:
            confidence += 0.10
        if railings_found:
            confidence += 0.10
        if std_spacing / mean_spacing >= 0.25:
            confidence += 0.05

        ymin = max(0, min(y_positions) - 15)
        ymax = min(h, max(y_positions) + 15)
        xmin = max(0, min(s[1] for s in clustered_steps) - 15)
        xmax = min(w, max(s[2] for s in clustered_steps) + 15)
        bbox = (xmin, ymin, xmax, ymax)

        dist = self.distance_estimator.estimate_distance("stair", bbox, h, w)
        in_lane, h_pos, urgency = self.distance_estimator.evaluate_walking_lane(bbox, w, h, dist)

        raw_conf = round(min(0.88, confidence), 2)
        shd_score, cal_conf = self.shadow_analyzer.analyze_obstacle(
            frame, bbox, "stair", raw_conf
        )
        if shd_score >= 0.60:   # Was 0.75 — also catch hue-shifted pavement shadows
            return None

        return DetectedObstacle(
            label="stair",
            confidence=cal_conf,
            raw_confidence=raw_conf,
            shadow_likelihood=shd_score,
            bbox=bbox,
            bbox_normalized=(xmin / w, ymin / h, xmax / w, ymax / h),
            distance_m=dist,
            in_walking_lane=in_lane,
            horizontal_position=h_pos,
            urgency=urgency,
            is_environmental_hazard=True,
            detection_source="heuristic"
        )

    def _detect_trees(
        self,
        frame: np.ndarray,
        h: int,
        w: int,
        exclusion_mask: np.ndarray
    ) -> List[DetectedObstacle]:
        """
        Detects trees through:
          1. Leaf / Foliage Density: Even if the trunk is not visible, leaves/canopy/branches
             are detected based on HSV foliage colors (green/olive/yellow-green) and dense texture.
          2. Vertical Trunk: Cylindrical trunk with bark texture and ground root ring.
          3. Unified Tree: Merges foliage and trunk when both are visible into a single obstacle.
          4. Effective radius: Adds +0.3m padding for root zones and low-hanging branches.
        """
        trees: List[DetectedObstacle] = []

        # 1. Detect Leaf / Foliage Density Clusters
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        # Tighter saturation (55) and value (50) floors reduce false-positives from:
        # yellowed grass, washed-out signage, and pale reflections.
        lower_green = np.array([32, 55, 50])
        upper_green = np.array([85, 255, 255])
        green_mask = cv2.inRange(hsv, lower_green, upper_green)
        green_mask[exclusion_mask > 0] = 0

        # Cluster foliage leaves into connected canopies / branches
        f_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        foliage_clustered = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, f_kernel)
        contours_f, _ = cv2.findContours(foliage_clustered, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        foliage_boxes: List[Tuple[int, int, int, int]] = []
        for cnt in contours_f:
            area = cv2.contourArea(cnt)
            if area >= 2500:   # Was 1800 — filter smaller specular/noise blobs
                x, y, cw, ch = cv2.boundingRect(cnt)
                # Leaves/canopy/branches are elevated (not flat on floor) and span walking corridor
                if y < int(h * 0.65) and (x + cw) > w * 0.15 and x < w * 0.85:
                    foliage_boxes.append((x, y, x + cw, y + ch))

        # 2. Detect Vertical Trunk / Column in path corridor
        roi_xmin = int(w * 0.15)
        roi_xmax = int(w * 0.85)
        roi_ymin = int(h * 0.20)
        roi_ymax = int(h * 0.90)

        roi = frame[roi_ymin:roi_ymax, roi_xmin:roi_xmax]
        roi_excl = exclusion_mask[roi_ymin:roi_ymax, roi_xmin:roi_xmax]

        trunk_boxes: List[Tuple[int, int, int, int]] = []
        if roi.size > 0:
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            gray[roi_excl > 0] = 128
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            sobel_x = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=3)
            sobel_abs = np.uint8(np.absolute(sobel_x))
            _, thresh = cv2.threshold(sobel_abs, 45, 255, cv2.THRESH_BINARY)
            thresh[roi_excl > 0] = 0

            v_closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 21)))
            col_closed = cv2.morphologyEx(v_closed, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1)))

            contours_t, _ = cv2.findContours(col_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours_t:
                x, y, cw, ch = cv2.boundingRect(cnt)
                if ch >= int(h * 0.30) and cw >= int(w * 0.04) and (ch / max(1, cw)) >= 1.3:
                    if x > 10 and (x + cw) < (roi_xmax - roi_xmin - 10):
                        # Verify bark texture / roughness
                        col_roi = gray[y:y+ch, x:x+cw]
                        laplacian_var = float(np.var(cv2.Laplacian(col_roi, cv2.CV_64F)))
                        if laplacian_var >= 130.0:  # Textured bark
                            trunk_boxes.append((roi_xmin + x, roi_ymin + y, roi_xmin + x + cw, roi_ymin + y + ch))

        # 3. Unified Assembly: Merge foliage and trunk, or process each individually
        tree_regions: List[Tuple[int, int, int, int, Optional[int]]] = []  # (xmin, ymin, xmax, ymax, ground_y)
        used_trunks = set()

        for fx1, fy1, fx2, fy2 in foliage_boxes:
            merged = False
            for tidx, (tx1, ty1, tx2, ty2) in enumerate(trunk_boxes):
                # Check horizontal overlap and vertical proximity (foliage above/overlapping trunk)
                h_overlap = max(0, min(fx2, tx2) - max(fx1, tx1))
                if h_overlap > 20 and fy2 >= (ty1 - 40):
                    mx1 = min(fx1, tx1)
                    my1 = min(fy1, ty1)
                    mx2 = max(fx2, tx2)
                    my2 = max(fy2, ty2)
                    tree_regions.append((mx1, my1, mx2, my2, my2))
                    used_trunks.add(tidx)
                    merged = True
                    break
            if not merged:
                # Foliage-only tree detection (e.g. canopy or low-hanging branches in corridor)
                tree_regions.append((fx1, fy1, fx2, fy2, fy2))

        for tidx, (tx1, ty1, tx2, ty2) in enumerate(trunk_boxes):
            if tidx not in used_trunks:
                # Check if already covered by an existing tree region
                already_covered = any(
                    (rx1 <= tx1 and rx2 >= tx2 and ry1 <= ty1 and ry2 >= ty2)
                    for rx1, ry1, rx2, ry2, _ in tree_regions
                )
                if not already_covered:
                    tree_regions.append((tx1, ty1, tx2, ty2, ty2))

        # Convert tree regions to DetectedObstacle instances
        for xmin, ymin, xmax, ymax, ground_y in tree_regions:
            bbox = (xmin, ymin, xmax, ymax)
            effective_radius = 0.30  # +0.3m padding for root zone / branch overhang

            dist = self.distance_estimator.estimate_distance("tree", bbox, h, w, contact_y=ground_y)
            in_lane, h_pos, urgency = self.distance_estimator.evaluate_walking_lane(
                bbox, w, h, dist, effective_radius_m=effective_radius
            )

            trees.append(DetectedObstacle(
                label="tree",
                confidence=0.75,
                bbox=bbox,
                bbox_normalized=(xmin / w, ymin / h, xmax / w, ymax / h),
                distance_m=dist,
                in_walking_lane=in_lane,
                horizontal_position=h_pos,
                urgency=urgency,
                is_environmental_hazard=True,
                effective_radius_m=effective_radius,
                detection_source="heuristic",
                ground_contact_y=ground_y
            ))

        return trees

    def _detect_pillars(
        self,
        frame: np.ndarray,
        h: int,
        w: int,
        exclusion_mask: np.ndarray
    ) -> List[DetectedObstacle]:
        """
        Detects smooth architectural columns / pillars standing inside the corridor.
        """
        pillars: List[DetectedObstacle] = []
        roi_xmin = int(w * 0.15)
        roi_xmax = int(w * 0.85)
        roi_ymin = int(h * 0.20)
        roi_ymax = int(h * 0.90)

        roi = frame[roi_ymin:roi_ymax, roi_xmin:roi_xmax]
        roi_excl = exclusion_mask[roi_ymin:roi_ymax, roi_xmin:roi_xmax]
        if roi.size == 0:
            return pillars

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray[roi_excl > 0] = 128
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        sobel_x = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=3)
        sobel_abs = np.uint8(np.absolute(sobel_x))
        _, thresh = cv2.threshold(sobel_abs, 45, 255, cv2.THRESH_BINARY)
        thresh[roi_excl > 0] = 0

        v_closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 21)))
        col_closed = cv2.morphologyEx(v_closed, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1)))

        contours, _ = cv2.findContours(col_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if ch >= int(h * 0.35) and cw >= int(w * 0.05) and (ch / max(1, cw)) >= 1.5:
                if x <= 10 or (x + cw) >= (roi_xmax - roi_xmin - 10):
                    continue

                col_roi = gray[y:y+ch, x:x+cw]
                laplacian_var = float(np.var(cv2.Laplacian(col_roi, cv2.CV_64F)))
                # Pillars have smooth surfaces (low laplacian variance), unlike tree bark
                if laplacian_var < 130.0:
                    abs_xmin = roi_xmin + x
                    abs_ymin = roi_ymin + y
                    abs_xmax = roi_xmin + x + cw
                    abs_ymax = roi_ymin + y + ch
                    bbox = (abs_xmin, abs_ymin, abs_xmax, abs_ymax)

                    dist = self.distance_estimator.estimate_distance("pillar", bbox, h, w, contact_y=abs_ymax)
                    in_lane, h_pos, urgency = self.distance_estimator.evaluate_walking_lane(
                        bbox, w, h, dist
                    )

                    pillars.append(DetectedObstacle(
                        label="pillar",
                        confidence=0.78,
                        bbox=bbox,
                        bbox_normalized=(abs_xmin / w, abs_ymin / h, abs_xmax / w, abs_ymax / h),
                        distance_m=dist,
                        in_walking_lane=in_lane,
                        horizontal_position=h_pos,
                        urgency=urgency,
                        is_environmental_hazard=True,
                        detection_source="heuristic",
                        ground_contact_y=abs_ymax
                    ))

        return pillars

    def _detect_potholes(
        self,
        frame: np.ndarray,
        h: int,
        w: int,
        exclusion_mask: np.ndarray
    ) -> Optional[DetectedObstacle]:
        """
        Detects real potholes and surface depressions while strictly rejecting flat shadows.
        """
        roi_ymin = int(h * 0.55)
        roi_xmin = int(w * 0.15)
        roi_xmax = int(w * 0.85)

        roi = frame[roi_ymin:h, roi_xmin:roi_xmax]
        roi_excl = exclusion_mask[roi_ymin:h, roi_xmin:roi_xmax]
        if roi.size == 0:
            return None

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray_masked = gray.copy()
        gray_masked[roi_excl > 0] = 128

        floor_pixels = gray_masked[roi_excl == 0]
        if floor_pixels.size < 500:
            return None

        floor_laplacian = cv2.Laplacian(gray_masked, cv2.CV_64F)
        valid_floor_mask = (roi_excl == 0)
        floor_roughness = float(np.var(floor_laplacian[valid_floor_mask])) if np.any(valid_floor_mask) else 50.0
        floor_roughness = max(10.0, floor_roughness)

        blurred = cv2.GaussianBlur(gray_masked, (7, 7), 0)
        edges = cv2.Canny(blurred, 35, 100)
        edges[roi_excl > 0] = 0

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        closed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 800 <= area <= 25000:
                perimeter = cv2.arcLength(cnt, True)
                if perimeter == 0:
                    continue

                rim_roughness = (perimeter * perimeter) / (4.0 * np.pi * area)
                if rim_roughness < 1.6:
                    continue

                x, y, cw, ch = cv2.boundingRect(cnt)
                cnt_mask = np.zeros_like(gray)
                cv2.drawContours(cnt_mask, [cnt], -1, 255, -1)
                overlap = cv2.bitwise_and(cnt_mask, roi_excl)
                if cv2.countNonZero(overlap) > (area * 0.10):
                    continue

                pothole_interior = gray[y:y+ch, x:x+cw]
                pothole_mask_interior = cnt_mask[y:y+ch, x:x+cw]
                if pothole_interior.size == 0 or cv2.countNonZero(pothole_mask_interior) < 100:
                    continue

                interior_laplacian = cv2.Laplacian(pothole_interior, cv2.CV_64F)
                interior_roughness = float(np.var(interior_laplacian[pothole_mask_interior > 0]))
                distortion_ratio = interior_roughness / floor_roughness

                if distortion_ratio < 2.0:
                    continue

                aspect_ratio = cw / float(ch) if ch > 0 else 0
                if not (0.85 <= aspect_ratio <= 3.8):
                    continue

                abs_xmin = roi_xmin + x
                abs_ymin = roi_ymin + y
                abs_xmax = abs_xmin + cw
                abs_ymax = abs_ymin + ch
                bbox = (abs_xmin, abs_ymin, abs_xmax, abs_ymax)

                raw_conf = round(min(0.85, 0.65 + 0.05 * min(4.0, distortion_ratio)), 2)
                shd_score, cal_conf = self.shadow_analyzer.analyze_obstacle(
                    frame, bbox, "pothole", raw_conf
                )

                if shd_score >= 0.75:
                    continue

                dist = self.distance_estimator.estimate_distance("pothole", bbox, h, w)
                in_lane, h_pos, urgency = self.distance_estimator.evaluate_walking_lane(
                    bbox, w, h, dist
                )

                if shd_score >= 0.40 and urgency == "critical":
                    urgency = "high"

                return DetectedObstacle(
                    label="pothole",
                    confidence=cal_conf,
                    raw_confidence=raw_conf,
                    shadow_likelihood=shd_score,
                    bbox=bbox,
                    bbox_normalized=(abs_xmin / w, abs_ymin / h, abs_xmax / w, abs_ymax / h),
                    distance_m=dist,
                    in_walking_lane=in_lane,
                    horizontal_position=h_pos,
                    urgency=urgency,
                    is_environmental_hazard=True,
                    detection_source="heuristic"
                )

        return None

    def _detect_stones(
        self,
        frame: np.ndarray,
        h: int,
        w: int,
        exclusion_mask: np.ndarray
    ) -> List[DetectedObstacle]:
        """
        Detects large stones, rocks, and rubble resting on the walking ground.
        STRICTLY differentiates stones from flat paver blocks:
          - Paver blocks have flat periodic joints with no vertical height.
          - Stones have:
            1. Isolated 3D protrusion contrasting against the floor.
            2. Distinct 3D crown shading: upper crown catches overhead light, lower band is in shadow (shading >= 15).
            3. Compact aspect ratio (0.5 to 2.4).
        """
        stones: List[DetectedObstacle] = []
        roi_ymin = int(h * 0.45)
        roi_xmin = int(w * 0.15)
        roi_xmax = int(w * 0.85)

        roi = frame[roi_ymin:h, roi_xmin:roi_xmax]
        roi_excl = exclusion_mask[roi_ymin:h, roi_xmin:roi_xmax]
        if roi.size == 0:
            return stones

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray_masked = gray.copy()
        gray_masked[roi_excl > 0] = 180

        floor_median = np.median(gray_masked[roi_excl == 0]) if np.any(roi_excl == 0) else 180.0

        # Contrast against floor plane
        diff = cv2.absdiff(gray_masked, int(floor_median))
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        thresh[roi_excl > 0] = 0

        # Morphological open to completely eliminate thin 1-2px paver lines
        clean = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
        clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))

        contours, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 500 <= area <= 18000:
                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect_ratio = cw / float(ch) if ch > 0 else 0

                if not (0.5 <= aspect_ratio <= 2.4):
                    continue

                obj_roi = gray[y:y+ch, x:x+cw]
                top_band = obj_roi[:max(1, ch // 3), :]
                bot_band = obj_roi[max(1, 2 * ch // 3):, :]
                if top_band.size == 0 or bot_band.size == 0:
                    continue

                # 3D Crown Shading: Stone catches overhead light on top, dark at base
                shading_contrast = float(np.mean(top_band)) - float(np.mean(bot_band))

                if shading_contrast < 15.0:
                    continue

                abs_xmin = roi_xmin + x
                abs_ymin = roi_ymin + y
                abs_xmax = abs_xmin + cw
                abs_ymax = abs_ymin + ch
                bbox = (abs_xmin, abs_ymin, abs_xmax, abs_ymax)

                raw_conf = 0.72
                shd_score, cal_conf = self.shadow_analyzer.analyze_obstacle(
                    frame, bbox, "stone", raw_conf
                )

                # Suppress if heavily flagged as dappled canopy light / flat shadow
                if shd_score >= 0.65:
                    continue

                dist = self.distance_estimator.estimate_distance("stone", bbox, h, w, contact_y=abs_ymax)
                in_lane, h_pos, urgency = self.distance_estimator.evaluate_walking_lane(
                    bbox, w, h, dist
                )

                if shd_score >= 0.40 and urgency == "critical":
                    urgency = "high"

                stones.append(DetectedObstacle(
                    label="stone",
                    confidence=cal_conf,
                    raw_confidence=raw_conf,
                    shadow_likelihood=shd_score,
                    bbox=bbox,
                    bbox_normalized=(abs_xmin / w, abs_ymin / h, abs_xmax / w, abs_ymax / h),
                    distance_m=dist,
                    in_walking_lane=in_lane,
                    horizontal_position=h_pos,
                    urgency=urgency,
                    is_environmental_hazard=True,
                    detection_source="heuristic",
                    ground_contact_y=abs_ymax
                ))

        return stones

    def _detect_wall(self, frame: np.ndarray, h: int, w: int) -> Optional[DetectedObstacle]:
        """
        Detects imminent planar wall obstruction right in front of user (<1.5m).

        Guard rails added to reduce false positives on outdoor campus scenes:
          1. Sky-fraction check: if the top 30% of the frame is bright (>170 mean value),
             the scene is outdoors with visible sky -> no wall close in front.
          2. Top-vs-bottom brightness: walls cause top/bottom to look similar.
          3. Tightened edge density and color std thresholds.
          4. Confidence set to 0.75 (below emergency-override zone) so the 2-second
             temporal stability check in detector.py applies and prevents
             a single noisy frame from triggering a wall alert.
        """
        # Guard 1: Sky detection (outdoor scene with open view ahead — no imminent wall).
        # True sky: high Value AND blue/cyan hue (H 85–130 in OpenCV's 0-180 scale)
        # AND meaningful saturation (sky has S ≥ 25; light-gray walls are achromatic, S < 15).
        # Indoor walls: neutral gray/warm gray — high V but very low saturation, no blue hue.
        top_strip = frame[:int(h * 0.30), :]
        top_hsv = cv2.cvtColor(top_strip, cv2.COLOR_BGR2HSV)
        top_v = top_hsv[:, :, 2]
        top_s = top_hsv[:, :, 1]
        top_h = top_hsv[:, :, 0]
        bright_mask = top_v > 140
        if bright_mask.sum() > 0:
            h_bright = top_h[bright_mask]
            s_bright = top_s[bright_mask]
            sky_hue_fraction = float(np.mean((h_bright >= 85) & (h_bright <= 130)))
            mean_s_bright = float(np.mean(s_bright))
            # Require both sky hue AND meaningful saturation (S ≥ 25).
            # Walls are achromatic (S < 15) even if they have a slight hue bias.
            is_sky = (
                mean_s_bright >= 25.0 and
                ((sky_hue_fraction >= 0.30) or (sky_hue_fraction >= 0.15 and mean_s_bright >= 40))
            )
            if is_sky:
                return None   # Outdoor sky visible — no imminent wall

        top_mean = float(np.mean(frame[:int(h * 0.35), :]))
        bottom_mean = float(np.mean(frame[int(h * 0.65):, :]))
        if abs(top_mean - bottom_mean) > 25.0:
            return None

        center_roi = frame[int(h * 0.3):int(h * 0.9), int(w * 0.2):int(w * 0.8)]
        if center_roi.size == 0:
            return None

        gray = cv2.cvtColor(center_roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 120)
        edge_density = np.count_nonzero(edges) / edges.size

        color_std = float(np.std(gray))
        # Tightened: edge_density < 0.015 (was 0.02) and color_std < 16.0 (was 20.0)
        if edge_density < 0.015 and color_std < 16.0:
            bbox = (int(w * 0.15), int(h * 0.2), int(w * 0.85), int(h * 0.95))
            dist = 1.10
            # Confidence 0.75: below emergency-override threshold (1.5m), so this
            # obstacle still goes through the 2-second temporal stability check in detector.py.
            return DetectedObstacle(
                label="wall",
                confidence=0.75,
                bbox=bbox,
                bbox_normalized=(0.15, 0.20, 0.85, 0.95),
                distance_m=dist,
                in_walking_lane=True,
                horizontal_position="center",
                urgency="critical",
                is_environmental_hazard=True,
                detection_source="heuristic"
            )

        return None
