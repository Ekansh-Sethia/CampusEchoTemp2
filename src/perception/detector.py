"""YOLOv8n-based obstacle detection and frame analysis engine with temporal debouncing."""
import threading
import time
from typing import Dict, List, Optional, Set, Tuple
import cv2
import numpy as np

from .distance import DistanceEstimator
from .hazard_heuristics import EnvironmentalHazardDetector
from .models import DetectedObstacle, FramePerceptionResult


# Target COCO classes relevant to indoor and campus navigation
TARGET_COCO_CLASSES: Set[str] = {
    "person",
    "chair",
    "couch",
    "bench",
    "dining table",
    "backpack",
    "suitcase",
    "handbag",
    "bottle",
    "potted plant",
    "traffic light",
    "stop sign",
    "fire hydrant"
}


class ObstacleDetector:
    """
    Real-time perception pipeline combining YOLOv8n object detection,
    heuristic hazard recognition (stairs/potholes/walls), distance estimation,
    and temporal debouncing to eliminate noisy flickering.
    """

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        confidence_threshold: float = 0.35,
        target_classes: Optional[Set[str]] = None,
        focal_length_px: float = 650.0,
        enable_heuristics: bool = True
    ):
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.target_classes = target_classes or TARGET_COCO_CLASSES
        self.enable_heuristics = enable_heuristics

        self.distance_estimator = DistanceEstimator(focal_length_px)
        self.hazard_detector = EnvironmentalHazardDetector(self.distance_estimator)

        self._lock = threading.Lock()
        self._model = None
        self._frame_count = 0
        self._last_process_time = 0.0

        # Debounce tracking: {label: consecutive_frames_seen}
        self._seen_history: Dict[str, int] = {}

    def _load_model_if_needed(self):
        """Lazy loader for YOLO model to allow import without immediate model weight download."""
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(self.model_name)

    def process_frame(
        self,
        frame: np.ndarray,
        debounce_frames: int = 2
    ) -> FramePerceptionResult:
        """
        Analyzes a single video frame. Thread-safe and non-overlapping.

        Args:
            frame: BGR numpy image array.
            debounce_frames: Number of consecutive frames an obstacle must be seen
                             to be confirmed (suppresses single-frame noise).
        """
        # Non-blocking lock to guarantee no overlapping frame execution
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            # Drop frame if previous processing is still ongoing
            return FramePerceptionResult(
                frame_id=self._frame_count,
                timestamp=time.time(),
                path_clear=True,
                processing_time_ms=0.0
            )

        start_time = time.time()
        try:
            self._load_model_if_needed()
            self._frame_count += 1
            h, w = frame.shape[:2]

            detected_obstacles: List[DetectedObstacle] = []

            # 1. Run YOLOv8n inference (CPU optimized)
            results = self._model.predict(
                source=frame,
                conf=self.confidence_threshold,
                verbose=False,
                imgsz=640
            )

            current_labels_seen: Set[str] = set()

            if results and len(results) > 0:
                boxes = results[0].boxes
                names = results[0].names

                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    label = names.get(cls_id, "object").lower()

                    if label not in self.target_classes:
                        continue

                    conf = float(box.conf[0].item())
                    xyxy = box.xyxy[0].tolist()
                    xmin, ymin, xmax, ymax = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
                    bbox = (xmin, ymin, xmax, ymax)

                    dist = self.distance_estimator.estimate_distance(label, bbox, h, w)
                    in_lane, h_pos, urgency = self.distance_estimator.evaluate_walking_lane(
                        bbox, w, h, dist
                    )

                    current_labels_seen.add(label)

                    detected_obstacles.append(DetectedObstacle(
                        label=label,
                        confidence=round(conf, 2),
                        bbox=bbox,
                        bbox_normalized=(xmin / w, ymin / h, xmax / w, ymax / h),
                        distance_m=dist,
                        in_walking_lane=in_lane,
                        horizontal_position=h_pos,
                        urgency=urgency,
                        is_environmental_hazard=False
                    ))

            # 2. Run Environmental Hazard Heuristics (stairs, potholes, walls)
            if self.enable_heuristics:
                env_hazards = self.hazard_detector.detect_hazards(frame)
                for hazard in env_hazards:
                    current_labels_seen.add(hazard.label)
                    detected_obstacles.append(hazard)

            # 3. Apply Temporal Debounce / Hysteresis
            # Update history counts
            for lbl in current_labels_seen:
                self._seen_history[lbl] = self._seen_history.get(lbl, 0) + 1
            # Decay unseen objects
            for lbl in list(self._seen_history.keys()):
                if lbl not in current_labels_seen:
                    self._seen_history[lbl] = max(0, self._seen_history[lbl] - 1)

            # Filter or prioritize confirmed obstacles in walking lane
            lane_obstacles = [o for o in detected_obstacles if o.in_walking_lane]

            # Primary obstacle is the closest / highest urgency confirmed in lane
            primary_obs: Optional[DetectedObstacle] = None
            if lane_obstacles:
                # Sort by distance (closest first)
                lane_obstacles.sort(key=lambda o: (o.distance_m, -o.confidence))
                closest = lane_obstacles[0]
                # If seen for >= debounce_frames or urgency is critical, confirm as primary
                seen_count = self._seen_history.get(closest.label, 1)
                if seen_count >= debounce_frames or closest.urgency in ("critical", "high"):
                    primary_obs = closest

            proc_time_ms = round((time.time() - start_time) * 1000.0, 1)
            fps = round(1000.0 / proc_time_ms, 1) if proc_time_ms > 0 else 0.0

            return FramePerceptionResult(
                frame_id=self._frame_count,
                timestamp=time.time(),
                obstacles=detected_obstacles,
                primary_obstacle=primary_obs,
                path_clear=(primary_obs is None),
                processing_time_ms=proc_time_ms,
                fps=fps
            )

        finally:
            self._lock.release()

    def annotate_frame(
        self,
        frame: np.ndarray,
        result: FramePerceptionResult
    ) -> np.ndarray:
        """Draws bounding boxes, walking lane overlay, and HUD telemetry on the frame."""
        annotated = frame.copy()
        h, w = frame.shape[:2]

        # Draw Walking Lane Corridor (center 50%)
        lane_x1 = int(w * 0.25)
        lane_x2 = int(w * 0.75)
        corridor_overlay = annotated.copy()
        cv2.rectangle(corridor_overlay, (lane_x1, 0), (lane_x2, h), (0, 255, 0), -1)
        cv2.addWeighted(corridor_overlay, 0.08, annotated, 0.92, 0, annotated)

        # Draw Walking Corridor Boundary Lines
        cv2.line(annotated, (lane_x1, 0), (lane_x1, h), (0, 255, 0), 1, cv2.LINE_AA)
        cv2.line(annotated, (lane_x2, 0), (lane_x2, h), (0, 255, 0), 1, cv2.LINE_AA)

        # Draw Obstacle Bounding Boxes
        for obs in result.obstacles:
            xmin, ymin, xmax, ymax = obs.bbox

            if obs.urgency == "critical":
                box_color = (0, 0, 255)      # Red
            elif obs.urgency == "high":
                box_color = (0, 140, 255)    # Orange
            elif obs.in_walking_lane:
                box_color = (0, 255, 255)    # Yellow
            else:
                box_color = (255, 200, 0)    # Cyan/Blue

            thickness = 3 if obs == result.primary_obstacle else 2
            cv2.rectangle(annotated, (xmin, ymin), (xmax, ymax), box_color, thickness)

            # Label text: "chair | 0.88 | 2.1m [LANE]"
            lane_tag = " [LANE]" if obs.in_walking_lane else ""
            label_text = f"{obs.label.upper()} {obs.confidence:.2f} | {obs.distance_m}m{lane_tag}"

            # Label background box
            (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(
                annotated,
                (xmin, max(0, ymin - 20)),
                (xmin + tw + 6, max(20, ymin)),
                box_color,
                -1
            )
            cv2.putText(
                annotated,
                label_text,
                (xmin + 3, max(15, ymin - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0) if box_color == (0, 255, 255) else (255, 255, 255),
                1,
                cv2.LINE_AA
            )

        # Draw Top HUD Telemetry
        hud_text = f"FPS: {result.fps} | Latency: {result.processing_time_ms}ms"
        if result.primary_obstacle:
            status_text = (
                f"HAZARD: {result.primary_obstacle.label.upper()} "
                f"({result.primary_obstacle.distance_m}m) - {result.primary_obstacle.urgency.upper()}"
            )
            status_color = (0, 0, 255)
        else:
            status_text = "PATH CLEAR"
            status_color = (0, 255, 0)

        cv2.putText(annotated, hud_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(annotated, status_text, (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

        return annotated
