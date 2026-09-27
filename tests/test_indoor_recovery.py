"""
Unit & Integration Test Suite for Indoor Landmark Position Recovery.
Tests BLE smoothing, confidence scoring, QR fallback, topological graph routing,
safe low-confidence suppression, ESP32 command mapping, and API endpoints.
"""
import pytest
import time
from fastapi.testclient import TestClient

from backend.localization.gps import GPSSystem
from backend.localization.visual import VisualLocalizationSystem
from backend.localization.ble import BLELandmarkManager
from backend.localization.qr import QRValidator
from backend.localization.manager import LocalizationManager
from backend.navigation.map import IndoorMap
from backend.navigation.router import IndoorRouter
from backend.navigation.instructions import InstructionGenerator
from backend.communication.esp32 import ESP32Client
from backend.app import app


@pytest.fixture
def landmarks_config():
    return [
        {"id": "B1", "name": "Main Entrance", "floor": 0, "zone": "Entrance", "x": 0, "y": 0},
        {"id": "B2", "name": "Central Corridor", "floor": 0, "zone": "Corridor", "x": 5, "y": 0},
        {"id": "B3", "name": "Computer Lab", "floor": 0, "zone": "Lab", "x": 10, "y": 0},
        {"id": "B4", "name": "Staircase", "floor": 0, "zone": "Staircase", "x": 5, "y": 5},
        {"id": "B5", "name": "Library", "floor": 0, "zone": "Library", "x": 10, "y": 5},
    ]


@pytest.fixture
def indoor_map():
    m = IndoorMap()
    m.load()
    return m


# ── 1. BLE Hysteresis & Confidence Tests ──────────────────────────────

def test_ble_initial_detection(landmarks_config):
    mgr = BLELandmarkManager(landmarks_config)
    res = mgr.process_scan({"B1": -55.0, "B2": -85.0})
    assert res is not None
    assert res["landmark_id"] == "B1"
    assert res["zone"] == "Entrance"
    assert res["consecutive_scans"] == 1


def test_ble_smoothing_hysteresis(landmarks_config):
    """Spec Section 12: Do not change location after one noisy scan (e.g. B2, B2, B2, B3, B2)."""
    mgr = BLELandmarkManager(landmarks_config)
    # Establish at B2 with 3 scans
    for _ in range(3):
        mgr.process_scan({"B2": -50.0, "B3": -80.0})
    assert mgr.get_current_estimate()["landmark_id"] == "B2"

    # Single noisy scan where B3 is momentarily stronger
    noisy_res = mgr.process_scan({"B3": -48.0, "B2": -55.0})
    # Should still hold B2 because B3 has only 1 scan
    assert noisy_res["landmark_id"] == "B2"

    # Second noisy scan for B3
    noisy_res2 = mgr.process_scan({"B3": -48.0, "B2": -55.0})
    assert noisy_res2["landmark_id"] == "B2"

    # Third consecutive scan for B3 -> now it switches!
    switch_res = mgr.process_scan({"B3": -48.0, "B2": -55.0})
    assert switch_res["landmark_id"] == "B3"


def test_ble_confidence_thresholds(landmarks_config):
    """Spec Section 13: 0.75-1.00 HIGH, 0.50-0.74 MEDIUM, 0.00-0.49 LOW."""
    mgr = BLELandmarkManager(landmarks_config)
    # Strong signal with 3 matching scans -> HIGH
    for _ in range(3):
        mgr.process_scan({"B1": -48.0})
    assert mgr.calculate_confidence() >= 0.75
    assert mgr.get_confidence_level() == "HIGH"

    # Medium signal (-70 dBm) with 2 scans -> MEDIUM
    mgr.reset()
    mgr.process_scan({"B1": -70.0})
    mgr.process_scan({"B1": -70.0})
    conf = mgr.calculate_confidence()
    assert 0.40 <= conf <= 0.80

    # Very weak signal (-92 dBm) with 1 scan -> LOW
    mgr.reset()
    mgr.process_scan({"B1": -92.0})
    assert mgr.calculate_confidence() < 0.50
    assert mgr.get_confidence_level() == "LOW"


# ── 2. QR Fallback Tests ──────────────────────────────────────────────

def test_qr_payload_parsing(landmarks_config):
    qr = QRValidator(landmarks_config)
    assert qr.parse_payload("B3") == "B3"
    assert qr.parse_payload('{"type": "indoor_landmark", "id": "B4"}') == "B4"
    assert qr.parse_payload("campusecho://landmark/B5") == "B5"
    assert qr.parse_payload("INVALID_TAG") is None


