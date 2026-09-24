"""
Unit and integration tests for Phase 3:
SignpostReader, LandmarkMatcher, and CampusNavigator.
"""
from pathlib import Path
import cv2
import pytest

from src.perception.text_reader import SignpostReader, SignDetection
from src.routing.graph import CampusGraph
from src.routing.landmark_matcher import LandmarkMatcher
from src.routing.navigator import CampusNavigator, NavigationEvent


@pytest.fixture
def campus_graph():
    graph_path = Path(__file__).parent.parent / "data" / "campus_graph.json"
    return CampusGraph(str(graph_path))


@pytest.fixture
def landmark_matcher(campus_graph):
    return LandmarkMatcher(campus_graph)


@pytest.fixture
def navigator(campus_graph):
    nav = CampusNavigator(campus_graph)
    nav.start_navigation("golden_gate", "silveria_hall")
    return nav


def test_text_normalization():
    raw_1 = "  [ATC] BUILDING!! \n"
    norm_1 = SignpostReader.normalize_text(raw_1)
    assert norm_1 == "ATC BUILDING"

    raw_2 = "golden gate / entrance..."
    norm_2 = SignpostReader.normalize_text(raw_2)
    assert norm_2 == "GOLDEN GATE / ENTRANCE"


def test_landmark_matcher_exact(landmark_matcher):
    match = landmark_matcher.match("ATC BUILDING", ocr_confidence=0.95)
    assert match is not None
    assert match.node_id == "atc_building"
    assert match.similarity_score >= 0.90
    assert match.combined_confidence >= 0.85


def test_landmark_matcher_fuzzy_typo(landmark_matcher):
    # Minor OCR character misrecognition
    match = landmark_matcher.match("G0LDEN GATE", ocr_confidence=0.88)
    assert match is not None
    assert match.node_id == "golden_gate"
    assert match.similarity_score >= 0.70


def test_landmark_matcher_substring(landmark_matcher):
    # Short substring match
    match = landmark_matcher.match("SILVERIA", ocr_confidence=0.90)
    assert match is not None
    assert match.node_id == "silveria_hall"
    assert match.similarity_score >= 0.75


def test_navigator_route_initialization(navigator):
    assert navigator.current_node_id == "golden_gate"
    assert navigator.destination_node_id == "silveria_hall"
    assert navigator.active_route is not None
    assert "atc_building" in navigator.active_route.path
    assert navigator.get_remaining_distance() > 0.0


def test_navigator_waypoint_advancement(navigator):
    # Simulate OCR detecting ATC Building sign while en route to Silveria Hall
    det = SignDetection(
        text="ATC BUILDING",
        raw_text="ATC BUILDING",
        confidence=0.92,
        bbox=(100, 70, 540, 190)
    )
    event = navigator.process_sign_detections([det])
    assert event is not None
    assert event.event_type == "WAYPOINT_REACHED"
    assert event.node_id == "atc_building"
    assert navigator.current_node_id == "atc_building"
    assert "atc_building" in navigator.passed_nodes
    assert "ATC Building" in event.voice_instruction


def test_navigator_destination_reached(navigator):
    # Simulate OCR detecting Silveria Hall destination sign
    det = SignDetection(
        text="SILVERIA HALL",
        raw_text="SILVERIA HALL",
        confidence=0.95,
        bbox=(100, 70, 540, 190)
    )
    event = navigator.process_sign_detections([det])
    assert event is not None
    assert event.event_type == "DESTINATION_REACHED"
    assert event.node_id == "silveria_hall"
    assert navigator.current_node_id == "silveria_hall"
    assert navigator.get_remaining_distance() == 0.0
    assert "Destination confirmed" in event.voice_instruction


def test_easyocr_synthetic_landmark_end_to_end(campus_graph):
    """End-to-end test reading a rendered landmark image with EasyOCR."""
    landmark_path = Path(__file__).parent.parent / "data" / "landmarks" / "atc_building.jpg"
    assert landmark_path.exists(), "Benchmark landmark image missing"

    img = cv2.imread(str(landmark_path))
    assert img is not None

    reader = SignpostReader(languages=["en"], gpu=False)
    detections = reader.read_signs(img, force=True)
    assert len(detections) > 0

    texts = [d.text for d in detections]
    assert any("ATC" in t for t in texts)

    # Match against graph
    matcher = LandmarkMatcher(campus_graph)
    best_match = matcher.match_best_detection(detections)
    assert best_match is not None
    assert best_match.node_id == "atc_building"
