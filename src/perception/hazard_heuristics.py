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

    def detect_hazards(self, frame: np.ndarray) -> List[DetectedObstacle]:
        """Runs heuristic checks on the frame to identify stairs, potholes, or walls."""
        hazards: List[DetectedObstacle] = []
        h, w = frame.shape[:2]

        # 1. Detect Stairs (horizontal edge patterns in walking lane)
        stair_obs = self._detect_stairs(frame, h, w)
        if stair_obs:
            hazards.append(stair_obs)

        # 2. Detect Potholes (dark depressions on the walking surface)
        pothole_obs = self._detect_potholes(frame, h, w)
        if pothole_obs:
            hazards.append(pothole_obs)

        # 3. Detect Imminent Wall / Dead-End (large planar occlusion)
        wall_obs = self._detect_wall(frame, h, w)
        if wall_obs:
            hazards.append(wall_obs)

        return hazards

    def _detect_stairs(self, frame: np.ndarray, h: int, w: int) -> Optional[DetectedObstacle]:
        """
        Detects staircase risers by analyzing parallel horizontal line patterns
        in the lower half of the frame.
        """
        # Focus on lower 60% of the image (walking surface)
        roi_ymin = int(h * 0.40)
        roi = frame[roi_ymin:h, :]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Detect strong horizontal edges using Sobel Y
        edges = cv2.Canny(blurred, 50, 150, apertureSize=3)

        # HoughLinesP to find horizontal segments
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=50,
            minLineLength=int(w * 0.25),
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
            # Horizontal filter: angle within ~15 degrees
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            if dx > 0 and (dy / dx) < 0.25:
                # Store absolute y position in original frame
                horizontal_lines.append(roi_ymin + (y1 + y2) // 2)

        if len(horizontal_lines) >= 4:
            # Check for vertical spacing between steps
            horizontal_lines.sort()
            diffs = np.diff(horizontal_lines)
            # Valid step risers should have consistent spacing (e.g. 10-60 pixels apart)
            valid_spacings = [d for d in diffs if 8 <= d <= 80]

            if len(valid_spacings) >= 3:
                ymin = max(0, min(horizontal_lines) - 20)
                ymax = min(h, max(horizontal_lines) + 20)
                xmin = int(w * 0.20)
                xmax = int(w * 0.80)
                bbox = (xmin, ymin, xmax, ymax)

                confidence = min(0.85, 0.50 + 0.05 * len(valid_spacings))
                dist = self.distance_estimator.estimate_distance("stair", bbox, h, w)
                in_lane, h_pos, urgency = self.distance_estimator.evaluate_walking_lane(
                    bbox, w, h, dist
                )

                return DetectedObstacle(
                    label="stair",
                    confidence=round(confidence, 2),
                    bbox=bbox,
                    bbox_normalized=(xmin / w, ymin / h, xmax / w, ymax / h),
                    distance_m=dist,
                    in_walking_lane=in_lane,
                    horizontal_position=h_pos,
                    urgency=urgency,
                    is_environmental_hazard=True
                )

        return None

    def _detect_potholes(self, frame: np.ndarray, h: int, w: int) -> Optional[DetectedObstacle]:
        """
        Detects dark depressions or potholes on the walking floor.
        """
        # Floor ROI: bottom 45%
        roi_ymin = int(h * 0.55)
        roi = frame[roi_ymin:h, int(w * 0.20):int(w * 0.80)]
        if roi.size == 0:
            return None

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)

        # Threshold dark regions compared to floor mean
        mean_val = np.mean(blurred)
        _, dark_mask = cv2.threshold(blurred, int(mean_val * 0.65), 255, cv2.THRESH_BINARY_INV)

        contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Area must be significant enough to represent a hole (not just pebbles)
            if 800 <= area <= 20000:
                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect_ratio = cw / float(ch) if ch > 0 else 0
                # Potholes viewed from perspective are horizontally elliptical (aspect ratio 1.1 to 3.5)
                if 0.8 <= aspect_ratio <= 4.0:
                    abs_xmin = int(w * 0.20) + x
                    abs_ymin = roi_ymin + y
                    abs_xmax = abs_xmin + cw
                    abs_ymax = abs_ymin + ch
                    bbox = (abs_xmin, abs_ymin, abs_xmax, abs_ymax)

                    confidence = 0.72
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