def test_qr_recovery_confidence(landmarks_config):
    qr = QRValidator(landmarks_config)
    res = qr.process_qr_text("B2")
    assert res is not None
    assert res["source"] == "QR"
    assert res["landmark_id"] == "B2"
    assert res["confidence"] == 1.0
    assert res["confidence_level"] == "HIGH"


# ── 3. Localization Manager Priority Chain ───────────────────────────

def test_localization_manager_gps_priority(landmarks_config):
    gps = GPSSystem(initial_reliable=True, initial_confidence=0.90)
    ble = BLELandmarkManager(landmarks_config)
    mgr = LocalizationManager(landmarks_config, gps=gps, ble=ble)

    loc = mgr.get_current_location()
    assert loc["source"] == "GPS"


def test_localization_manager_ble_takeover(landmarks_config):
    gps = GPSSystem(initial_reliable=False, initial_confidence=0.10)
    ble = BLELandmarkManager(landmarks_config)
    mgr = LocalizationManager(landmarks_config, gps=gps, ble=ble)

    for _ in range(3):
        mgr.feed_ble_scan({"B2": -52.0})

    loc = mgr.get_current_location()
    assert loc["source"] == "BLE"
    assert loc["landmark_id"] == "B2"


def test_localization_manager_qr_takeover(landmarks_config):
    gps = GPSSystem(initial_reliable=False, initial_confidence=0.10)
    ble = BLELandmarkManager(landmarks_config)
    qr = QRValidator(landmarks_config)
    mgr = LocalizationManager(landmarks_config, gps=gps, ble=ble, qr=qr)

    # BLE has low confidence
    mgr.feed_ble_scan({"B2": -95.0})
    # User scans QR B4
    mgr.feed_qr_payload("B4")

    loc = mgr.get_current_location()
    assert loc["source"] == "QR"
    assert loc["landmark_id"] == "B4"
    assert loc["confidence"] == 1.0


def test_localization_manager_unknown_state(landmarks_config):
    gps = GPSSystem(initial_reliable=False, initial_confidence=0.10)
    ble = BLELandmarkManager(landmarks_config)
    mgr = LocalizationManager(landmarks_config, gps=gps, ble=ble)

    loc = mgr.get_current_location()
    assert loc["source"] == "UNKNOWN"
    assert loc["confidence"] == 0.0


# ── 4. Indoor Map & Router Tests ──────────────────────────────────────

def test_indoor_graph_connectivity(indoor_map):
    assert "B1" in indoor_map.nodes
    assert "B5" in indoor_map.nodes
    assert "B2" in indoor_map.get_neighbors("B1")
    assert "B3" in indoor_map.get_neighbors("B2")
    assert "B4" in indoor_map.get_neighbors("B2")
    assert "B5" in indoor_map.get_neighbors("B4")


def test_indoor_router_shortest_paths(indoor_map):
    router = IndoorRouter(indoor_map)

    # Test 1: B1 to B3
    p1 = router.find_route("B1", "B3")
    assert p1 == ["B1", "B2", "B3"]

    # Test 3: B3 to B5
    p3 = router.find_route("B3", "B5")
    assert p3 == ["B3", "B2", "B4", "B5"]

    # Test B1 to B5
    p_all = router.find_route("B1", "B5")
    assert p_all == ["B1", "B2", "B4", "B5"]


# ── 5. Safe Low-Confidence Behavior & Instruction Generator ───────────

def test_safe_low_confidence_behavior(indoor_map):
    """Spec Section 16: Safe low-confidence behavior suppresses directional commands."""
    gen = InstructionGenerator(indoor_map)

    # Low confidence location
    uncertain_loc = {
        "source": "UNKNOWN",
        "landmark_id": None,
        "confidence": 0.25,
    }
    inst = gen.generate_instruction(uncertain_loc, destination_id="B5")

    assert inst["safe_mode"] is True
    assert inst["command"] == "UNKNOWN"
    assert "uncertain" in inst["instruction"].lower()
    # Ensure directional commands were suppressed
    assert inst["command"] not in ("LEFT", "RIGHT", "FORWARD")


