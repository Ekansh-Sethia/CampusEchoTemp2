"""Unit tests for the perception module: YOLOv8n, distance estimation, hazard heuristics, and video sources."""
from pathlib import Path
import cv2
import numpy as np
import pytest

from src.perception.distance import DistanceEstimator
from src.perception.hazard_heuristics import EnvironmentalHazardDetector
from src.perception.video_source import VideoSource
from src.perception.detector import ObstacleDetector
from tests.generate_test_frames import generate_all_frames


TEST_FRAMES_DIR = Path(__file__).parent.parent / "data" / "test_frames"

# Ensure test frames exist
if not TEST_FRAMES_DIR.exists() or not list(TEST_FRAMES_DIR.glob("*.jpg")):
    generate_all_frames()


@pytest.fixture
def distance_estimator():
    return DistanceEstimator(focal_length_px=650.0)


@pytest.fixture
def hazard_detector(distance_estimator):
    return EnvironmentalHazardDetector(distance_estimator)


@pytest.fixture
def obstacle_detector():
    return ObstacleDetector(confidence_threshold=0.30, enable_heuristics=True)


def test_distance_estimator_pinhole(distance_estimator):
    """Verifies that bounding box height inversely scales with distance."""
    h_frame, w_frame = 480, 640

    # Large chair close up (height = 250px)
    close_bbox = (220, 150, 420, 400)
    dist_close = distance_estimator.estimate_distance("chair", close_bbox, h_frame, w_frame)

    # Small chair far away (height = 80px)
    far_bbox = (280, 200, 360, 280)
    dist_far = distance_estimator.estimate_distance("chair", far_bbox, h_frame, w_frame)

    assert dist_close < dist_far
    assert 1.0 <= dist_close <= 2.5
    assert dist_far >= 3.5


def test_walking_lane_evaluation(distance_estimator):
    """Verifies corridor containment and urgency levels."""
    h_frame, w_frame = 480, 640

    # 1. Obstacle directly in center corridor at 1.8m -> in lane, high urgency
    center_bbox = (240, 200, 400, 420)
    in_lane, h_pos, urgency = distance_estimator.evaluate_walking_lane(
        center_bbox, w_frame, h_frame, distance_m=1.8
    )
    assert in_lane is True
    assert h_pos == "center"
    assert urgency == "high"

    # 2. Obstacle far off to the left side (0 to 100px) -> outside lane
    left_bbox = (10, 250, 90, 400)
    in_lane_left, h_pos_left, _ = distance_estimator.evaluate_walking_lane(
        left_bbox, w_frame, h_frame, distance_m=1.8
    )
    assert in_lane_left is False
    assert h_pos_left == "left"

    # 3. Obstacle in corridor but far away (>3.5m) -> not in immediate walking lane
    in_lane_far, _, urgency_far = distance_estimator.evaluate_walking_lane(
        center_bbox, w_frame, h_frame, distance_m=4.5
    )
    assert in_lane_far is False
    assert urgency_far == "low"


def test_hazard_heuristics_stairs(hazard_detector):
    """Verifies heuristic detection of staircases."""
    img_path = TEST_FRAMES_DIR / "frame_03_stairs.jpg"
    frame = cv2.imread(str(img_path))
    assert frame is not None

    hazards = hazard_detector.detect_hazards(frame)
    stair_hazards = [h for h in hazards if h.label == "stair"]
    assert len(stair_hazards) >= 1
    stair = stair_hazards[0]
    assert stair.in_walking_lane is True
    assert stair.confidence >= 0.60


def test_hazard_heuristics_pothole(hazard_detector):
    """Verifies heuristic detection of potholes / surface depressions."""
    img_path = TEST_FRAMES_DIR / "frame_04_pothole.jpg"
    frame = cv2.imread(str(img_path))
    assert frame is not None

    hazards = hazard_detector.detect_hazards(frame)
    pothole_hazards = [h for h in hazards if h.label == "pothole"]
    assert len(pothole_hazards) >= 1
    pothole = pothole_hazards[0]
    assert pothole.in_walking_lane is True
    assert pothole.distance_m <= 3.5


def test_hazard_heuristics_wall(hazard_detector):
    """Verifies heuristic detection of close wall / dead end."""
    img_path = TEST_FRAMES_DIR / "frame_05_wall.jpg"
    frame = cv2.imread(str(img_path))
    assert frame is not None

    hazards = hazard_detector.detect_hazards(frame)
    wall_hazards = [h for h in hazards if h.label == "wall"]
    assert len(wall_hazards) >= 1
    assert wall_hazards[0].urgency == "critical"


def test_video_source_image_directory():
    """Verifies that VideoSource correctly reads and loops image directories."""
    with VideoSource(source=TEST_FRAMES_DIR, loop_file=True) as v_src:
        assert v_src.is_opened is True
        ret1, frame1 = v_src.read_frame()
        assert ret1 is True
        assert frame1 is not None
        assert frame1.shape == (480, 640, 3)

        # Read multiple frames and ensure looping works
        for _ in range(10):
            ret, f = v_src.read_frame()
            assert ret is True
            assert f is not None


def test_detector_clear_frame(obstacle_detector):
    """Verifies that a clear hallway produces path_clear=True."""
    frame = cv2.imread(str(TEST_FRAMES_DIR / "frame_01_clear.jpg"))
    result = obstacle_detector.process_frame(frame)
    assert result.path_clear is True
    assert result.primary_obstacle is None
    assert result.processing_time_ms > 0.0


def test_detector_debouncing(obstacle_detector):
    """
    Verifies that single-frame flicker is debounced, and persistent obstacles
    across 2 consecutive frames are confirmed.
    """
    frame_stairs = cv2.imread(str(TEST_FRAMES_DIR / "frame_03_stairs.jpg"))

    # Frame 1: seen once (debouncing requires 2 frames unless critical)
    res1 = obstacle_detector.process_frame(frame_stairs, debounce_frames=2)
    # Frame 2: seen twice -> confirmed
    res2 = obstacle_detector.process_frame(frame_stairs, debounce_frames=2)

    assert res2.primary_obstacle is not None
    assert res2.primary_obstacle.label == "stair"
    assert res2.path_clear is False


def test_person_exclusion_prevents_false_pothole(obstacle_detector):
    """
    Verifies that a person wearing dark clothes/shoes does NOT trigger a false pothole
    due to exclusion masking and physical structure checks.
    """
    # Create a frame with a person (dark torso/legs in lower frame)
    h, w = 480, 640
    frame = np.full((h, w, 3), 190, dtype=np.uint8)

    # Draw dark clothes/legs where a person stands in the lower center
    cv2.rectangle(frame, (260, 200), (380, 440), (30, 30, 35), -1)

    # Synthetic obstacle representing the person detected by YOLO
    from src.perception.models import DetectedObstacle
    person_obs = DetectedObstacle(
        label="person",
        confidence=0.92,
        bbox=(250, 180, 390, 450),
        bbox_normalized=(250/w, 180/h, 390/w, 450/h),
        distance_m=2.0,
        in_walking_lane=True,
        horizontal_position="center",
        urgency="high"
    )

    # Test hazard detector with the person in excluded_obstacles
    hazards = obstacle_detector.hazard_detector.detect_hazards(
        frame, excluded_obstacles=[person_obs]
    )

    potholes = [h for h in hazards if h.label == "pothole"]
    assert len(potholes) == 0, "Person's dark clothes should NOT be detected as a pothole!"

