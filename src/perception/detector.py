"""YOLOv8n-based obstacle detection and frame analysis engine with temporal debouncing,
multi-class recognition, monocular distance estimation, and kinematic tracking.

Fix changelog (v2):
  - Confidence threshold raised from 0.35 → 0.45 (fewer low-quality YOLO picks).
  - alert_confidence_threshold (default 0.55): secondary gate before triggering haptic/audio.
  - max_alert_distance_m (default 4.0): obstacles beyond this are tracked but never alerted.
  - stability_required_sec (default 2.0): static/parked obstacles must persist for ≥2 s
    before becoming primary_obstacle.  Moving-approaching objects bypass this wait.
  - Moving-away obstacles (velocity_mps ≤ -0.25 m/s) are never elevated to primary.
"""
import threading
import time
from typing import Dict, List, Optional, Set, Tuple
import cv2
import numpy as np

from .distance import DistanceEstimator
from .hazard_heuristics import EnvironmentalHazardDetector
from .models import DetectedObstacle, FramePerceptionResult
from .shadow_filter import ShadowLightAnalyzer
from .tracking import CentroidTracker


# Target COCO classes relevant to indoor and campus navigation (including vehicles)
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
    "bicycle",
    "motorcycle",
    "car",
    "bus",
    "truck",
    "traffic light",
    "stop sign",
    "fire hydrant"
}