def test_instruction_directions(indoor_map):
    gen = InstructionGenerator(indoor_map)

    # At B1 en route to B3: next is B2 -> FORWARD
    loc_b1 = {"source": "BLE", "landmark_id": "B1", "confidence": 0.90}
    inst_b1 = gen.generate_instruction(loc_b1, "B3", ["B1", "B2", "B3"])
    assert inst_b1["command"] == "FORWARD"

    # At B2 en route to B5: next is B4 -> LEFT
    loc_b2 = {"source": "BLE", "landmark_id": "B2", "confidence": 0.90}
    inst_b2 = gen.generate_instruction(loc_b2, "B5", ["B2", "B4", "B5"])
    assert inst_b2["command"] == "LEFT"

    # Arrived at destination
    loc_b5 = {"source": "BLE", "landmark_id": "B5", "confidence": 0.90}
    inst_b5 = gen.generate_instruction(loc_b5, "B5", ["B5"])
    assert inst_b5["command"] == "ARRIVED"


# ── 6. ESP32 Client Tests ─────────────────────────────────────────────

def test_esp32_client_mappings():
    client = ESP32Client()
    assert client.COMMAND_ENDPOINTS["LEFT"] == "/left"
    assert client.COMMAND_ENDPOINTS["RIGHT"] == "/right"
    assert client.COMMAND_ENDPOINTS["FORWARD"] == "/forward"
    assert client.COMMAND_ENDPOINTS["STOP"] == "/stop"
    assert client.COMMAND_ENDPOINTS["UNKNOWN"] == "/unknown"
    assert client.SERIAL_FALLBACK_MAPPINGS["LEFT"] == "L,8,0\n"
    assert client.SERIAL_FALLBACK_MAPPINGS["RIGHT"] == "R,8,0\n"


# ── 7. REST API Endpoints ─────────────────────────────────────────────

def test_api_status_and_presets():
    client = TestClient(app)

    # Initial status
    resp = client.get("/api/indoor/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "current_location" in data
    assert "map" in data

    # Test 1 preset
    p1_resp = client.post("/api/indoor/test-preset", json={"preset": "test1_normal"})
    assert p1_resp.status_code == 200
    snap1 = p1_resp.json()["snapshot"]
    assert snap1["current_location"]["landmark_id"] == "B1"
    assert snap1["destination"]["id"] == "B3"
    assert snap1["route"] == ["B1", "B2", "B3"]

    # Test 4 preset (safe low confidence)
    p4_resp = client.post("/api/indoor/test-preset", json={"preset": "test4_confidence_drop"})
    assert p4_resp.status_code == 200
    snap4 = p4_resp.json()["snapshot"]
    assert snap4["instruction"]["safe_mode"] is True
    assert snap4["instruction"]["command"] in ("UNKNOWN", "STOP")

    # Test 5 preset (QR recovery)
    p5_resp = client.post("/api/indoor/test-preset", json={"preset": "test5_qr_recovery"})
    assert p5_resp.status_code == 200
    snap5 = p5_resp.json()["snapshot"]
    assert snap5["current_location"]["source"] == "QR"
    assert snap5["current_location"]["landmark_id"] == "B4"
    assert snap5["current_location"]["confidence"] >= 0.75


def test_api_update_landmarks():
    client = TestClient(app)

    # Update landmarks list
    new_landmarks = [
        {"id": "B1", "name": "Main Entrance", "floor": 0, "zone": "Entrance", "x": 0.0, "y": 0.0},
        {"id": "B2", "name": "Central Corridor", "floor": 0, "zone": "Corridor", "x": 6.0, "y": 0.0},
        {"id": "B3", "name": "Computer Lab", "floor": 0, "zone": "Lab", "x": 12.0, "y": 0.0},
        {"id": "B4", "name": "Staircase", "floor": 0, "zone": "Staircase", "x": 6.0, "y": 6.0},
        {"id": "B5", "name": "Library", "floor": 0, "zone": "Library", "x": 12.0, "y": 6.0},
        {"id": "B6", "name": "Robotics Studio", "floor": 0, "zone": "Studio", "x": 18.0, "y": 6.0},
    ]

    res = client.post("/api/indoor/landmarks", json={"landmarks": new_landmarks})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "landmarks_updated"
    assert data["count"] == 6

    # Verify status reflects 6 landmarks
    status_resp = client.get("/api/indoor/landmarks")
    assert status_resp.status_code == 200
    ids = [lm["id"] for lm in status_resp.json()]
    assert "B6" in ids

    # Reset back to default B1-B5
    reset_resp = client.post("/api/indoor/landmarks/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["count"] == 5
