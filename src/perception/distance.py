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

        # 1. Continuous perspective ground-plane projection (calibrated inverse-distance curve)
        ground_y = contact_y if contact_y is not None else ymax
        y_norm = max(0.0, min(1.0, ground_y / frame_height))
        y_horizon = 0.36
        if y_norm <= y_horizon:
            dist_ground = 8.0
        else:
            v = (y_norm - y_horizon) / (1.0 - y_horizon)
            dist_ground = 0.60 + 1.25 * ((1.0 - v) / (v + 0.18))

        conf = self._get_class_config(label)
        primary_dim = conf.get("primary_dimension", "height")
        norm_label = label.lower()

        # Edge crop reliability factors [0.05 to 1.0]
        # Smoothly down-weights height or width when truncated at screen border to prevent jumpiness
        crop_margin = 12.0
        crop_top = max(0.05, min(1.0, ymin / crop_margin))
        crop_bot = max(0.05, min(1.0, (frame_height - ymax) / crop_margin))
        crop_left = max(0.05, min(1.0, xmin / crop_margin))
        crop_right = max(0.05, min(1.0, (frame_width - xmax) / crop_margin))

        r_vert = crop_top * crop_bot
        r_horiz = crop_left * crop_right

        real_width = float(conf.get("real_width_m") or conf.get("trunk_diameter_m") or 0.50)
        real_height = float(conf.get("real_height_m", 0.80))

        # Aspect ratio check for upright objects (detect torso vs full body)
        # Prevents torso/half-body detections from severely overestimating distance
        ar = bbox_height / float(bbox_width)
        if norm_label == "person" and ar < 2.2:
            eff_height = min(real_height, real_width * max(1.4, ar))
        else:
            eff_height = real_height

        dist_height = (scaled_focal_length * eff_height) / bbox_height
        dist_width = (scaled_focal_length * real_width) / bbox_width

        # Multi-cue continuous fusion based on class semantics and boundary reliability
        if norm_label == "unidentified":
            safety_factor = float(conf.get("safety_factor", 0.85))
            estimated_dist = max(0.35, dist_ground * safety_factor)

        elif primary_dim == "ground_contact" or norm_label in (
            "stone", "rock", "rubble", "large_stone", "pothole", "bottle",
            "two_wheeler", "bicycle", "motorcycle", "bike", "scooter"
        ):
            # Ground-plane projection dominant for low-profile / irregular floor hazards
            w_g = 0.85
            w_w = 0.15 * r_horiz
            estimated_dist = (w_g * dist_ground + w_w * dist_width) / (w_g + w_w)

        elif primary_dim == "width":
            # Width-dominant objects (vehicles, pillars, walls, gates)
            w_w = 0.70 * r_horiz
            w_g = 0.20
            w_h = 0.10 * r_vert
            total_w = w_w + w_g + w_h
            estimated_dist = (w_w * dist_width + w_g * dist_ground + w_h * dist_height) / total_w

        else:
            # Height-dominant objects (person, chair, stair, backpack, etc.)
            w_h = 0.50 * r_vert
            w_w = 0.35 * r_horiz
            w_g = 0.15
            total_w = w_h + w_w + w_g
            estimated_dist = (w_h * dist_height + w_w * dist_width + w_g * dist_ground) / total_w

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