class ObstacleDetector:
    """
    Real-time perception pipeline combining YOLOv8n object detection,
    heuristic hazard recognition (stairs/potholes/walls/stones/trees/pillars/unidentified),
    monocular distance estimation, dynamic kinematic tracking, and temporal debouncing.
    """

    def __init__(
        self,
        model_name: str = "yolov8l.pt",
        confidence_threshold: float = 0.65,          # Upgraded to YOLOv8l with 0.65 high-confidence gate
        target_classes: Optional[Set[str]] = None,
        focal_length_px: float = 650.0,
        enable_heuristics: bool = True,
        max_alert_distance_m: float = 4.0,           # Beyond this: track silently, no alert
        alert_confidence_threshold: float = 0.65,    # High confidence gate before alerting (0.6-0.7)
        stability_required_sec: float = 2.0,         # Static/parked must persist ≥N s
        inference_cadence: int = 1                   # Run full YOLO/hazards every N frames (cadence ≥ 4 for 10-12 FPS)
    ):
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.target_classes = target_classes or TARGET_COCO_CLASSES
        self.enable_heuristics = enable_heuristics
        self.max_alert_distance_m = max_alert_distance_m
        self.alert_confidence_threshold = alert_confidence_threshold
        self.stability_required_sec = stability_required_sec
        self.inference_cadence = max(1, inference_cadence)

        self.distance_estimator = DistanceEstimator(focal_length_px)
        self.shadow_analyzer = ShadowLightAnalyzer()
        self.hazard_detector = EnvironmentalHazardDetector(self.distance_estimator, self.shadow_analyzer)
        self.tracker = CentroidTracker()

        self._lock = threading.Lock()
        self._model = None
        self._frame_count = 0
        self._cached_detected_obstacles: Optional[List[DetectedObstacle]] = None
        self._frame_timestamps: List[float] = []

        # Debounce tracking: {label: consecutive_frames_seen}
        self._seen_history: Dict[str, int] = {}

        # Temporal stability tracking: {label: first_timestamp_when_obstacle_was_static}
        # Cleared when the label disappears from view or starts moving.
        self._label_first_stable: Dict[str, float] = {}

    def _load_model_if_needed(self):
        """Lazy loader for YOLO model to allow import without immediate model weight download."""
        if self._model is None:
            import torch
            if not torch.cuda.is_available():
                try:
                    torch.set_num_threads(12)
                except Exception:
                    pass
            from ultralytics import YOLO
            self._model = YOLO(self.model_name)

    def reset_cadence(self) -> None:
        """Forces the next processed frame to be a full inference keyframe."""
        with self._lock:
            self._cached_detected_obstacles = None

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
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
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
            now_ts = time.time()

            is_keyframe = (
                self.inference_cadence <= 1
                or (self._frame_count % self.inference_cadence == 1)
                or (self._cached_detected_obstacles is None)
            )

            current_labels_seen: Set[str] = set()

            if is_keyframe:
                detected_obstacles: List[DetectedObstacle] = []

                # 1. Run YOLO inference (CPU optimized with inference_mode)
                import torch
                with torch.inference_mode():
                    results = self._model.predict(
                        source=frame,
                        conf=self.confidence_threshold,
                        verbose=False,
                        imgsz=640
                    )

                if results and len(results) > 0:
                    boxes = results[0].boxes
                    names = results[0].names

                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        raw_label = names.get(cls_id, "object").lower()

                        if raw_label not in self.target_classes:
                            continue

                        conf = float(box.conf[0].item())
                        xyxy = box.xyxy[0].tolist()
                        xmin, ymin, xmax, ymax = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
                        bbox = (xmin, ymin, xmax, ymax)

                        # Map raw YOLO vehicle classes to unified names if desired
                        label = raw_label
                        if raw_label in ("bicycle", "motorcycle"):
                            label = "two_wheeler"
                        elif raw_label in ("car", "bus", "truck"):
                            label = "four_wheeler"

                        # Ground contact y (bottom of wheels/base)
                        contact_y = ymax

                        dist = self.distance_estimator.estimate_distance(
                            label, bbox, h, w, contact_y=contact_y
                        )
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
                            is_environmental_hazard=False,
                            detection_source="yolo",
                            ground_contact_y=contact_y
                        ))

                # 2. Run Environmental Hazard Heuristics (stairs, potholes, walls, stones, trees, pillars, unidentified)
                if self.enable_heuristics:
                    env_hazards = self.hazard_detector.detect_hazards(
                        frame, excluded_obstacles=detected_obstacles
                    )
                    for hazard in env_hazards:
                        current_labels_seen.add(hazard.label)
                        detected_obstacles.append(hazard)

                # 3. Apply Shadow/Light Analysis to uncalibrated obstacles
                for obs in detected_obstacles:
                    if obs.shadow_likelihood == 0.0 and obs.label in ("stone", "pothole", "stair"):
                        shd, cal_conf = self.shadow_analyzer.analyze_obstacle(
                            frame, obs.bbox, obs.label, obs.confidence, timestamp=now_ts
                        )
                        obs.shadow_likelihood = shd
                        obs.raw_confidence = obs.confidence
                        obs.confidence = cal_conf

                # Suppress obstacles whose confidence dropped below threshold due to shadow penalty
                detected_obstacles = [o for o in detected_obstacles if o.confidence >= self.confidence_threshold]

                # Update keyframe cache
                self._cached_detected_obstacles = list(detected_obstacles)
            else:
                # Fast tracking frame: reuse cached detections with updated lane checks
                detected_obstacles = []
                for obs in self._cached_detected_obstacles:
                    in_lane, h_pos, urgency = self.distance_estimator.evaluate_walking_lane(
                        obs.bbox, w, h, obs.distance_m
                    )
                    current_labels_seen.add(obs.label)
                    detected_obstacles.append(
                        obs.model_copy(update={
                            "in_walking_lane": in_lane,
                            "horizontal_position": h_pos,
                            "urgency": urgency
                        })
                    )

            # 4. Kinematic Tracking across frames (velocity, moving vs parked state)
            self.tracker.update(detected_obstacles, timestamp=now_ts)

            # 5. Temporal Debounce / Hysteresis (frame counter)
            for lbl in current_labels_seen:
                self._seen_history[lbl] = self._seen_history.get(lbl, 0) + 1
            for lbl in list(self._seen_history.keys()):
                if lbl not in current_labels_seen:
                    self._seen_history[lbl] = max(0, self._seen_history[lbl] - 1)

            # 6. Temporal Stability Clock (wall-clock, per label)
            # Tracks how long a label has been continuously *static* in the walking lane.
            # Cleared when the object becomes dynamic or leaves the lane/view.
            current_static_lane_labels: Set[str] = set()
            for obs in detected_obstacles:
                if obs.in_walking_lane and not obs.is_moving:
                    current_static_lane_labels.add(obs.label)
                    if obs.label not in self._label_first_stable:
                        self._label_first_stable[obs.label] = now_ts  # Start the stability clock
                elif obs.is_moving and obs.label in self._label_first_stable:
                    # Object started moving again — reset its stability clock
                    del self._label_first_stable[obs.label]
            # Prune labels no longer visible
            for lbl in list(self._label_first_stable.keys()):
                if lbl not in current_labels_seen:
                    del self._label_first_stable[lbl]

            # Filter or prioritize confirmed obstacles in walking lane
            lane_obstacles = [o for o in detected_obstacles if o.in_walking_lane]

            # Priority ranking: critical urgency first, then approaching movers, then distance
            lane_obstacles.sort(
                key=lambda o: (
                    0 if o.urgency == "critical" else (1 if (o.is_moving and o.velocity_mps >= 0.25) else 2),
                    o.distance_m,
                    -o.confidence
                )
            )

            # Select primary obstacle by walking through sorted candidates and applying all filters
            primary_obs: Optional[DetectedObstacle] = None
            for candidate in lane_obstacles:
                lbl = candidate.label

                # ── Rule 1: Moving-away objects are never a hazard ─────────────────────
                if candidate.velocity_mps <= -0.25:
                    continue

                # ── Rule 2: Distance cap ──────────────────────────────────────────────
                if candidate.distance_m > self.max_alert_distance_m:
                    continue

                # ── Rule 3: Frame debounce ────────────────────────────────────────────
                seen_count = self._seen_history.get(lbl, 0)
                if seen_count < debounce_frames and candidate.urgency not in ("critical", "high"):
                    continue

                # ── Rule 4: Alert-confidence gate ─────────────────────────────────────
                # Emergency override: critically-close obstacle always wins.
                is_emergency = (candidate.urgency == "critical" and candidate.distance_m <= 1.5)
                if candidate.confidence < self.alert_confidence_threshold and not is_emergency:
                    continue

                # ── Rule 5: 2-second temporal stability for static/parked obstacles ──
                if not candidate.is_moving:
                    stable_ts = self._label_first_stable.get(lbl)
                    stable_for_sec = (now_ts - stable_ts) if stable_ts is not None else 0.0
                    if stable_for_sec < self.stability_required_sec and not is_emergency:
                        continue  # Not confirmed long enough yet — keep tracking silently

                # All filters passed — this is the primary obstacle
                primary_obs = candidate
                break

            now_call = time.time()
            proc_time_ms = max(0.5, round((now_call - start_time) * 1000.0, 1))

            # Calculate steady throughput FPS across rolling window of frames
            self._frame_timestamps.append(now_call)
            if len(self._frame_timestamps) > 15:
                self._frame_timestamps.pop(0)

            if len(self._frame_timestamps) >= 2:
                time_span = self._frame_timestamps[-1] - self._frame_timestamps[0]
                fps = round((len(self._frame_timestamps) - 1) / time_span, 1) if time_span > 0 else 0.0
            else:
                fps = round(1000.0 / proc_time_ms, 1) if proc_time_ms > 0 else 0.0

            return FramePerceptionResult(
                frame_id=self._frame_count,
                timestamp=now_call,
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
        """Draws bounding boxes, walking lane overlay, root padding, and HUD telemetry on the frame."""
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

        # Draw Obstacle Bounding Boxes & Ground Contacts
        for obs in result.obstacles:
            xmin, ymin, xmax, ymax = obs.bbox

            if obs.urgency == "critical":
                box_color = (0, 0, 255)      # Red for Critical
            elif obs.urgency == "high":
                box_color = (0, 140, 255)    # Orange for High
            elif obs.in_walking_lane:
                box_color = (0, 255, 255)    # Yellow for In-Lane
            else:
                box_color = (255, 200, 0)    # Cyan/Blue for off-path

            thickness = 3 if obs == result.primary_obstacle else 2
            cv2.rectangle(annotated, (xmin, ymin), (xmax, ymax), box_color, thickness)

            # Draw Ground Contact Line
            if obs.ground_contact_y is not None:
                cv2.line(
                    annotated,
                    (xmin, obs.ground_contact_y),
                    (xmax, obs.ground_contact_y),
                    (0, 255, 255),
                    2
                )

            # Draw Root Ring padding for trees
            if obs.label == "tree" and obs.effective_radius_m > 0:
                pad_px = int(obs.effective_radius_m * (w / 4.0))
                center_x = (xmin + xmax) // 2
                cv2.ellipse(
                    annotated,
                    (center_x, ymax),
                    (max(10, (xmax - xmin) // 2 + pad_px), max(5, pad_px // 2)),
                    0, 0, 360,
                    (0, 165, 255),
                    2,
                    cv2.LINE_AA
                )

            # Label text formatting: "CAR 0.88 | 2.1m [MOVING +1.2m/s] [LANE]"
            lane_tag = " [LANE]" if obs.in_walking_lane else ""
            state_tag = ""
            if obs.state == "moving":
                vel_sign = "+" if obs.velocity_mps >= 0 else ""
                state_tag = f" [{obs.state.upper()} {vel_sign}{obs.velocity_mps}m/s]"
            elif obs.state == "parked":
                state_tag = " [PARKED]"

            shd_tag = f" [SHD:{obs.shadow_likelihood:.2f}]" if obs.shadow_likelihood > 0 else ""
            root_tag = " [+ROOT]" if (obs.label == "tree" and obs.effective_radius_m > 0) else ""

            label_text = f"{obs.label.upper()} {obs.confidence:.2f}{shd_tag} | {obs.distance_m}m{state_tag}{root_tag}{lane_tag}"

            # Label background box
            (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
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
                0.45,
                (0, 0, 0) if box_color == (0, 255, 255) else (255, 255, 255),
                1,
                cv2.LINE_AA
            )

        # Draw Top HUD Telemetry
        hud_text = f"FPS: {result.fps} | Latency: {result.processing_time_ms}ms"
        if result.primary_obstacle:
            state_info = f" ({result.primary_obstacle.state.upper()})" if result.primary_obstacle.state != "static" else ""
            shd_hud = f" (Shd:{result.primary_obstacle.shadow_likelihood:.2f})" if result.primary_obstacle.shadow_likelihood > 0 else ""
            status_text = (
                f"HAZARD: {result.primary_obstacle.label.upper()}{state_info}{shd_hud} "
                f"({result.primary_obstacle.distance_m}m) - {result.primary_obstacle.urgency.upper()}"
            )
            status_color = (0, 0, 255) if result.primary_obstacle.urgency in ("critical", "high") else (0, 140, 255)
        else:
            status_text = "PATH CLEAR"
            status_color = (0, 255, 0)

        cv2.putText(annotated, hud_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(annotated, status_text, (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

        return annotated
