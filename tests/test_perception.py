"""Unit tests for the perception module: YOLOv8n, distance estimation, hazard heuristics,
vehicle detection, stone vs paver blocks differentiation, tree detection via leaves/foliage
and trunk, and velocity tracking.
"""
from pathlib import Path
import cv2
import numpy as np
import pytest

from src.perception.distance import DistanceEstimator
from src.perception.hazard_heuristics import EnvironmentalHazardDetector
from src.perception.video_source import VideoSource
from src.perception.detector import ObstacleDetector
from src.perception.tracking import CentroidTracker
from src.perception.models import DetectedObstacle
from tests.generate_test_frames import generate_all_frames


TEST_FRAMES_DIR = Path(__file__).parent.parent / "data" / "test_frames"

# Ensure all 12 test frames exist
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
    """Verifies that bounding box height/width inversely scales with distance."""
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


def test_two_wheeler_and_four_wheeler_distance_estimation(distance_estimator):
    """
    Verifies that distance estimation uses:
      - Width for four-wheelers (car/bus/truck)
      - Ground contact point for two-wheelers (bicycle/motorcycle)
    """
    h_frame, w_frame = 480, 640

    # 1. Four-wheeler (Car): width = 280px, height = 120px at bottom y=380
    car_bbox = (180, 260, 460, 380)
    car_dist = distance_estimator.estimate_distance("four_wheeler", car_bbox, h_frame, w_frame)
    assert 2.0 <= car_dist <= 5.0

    # 2. Two-wheeler (Bicycle): uses wheel ground contact line (y=390)
    bike_bbox = (260, 300, 370, 390)
    bike_dist = distance_estimator.estimate_distance("two_wheeler", bike_bbox, h_frame, w_frame, contact_y=390)
    assert 1.0 <= bike_dist <= 3.0


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


def test_stone_differentiated_from_paver_blocks(hazard_detector):
    """
    Verifies that:
      1. A large stone protruding from a paver block floor IS detected as a stone.
      2. A flat paver block walkway without a stone does NOT trigger false stone or stair detections.
    """
    # 1. Test frame with 3D stone on paver walkway
    img_stone = cv2.imread(str(TEST_FRAMES_DIR / "frame_10_large_stone.jpg"))
    assert img_stone is not None
    hazards_stone = hazard_detector.detect_hazards(img_stone)
    stone_obs = [h for h in hazards_stone if h.label == "stone"]
    assert len(stone_obs) >= 1, "Large stone should be detected!"
    assert stone_obs[0].in_walking_lane is True
    assert stone_obs[0].confidence >= 0.60

    # 2. Test flat paver blocks (without stone)
    img_pavers = cv2.imread(str(TEST_FRAMES_DIR / "frame_06_paver_blocks.jpg"))
    assert img_pavers is not None
    hazards_pavers = hazard_detector.detect_hazards(img_pavers)
    stones_in_pavers = [h for h in hazards_pavers if h.label == "stone"]
    stairs_in_pavers = [h for h in hazards_pavers if h.label == "stair"]
    assert len(stones_in_pavers) == 0, "Flat paver blocks must NOT be detected as stones!"
    assert len(stairs_in_pavers) == 0, "Flat paver blocks must NOT be detected as stairs!"


def test_tree_root_padding_extension(hazard_detector):
    """
    Verifies that a tree with both trunk and canopy is detected,
    and its raised root ring extends the effective hazard radius by +0.3m.
    """
    img_tree = cv2.imread(str(TEST_FRAMES_DIR / "frame_11_tree_trunk.jpg"))
    assert img_tree is not None

    hazards = hazard_detector.detect_hazards(img_tree)
    tree_obs = [h for h in hazards if h.label == "tree"]
    assert len(tree_obs) >= 1, "Tree should be detected!"
    tree = tree_obs[0]
    assert tree.effective_radius_m >= 0.20, "Tree must include root ring padding!"
    assert tree.in_walking_lane is True


def test_tree_detected_via_leaves_density_alone(hazard_detector):
    """
    Verifies that trees can be detected based on density of leaves / canopy alone,
    even if the trunk is not visible (e.g. low-hanging branches in walking corridor).
    """
    img_leaves = cv2.imread(str(TEST_FRAMES_DIR / "frame_12_tree_leaves_only.jpg"))
    assert img_leaves is not None

    hazards = hazard_detector.detect_hazards(img_leaves)
    tree_obs = [h for h in hazards if h.label == "tree"]
    assert len(tree_obs) >= 1, "Tree should be detected via leaf/foliage density even when trunk is not visible!"
    tree = tree_obs[0]
    assert tree.in_walking_lane is True
    assert tree.confidence >= 0.70


def test_velocity_tracking_moving_vs_parked():
    """
    Verifies that CentroidTracker correctly computes approach velocity
    and classifies two-wheelers / four-wheelers as 'moving' vs 'parked'.
    """
    tracker = CentroidTracker()

    # Frame 1: Car detected at distance 4.0m, t=100.0
    obs1 = DetectedObstacle(
        label="four_wheeler",
        confidence=0.88,
        bbox=(200, 200, 440, 360),
        bbox_normalized=(200/640, 200/480, 440/640, 360/480),
        distance_m=4.0,
        in_walking_lane=True,
        horizontal_position="center"
    )
    tracker.update([obs1], timestamp=100.0)
    assert obs1.tracking_id is not None
    assert obs1.is_moving is False
    assert obs1.state == "parked"

    # Frame 2: Car approached to distance 3.2m at t=100.5 (dt = 0.5s, delta = 0.8m -> v = 1.6 m/s)
    obs2 = DetectedObstacle(
        label="four_wheeler",
        confidence=0.90,
        bbox=(190, 190, 450, 370),
        bbox_normalized=(190/640, 190/480, 450/640, 370/480),
        distance_m=3.2,
        in_walking_lane=True,
        horizontal_position="center"
    )
    tracker.update([obs2], timestamp=100.5)
    assert obs2.tracking_id == obs1.tracking_id
    assert obs2.is_moving is True
    assert obs2.state == "moving"
    assert obs2.velocity_mps >= 1.2
    assert obs2.urgency == "critical"  # Approaching in walking lane


def test_video_source_image_directory():
    """Verifies that VideoSource correctly reads and loops image directories."""
    with VideoSource(source=TEST_FRAMES_DIR, loop_file=True) as v_src:
        assert v_src.is_opened is True
        ret1, frame1 = v_src.read_frame()
        assert ret1 is True
        assert frame1 is not None
        assert frame1.shape == (480, 640, 3)

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


def test_shadow_not_detected_as_pothole(hazard_detector):
    """
    Verifies that a dark floor shadow is NOT detected as a pothole
    because it lacks internal structural distortion / texture disorder.
    """
    img_path = TEST_FRAMES_DIR / "frame_07_shadow.jpg"
    frame = cv2.imread(str(img_path))
    assert frame is not None

    hazards = hazard_detector.detect_hazards(frame)
    potholes = [h for h in hazards if h.label == "pothole"]
    assert len(potholes) == 0, "Normal floor shadow should NOT be detected as a pothole!"
