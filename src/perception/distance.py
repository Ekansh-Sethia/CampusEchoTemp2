import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "reference_dimensions.json"


def load_reference_dimensions() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


REFERENCE_DIMENSIONS = load_reference_dimensions()
DEFAULT_FOCAL_LENGTH_PX: float = 650.0


class DistanceEstimator:
    """
    Estimates real-world distance from monocular 2D bounding boxes and frame geometry.
    Uses the optimal geometric dimension per class:
      - width: for wide/flat objects (four-wheelers, pillars, gates, tree trunks)
      - height: for upright objects (persons, chairs, stairs)
      - ground_contact: for low/irregular objects (stones, potholes, 2-wheelers, unidentified)
    Falls back to ground-plane projection when height/width is unreliable or cropped.
    """

    def __init__(self, focal_length_px: float = DEFAULT_FOCAL_LENGTH_PX):
        self.focal_length_px = focal_length_px
        self.dimensions = REFERENCE_DIMENSIONS

    def _get_class_config(self, label: str) -> Dict[str, Any]:
        lbl = label.lower().replace("-", "_").replace(" ", "_")
        if lbl in self.dimensions:
            return self.dimensions[lbl]
        # Check aliases
        for key, conf in self.dimensions.items():
            if "aliases" in conf and (lbl in conf["aliases"] or label.lower() in conf["aliases"]):
                return conf
        return {}

    def get_effective_radius_padding(self, label: str) -> float:
        """Returns extra safety radius padding (e.g. 0.3m for tree roots)."""
        conf = self._get_class_config(label)
        return float(conf.get("root_padding_m", 0.0))

    def estimate_distance(
        self,
        label: str,
        bbox: Tuple[int, int, int, int],
        frame_height: int,
        frame_width: int,
        contact_y: Optional[int] = None
    ) -> float:
        """
        Estimates the distance in meters to the detected object.
        Selects the most stable geometric cue per class:
          - width: for wide objects (cars, buses, trucks, pillars, tree trunks)
          - height: for tall upright objects (persons, chairs, stairs)
          - ground_contact: for low/irregular objects (stones, potholes, 2-wheelers)
        Falls back to ground-plane projection when height/width is unreliable or cropped.
        """
        xmin, ymin, xmax, ymax = bbox
        bbox_height = max(1, ymax - ymin)
        bbox_width = max(1, xmax - xmin)

        scaled_focal_length = self.focal_length_px * (frame_height / 480.0)

        # 1. Ground-plane perspective projection (based on ground contact point ymax or contact_y)
        ground_y = contact_y if contact_y is not None else ymax
        bottom_norm = max(0.0, min(1.0, ground_y / frame_height))  # 0.0 at top, 1.0 at bottom edge
        if bottom_norm > 0.35:
            dist_ground = 0.8 + 4.5 * ((1.0 - bottom_norm) ** 1.8)
        else:
            dist_ground = 5.5

        # Check if object is cropped at frame edges (unreliable height/width)
        is_cropped = (ymin <= 5) or (ymax >= frame_height - 5) or (xmin <= 5) or (xmax >= frame_width - 5)

        conf = self._get_class_config(label)
        primary_dim = conf.get("primary_dimension", "height")
        norm_label = label.lower()

        if is_cropped or primary_dim == "ground_contact" or norm_label in (
            "stone", "rock", "rubble", "large_stone", "pothole", "bottle", "unidentified",
            "two_wheeler", "bicycle", "motorcycle", "bike", "scooter"
        ):
            # Ground-plane projection for ground-contact / irregular / cropped objects
            estimated_dist = dist_ground
            if norm_label == "unidentified":
                # Conservative fail-safe: assume closer than estimated to guarantee safety
                safety_factor = float(conf.get("safety_factor", 0.85))
                estimated_dist = max(0.35, estimated_dist * safety_factor)

        elif primary_dim == "width":
            real_width = conf.get("real_width_m") or conf.get("trunk_diameter_m") or 1.80
            dist_width = (scaled_focal_length * real_width) / bbox_width
            # Cross-check with ground plane to reject outliers
            estimated_dist = 0.75 * dist_width + 0.25 * dist_ground

        else:  # primary_dim == "height"
            real_height = conf.get("real_height_m", 0.80)
            dist_height = (scaled_focal_length * real_height) / bbox_height
            # Cross-check with ground plane
            estimated_dist = 0.70 * dist_height + 0.30 * dist_ground

        # Clamp between 0.3m (immediate collision) and 10.0m (far field)
        return round(float(max(0.3, min(10.0, estimated_dist))), 2)

    def evaluate_walking_lane(
        self,
        bbox: Tuple[int, int, int, int],
        frame_width: int,
        frame_height: int,
        distance_m: float,
        lane_margin_ratio: float = 0.25,
        max_hazard_distance_m: float = 3.5,
        effective_radius_m: float = 0.0
    ) -> Tuple[bool, str, str]:
        """
        Determines whether the obstacle is inside the user's direct walking corridor.
        Accounts for effective_radius_m (e.g. tree root padding) to widen collision corridor.

        Returns:
            (in_walking_lane: bool, horizontal_position: str, urgency: str)
        """
        xmin, ymin, xmax, ymax = bbox
        center_x = (xmin + xmax) / 2.0

        # Horizontal corridor: center 50% of the frame (0.25W to 0.75W)
        pixel_padding = int(effective_radius_m * (frame_width / 4.0)) if effective_radius_m > 0 else 0
        left_bound = frame_width * lane_margin_ratio - pixel_padding
        right_bound = frame_width * (1.0 - lane_margin_ratio) + pixel_padding

        # Horizontal classification
        if center_x < frame_width * 0.35:
            h_pos = "left"
        elif center_x > frame_width * 0.65:
            h_pos = "right"
        else:
            h_pos = "center"

        # Walking lane check:
        # 1. Obstacle center is within corridor bounds
        # 2. Or obstacle substantially encroaches the corridor (>=25% overlap of width and >=30px)
        corridor_overlap = max(0.0, min(float(xmax), right_bound) - max(float(xmin), left_bound))
        corridor_overlap_ratio = corridor_overlap / max(1.0, float(xmax - xmin))
        is_in_corridor = (left_bound <= center_x <= right_bound) or (corridor_overlap_ratio >= 0.25 and corridor_overlap >= 30.0)

        is_close_enough = distance_m <= (max_hazard_distance_m + effective_radius_m)

        in_walking_lane = bool(is_in_corridor and is_close_enough)

        # Determine urgency
        if distance_m <= 1.2 and in_walking_lane:
            urgency = "critical"
        elif distance_m <= 2.2 and in_walking_lane:
            urgency = "high"
        elif distance_m <= (max_hazard_distance_m + effective_radius_m) and in_walking_lane:
            urgency = "medium"
        else:
            urgency = "low"

        return in_walking_lane, h_pos, urgency
