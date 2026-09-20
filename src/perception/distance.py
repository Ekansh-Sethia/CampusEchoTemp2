"""Monocular distance estimation and walking lane geometry calculations."""
from typing import Dict, Tuple


# Known real-world physical heights in meters
REFERENCE_HEIGHTS_METERS: Dict[str, float] = {
    "person": 1.70,
    "chair": 0.80,
    "couch": 0.85,
    "bench": 0.75,
    "table": 0.75,
    "dining table": 0.75,
    "backpack": 0.50,
    "suitcase": 0.65,
    "handbag": 0.35,
    "bottle": 0.30,
    "potted plant": 0.60,
    "stair": 0.90,
    "pothole": 0.30,
    "wall": 2.00,
}

DEFAULT_OBJECT_HEIGHT_METERS: float = 0.80

# Camera calibration defaults (assuming standard ~60-70 degree FOV camera)
# For 640x480 resolution, focal length f ≈ 650 pixels
DEFAULT_FOCAL_LENGTH_PX: float = 650.0


class DistanceEstimator:
    """Estimates real-world distance from monocular 2D bounding boxes and frame geometry."""

    def __init__(self, focal_length_px: float = DEFAULT_FOCAL_LENGTH_PX):
        self.focal_length_px = focal_length_px

    def estimate_distance(
        self,
        label: str,
        bbox: Tuple[int, int, int, int],
        frame_height: int,
        frame_width: int
    ) -> float:
        """
        Estimates the distance in meters to the detected object.
        Uses pinhole geometry: distance = (focal_length * real_height) / bbox_height.
        For ground hazards (like potholes), blends with ground-plane perspective projection.
        """
        xmin, ymin, xmax, ymax = bbox
        bbox_height = max(1, ymax - ymin)

        real_height = REFERENCE_HEIGHTS_METERS.get(label.lower(), DEFAULT_OBJECT_HEIGHT_METERS)

        # Scale focal length if frame height differs from 480p baseline
        scaled_focal_length = self.focal_length_px * (frame_height / 480.0)

        # 1. Pinhole model based on object height
        dist_pinhole = (scaled_focal_length * real_height) / bbox_height

        # 2. Ground-plane perspective heuristic
        # Objects touching lower in the frame are closer to the user
        bottom_norm = ymax / frame_height  # 0.0 at top, 1.0 at bottom edge
        # Floor distance approximation: closer to 1.0 -> closer to 0.5m; near 0.4 -> ~4.0m
        if bottom_norm > 0.35:
            # Quadratic distance model from ground contact point
            dist_ground = 0.8 + 4.5 * ((1.0 - bottom_norm) ** 1.8)
        else:
            dist_ground = 5.0

        # For floor hazards (pothole, bottle, bag on floor), weight ground projection higher
        if label.lower() in ("pothole", "bottle", "handbag"):
            estimated_dist = 0.7 * dist_ground + 0.3 * dist_pinhole
        elif label.lower() == "wall":
            # Walls occupy large frame areas; distance is constrained
            estimated_dist = max(0.5, min(dist_pinhole, 4.0))
        else:
            estimated_dist = 0.7 * dist_pinhole + 0.3 * dist_ground

        # Clamp between 0.3m (immediate collision) and 10.0m (far field)
        return round(float(max(0.3, min(10.0, estimated_dist))), 2)

    def evaluate_walking_lane(
        self,
        bbox: Tuple[int, int, int, int],
        frame_width: int,
        frame_height: int,
        distance_m: float,
        lane_margin_ratio: float = 0.25,
        max_hazard_distance_m: float = 3.5
    ) -> Tuple[bool, str, str]:
        """
        Determines whether the obstacle is inside the user's direct walking corridor.

        Returns:
            (in_walking_lane: bool, horizontal_position: str, urgency: str)
        """
        xmin, ymin, xmax, ymax = bbox
        center_x = (xmin + xmax) / 2.0
        bottom_y = ymax

        # Horizontal corridor: center 50% of the frame (0.25W to 0.75W)
        left_bound = frame_width * lane_margin_ratio
        right_bound = frame_width * (1.0 - lane_margin_ratio)

        # Horizontal classification
        if center_x < frame_width * 0.35:
            h_pos = "left"
        elif center_x > frame_width * 0.65:
            h_pos = "right"
        else:
            h_pos = "center"

        # Walking lane check:
        # 1. Object bounding box overlaps the corridor
        # 2. Center_x is within bounds
        # 3. Object is within collision horizon (<= 3.5m)
        overlaps_corridor = not (xmax < left_bound or xmin > right_bound)
        is_in_corridor = (left_bound <= center_x <= right_bound) or overlaps_corridor
        is_close_enough = distance_m <= max_hazard_distance_m

        in_walking_lane = bool(is_in_corridor and is_close_enough)

        # Determine urgency
        if distance_m <= 1.2 and in_walking_lane:
            urgency = "critical"
        elif distance_m <= 2.2 and in_walking_lane:
            urgency = "high"
        elif distance_m <= max_hazard_distance_m and in_walking_lane:
            urgency = "medium"
        else:
            urgency = "low"

        return in_walking_lane, h_pos, urgency
