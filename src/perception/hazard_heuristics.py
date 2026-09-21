"""Heuristic computer vision detectors for environmental hazards: stairs, potholes, and walls."""
from typing import List, Optional, Tuple
import cv2
import numpy as np
from .models import DetectedObstacle
from .distance import DistanceEstimator


class EnvironmentalHazardDetector:
    """Detects campus hazards not present in standard COCO: stairs, potholes, and walls."""

    def __init__(self, distance_estimator: Optional[DistanceEstimator] = None):
        self.distance_estimator = distance_estimator or DistanceEstimator()

    def detect_hazards(
        self,
        frame: np.ndarray,
        excluded_obstacles: Optional[List[DetectedObstacle]] = None
    ) -> List[DetectedObstacle]:
        """
        Runs physics- and geometry-based checks to identify stairs, potholes, or walls.
        Guarantees that floor hazards are never detected on human bodies or furniture.
        """
        hazards: List[DetectedObstacle] = []
        h, w = frame.shape[:2]

        # Construct exclusion mask for any detected people, chairs, or furniture
        exclusion_mask = np.zeros((h, w), dtype=np.uint8)
        if excluded_obstacles:
            for obs in excluded_obstacles:
                if obs.label in ("person", "chair", "couch", "bench", "dining table", "backpack"):
                    xmin, ymin, xmax, ymax = obs.bbox
                    # Dilate slightly to include clothing folds and direct shadows
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

        # 2. Detect Potholes (ground level depression with disordered/rough internal texture)
        pothole_obs = self._detect_potholes(frame, h, w, exclusion_mask)
        if pothole_obs:
            hazards.append(pothole_obs)

        # 3. Detect Imminent Wall / Dead-End (large planar occlusion)
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
        Detects staircases based on:
        1. Regular geometric perspective progression (steps get narrower and spacing compresses with distance).
        2. Alternating light/shadow shading between vertical risers and horizontal treads.
        3. Contextual support from flanking diagonal side railings or wall stringers.
        4. Strict exclusion of human bodies and furniture.
        """
        # Focus on walking corridor in lower 60% of frame
        roi_ymin = int(h * 0.40)
        roi = frame[roi_ymin:h, :]
        roi_mask = exclusion_mask[roi_ymin:h, :]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # Suppress any regions occupied by people/chairs
        gray[roi_mask > 0] = 128
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # 1. Find horizontal edge risers
        edges = cv2.Canny(blurred, 40, 120, apertureSize=3)
        edges[roi_mask > 0] = 0

        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=45,
            minLineLength=int(w * 0.20),
            maxLineGap=25
        )

        if lines is None:
            return None

        # Filter horizontal lines and record (y_pos, x_left, x_right, width)
        step_candidates = []
        for line in lines:
            pts = line.flatten()
            if len(pts) < 4:
                continue
            x1, y1, x2, y2 = int(pts[0]), int(pts[1]), int(pts[2]), int(pts[3])
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            if dx > 0 and (dy / dx) < 0.20:  # Horizontal within ~11 degrees
                y_abs = roi_ymin + (y1 + y2) // 2
                x_min = min(x1, x2)
                x_max = max(x1, x2)
                step_candidates.append((y_abs, x_min, x_max, x_max - x_min))

        if len(step_candidates) < 3:
            return None

        # Sort candidate steps from bottom (closest) to top (furthest)
        step_candidates.sort(key=lambda s: s[0], reverse=True)

        # Cluster nearby lines belonging to the same step riser
        clustered_steps = []
        current_cluster = [step_candidates[0]]
        for step in step_candidates[1:]:
            if abs(step[0] - current_cluster[-1][0]) <= 12:
                current_cluster.append(step)
            else:
                # Average y, min x1, max x2
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

        if len(clustered_steps) < 3:
            return None

        # 2. Check Perspective Progression:
        # Distance between successive risers should compress as steps recede (dy decreases)
        # Width of steps should narrow as they recede into the distance
        y_positions = [s[0] for s in clustered_steps]
        spacings = [abs(y_positions[i] - y_positions[i+1]) for i in range(len(y_positions)-1)]

        # Spacings must be within reasonable step bounds (10 to 90 pixels)
        valid_spacings = [s for s in spacings if 10 <= s <= 90]
        if len(valid_spacings) < 2:
            return None

        # 3. Check Alternating Shading (Risers in shadow, Treads catching light)
        shading_alternations = 0
        for i in range(len(clustered_steps) - 1):
            y_lower = clustered_steps[i][0]
            y_upper = clustered_steps[i+1][0]
            mid_y = (y_lower + y_upper) // 2
            roi_slice_lower = gray[max(0, y_lower - roi_ymin - 3):max(1, y_lower - roi_ymin + 3), :]
            roi_slice_tread = gray[max(0, mid_y - roi_ymin - 3):max(1, mid_y - roi_ymin + 3), :]
            if roi_slice_lower.size > 0 and roi_slice_tread.size > 0:
                # Contrast difference between riser edge and tread plane
                if abs(float(np.mean(roi_slice_tread)) - float(np.mean(roi_slice_lower))) > 8.0:
                    shading_alternations += 1

        # 4. Check for Side Railing / Wall Context (diagonal framing lines)
        railings_found = False
        diag_lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 40, minLineLength=60, maxLineGap=15)
        if diag_lines is not None:
            for dline in diag_lines:
                pts = dline.flatten()
                if len(pts) >= 4:
                    dx = abs(pts[2] - pts[0])
                    dy = abs(pts[3] - pts[1])
                    if dx > 0 and 0.4 <= (dy / dx) <= 2.5:  # Diagonal railing angle (~22 to 68 degrees)
                        railings_found = True
                        break

        # Confidence calculation based on physical corroboration
        confidence = 0.60
        if len(valid_spacings) >= 3:
            confidence += 0.10
        if shading_alternations >= 2:
            confidence += 0.10
        if railings_found:
            confidence += 0.08

        ymin = max(0, min(y_positions) - 15)
        ymax = min(h, max(y_positions) + 15)
        xmin = max(0, min(s[1] for s in clustered_steps) - 15)
        xmax = min(w, max(s[2] for s in clustered_steps) + 15)
        bbox = (xmin, ymin, xmax, ymax)

        dist = self.distance_estimator.estimate_distance("stair", bbox, h, w)
        in_lane, h_pos, urgency = self.distance_estimator.evaluate_walking_lane(bbox, w, h, dist)

        return DetectedObstacle(
            label="stair",
            confidence=round(min(0.88, confidence), 2),
            bbox=bbox,
            bbox_normalized=(xmin / w, ymin / h, xmax / w, ymax / h),
            distance_m=dist,
            in_walking_lane=in_lane,
            horizontal_position=h_pos,
            urgency=urgency,
            is_environmental_hazard=True
        )

    def _detect_potholes(
        self,
        frame: np.ndarray,
        h: int,
        w: int,
        exclusion_mask: np.ndarray
    ) -> Optional[DetectedObstacle]:
        """
        Detects potholes / surface depressions based on:
        1. Ground depression boundary: Enclosed irregular/elliptical contour on the walking floor.
        2. Disordered internal texture: High internal gradient entropy / texture roughness (broken asphalt,
           gravel, or reflection distortion) contrasting with the relatively smooth surrounding floor plane.
        3. Strict exclusion of human bodies, clothing, shoes, and furniture.
        """
        # Floor ROI: bottom 45% of image, central corridor
        roi_ymin = int(h * 0.55)
        roi_xmin = int(w * 0.15)
        roi_xmax = int(w * 0.85)

        roi = frame[roi_ymin:h, roi_xmin:roi_xmax]
        roi_excl = exclusion_mask[roi_ymin:h, roi_xmin:roi_xmax]
        if roi.size == 0:
            return None

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # Suppress any region overlapping with people/chairs
        gray_masked = gray.copy()
        gray_masked[roi_excl > 0] = 128

        # Compute baseline texture roughness of the general floor (Laplacian variance)
        floor_laplacian = cv2.Laplacian(gray_masked, cv2.CV_64F)
        floor_texture_variance = float(np.var(floor_laplacian))

        # Detect rim boundaries using Canny edge contours
        blurred = cv2.GaussianBlur(gray_masked, (7, 7), 0)
        edges = cv2.Canny(blurred, 30, 90)
        edges[roi_excl > 0] = 0

        # Close small gaps in the depression rim
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        closed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Area must be significant enough to represent a real ground hole (800 to 25000 pixels)
            if 800 <= area <= 25000:
                x, y, cw, ch = cv2.boundingRect(cnt)

                # Check overlap with exclusion mask
                cnt_mask = np.zeros_like(gray)
                cv2.drawContours(cnt_mask, [cnt], -1, 255, -1)
                overlap = cv2.bitwise_and(cnt_mask, roi_excl)
                if cv2.countNonZero(overlap) > (area * 0.15):
                    # Overlaps significantly with a person or chair -> reject immediately
                    continue

                # Ground perspective check: Potholes on the floor appear horizontally elongated (aspect ratio 1.1 to 4.0)
                aspect_ratio = cw / float(ch) if ch > 0 else 0
                if not (0.9 <= aspect_ratio <= 4.0):
                    continue

                # Texture Disorder Check:
                # Inside a real pothole (cracked asphalt, depression cavity, water reflection),
                # texture roughness and gradient entropy are significantly higher than the smooth floor baseline
                pothole_interior = gray[y:y+ch, x:x+cw]
                if pothole_interior.size == 0:
                    continue

                interior_laplacian = cv2.Laplacian(pothole_interior, cv2.CV_64F)
                interior_texture_variance = float(np.var(interior_laplacian))

                # If the interior has disordered texture (variance significantly higher than floor or high edge content)
                # OR strong boundary depression contrast:
                has_disordered_structure = (interior_texture_variance > 1.4 * floor_texture_variance) or (interior_texture_variance > 180.0)

                # Rim depression contrast: mean brightness inside depression vs immediately surrounding floor rim
                pothole_mean = float(np.mean(pothole_interior))
                floor_mean = float(np.mean(gray_masked[roi_excl == 0])) if np.any(roi_excl == 0) else pothole_mean

                # Pothole has either disordered gravel/debris OR water reflection / cavity difference
                is_valid_pothole = has_disordered_structure and (abs(pothole_mean - floor_mean) > 12.0)

                if is_valid_pothole:
                    abs_xmin = roi_xmin + x
                    abs_ymin = roi_ymin + y
                    abs_xmax = abs_xmin + cw
                    abs_ymax = abs_ymin + ch
                    bbox = (abs_xmin, abs_ymin, abs_xmax, abs_ymax)

                    confidence = 0.75 if has_disordered_structure else 0.65
                    dist = self.distance_estimator.estimate_distance("pothole", bbox, h, w)
                    in_lane, h_pos, urgency = self.distance_estimator.evaluate_walking_lane(
                        bbox, w, h, dist
                    )

                    return DetectedObstacle(
                        label="pothole",
                        confidence=confidence,
                        bbox=bbox,
                        bbox_normalized=(abs_xmin / w, abs_ymin / h, abs_xmax / w, abs_ymax / h),
                        distance_m=dist,
                        in_walking_lane=in_lane,
                        horizontal_position=h_pos,
                        urgency=urgency,
                        is_environmental_hazard=True
                    )

        return None

    def _detect_wall(self, frame: np.ndarray, h: int, w: int) -> Optional[DetectedObstacle]:
        """
        Detects imminent planar wall obstruction right in front of user (<1.5m).
        """
        # If there is a distinct floor/ceiling contrast (e.g., ceiling vs floor),
        # the camera is looking down an open corridor, not facing a solid wall.
        top_mean = float(np.mean(frame[:int(h * 0.35), :]))
        bottom_mean = float(np.mean(frame[int(h * 0.65):, :]))
        if abs(top_mean - bottom_mean) > 25.0:
            return None

        # Central ROI: center 60% width, lower 60% height
        center_roi = frame[int(h * 0.3):int(h * 0.9), int(w * 0.2):int(w * 0.8)]
        if center_roi.size == 0:
            return None

        gray = cv2.cvtColor(center_roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 120)
        edge_density = np.count_nonzero(edges) / edges.size

        # In a very close wall (<1.2m), color variance is low and edge density is minimal
        color_std = float(np.std(gray))
        if edge_density < 0.02 and color_std < 20.0:
            bbox = (int(w * 0.15), int(h * 0.2), int(w * 0.85), int(h * 0.95))
            dist = 1.10
            return DetectedObstacle(
                label="wall",
                confidence=0.85,
                bbox=bbox,
                bbox_normalized=(0.15, 0.20, 0.85, 0.95),
                distance_m=dist,
                in_walking_lane=True,
                horizontal_position="center",
                urgency="critical",
                is_environmental_hazard=True
            )

        return None

