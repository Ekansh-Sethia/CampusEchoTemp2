"""Data models for perception, object detection, and hazard classification."""
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field


class DetectedObstacle(BaseModel):
    """Represents a single detected obstacle in the camera frame."""
    label: str                                   # e.g., "chair", "person", "car", "bicycle", "stair", "pothole", "tree", "pillar", "stone", "unidentified"
    confidence: float                            # Detection confidence [0.0 - 1.0]
    bbox: Tuple[int, int, int, int]              # [xmin, ymin, xmax, ymax] in pixels
    bbox_normalized: Tuple[float, float, float, float]  # [xmin, ymin, xmax, ymax] in [0.0, 1.0]
    distance_m: float                            # Estimated distance in meters
    in_walking_lane: bool                        # True if directly in user's walking path
    horizontal_position: str                     # "left", "center", "right"
    urgency: str = "medium"                      # "low", "medium", "high", "critical"
    is_environmental_hazard: bool = False        # True for stairs, potholes, walls, stones, trees
    is_moving: bool = False                      # True if dynamic obstacle has non-zero approach velocity
    velocity_mps: float = 0.0                    # Approach velocity in meters/second
    effective_radius_m: float = 0.0              # Extended hazard radius (e.g. tree roots)
    detection_source: str = "yolo"               # "yolo", "heuristic", "unidentified"
    tracking_id: Optional[int] = None            # Unique track ID across frames
    state: str = "static"                        # "static", "parked", "moving"
    ground_contact_y: Optional[int] = None       # Pixel y-coordinate of ground contact line


class FramePerceptionResult(BaseModel):
    """Complete perception analysis for a single video frame."""
    frame_id: int
    timestamp: float
    obstacles: List[DetectedObstacle] = Field(default_factory=list)
    primary_obstacle: Optional[DetectedObstacle] = None  # Most urgent obstacle in lane
    path_clear: bool = True
    processing_time_ms: float = 0.0
    fps: float = 0.0
