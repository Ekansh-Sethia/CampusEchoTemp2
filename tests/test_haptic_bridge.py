"""
Unit and integration tests for the ESP32 Haptic Wristband Bridge (campusecho_haptic_wristband.ino).

Tests:
  - Protocol translation (CampusEcho internal protocol <-> ESP32 CSV format)
  - Clamping, direct CSV passthrough, and safety shutdown handling
  - Serial transport with mocked serial.Serial
  - Port discovery and heuristic detection
  - ModeRouter integration (DUAL, HAPTIC_ONLY, VOICE_ONLY)
  - FastAPI REST endpoints for hardware wristband control
"""
import time
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.notifications.haptic_bridge import HapticBridge, PATTERN_TRANSLATION_MAP
from src.notifications.mode_router import ModeRouter, OutputMode, DispatchResult
from src.notifications.haptic_encoder import HapticEncoder
from src.decision.confidence_policy import PolicyDecision, ConfidenceTier
from src.routing.navigator import NavigationEvent, NavigationStep
from src.api.server import app, haptic_bridge as global_bridge


# ─── Protocol Translation Tests ───────────────────────────────────────────────

class TestHapticBridgeProtocol:
    def test_translate_turn_left(self):
        # L7P2 -> Left motor, intensity 7, pattern 3 (double-pulse)
        assert HapticBridge.translate_to_firmware("L7P2") == "L,7,3\n"

    def test_translate_turn_right(self):
        # R7P2 -> Right motor, intensity 7, pattern 3 (double-pulse)
        assert HapticBridge.translate_to_firmware("R7P2") == "R,7,3\n"

    def test_translate_walk_straight(self):
        # B3P1 -> Both motors, intensity 3, pattern 1 (slow pulse)
        assert HapticBridge.translate_to_firmware("B3P1") == "B,3,1\n"

    def test_translate_blocked_alert(self):
        # B9P3 -> Both motors, intensity 9, pattern 2 (rapid pulse)
        assert HapticBridge.translate_to_firmware("B9P3") == "B,9,2\n"

    def test_translate_hedge_alert(self):
        # B5P2 -> Both motors, intensity 5, pattern 3 (double-pulse)
        assert HapticBridge.translate_to_firmware("B5P2") == "B,5,3\n"

    def test_translate_escalate_alert(self):
        # B9P5 -> Both motors, intensity 9, pattern 3 (critical double-pulse)
        assert HapticBridge.translate_to_firmware("B9P5") == "B,9,3\n"

    def test_translate_arrival(self):
        # B7P4 -> Both motors, intensity 7, pattern 0 (continuous vibration)
        assert HapticBridge.translate_to_firmware("B7P4") == "B,7,0\n"

    def test_translate_walk_start(self):
        # B4P1 -> Both motors, intensity 4, pattern 1 (slow pulse)
        assert HapticBridge.translate_to_firmware("B4P1") == "B,4,1\n"

    def test_translate_approaching_waypoint(self):
        # B3P2 -> Both motors, intensity 3, pattern 3 (double-pulse)
        assert HapticBridge.translate_to_firmware("B3P2") == "B,3,3\n"

    def test_translate_silence_and_off(self):
        assert HapticBridge.translate_to_firmware("O0P0") == "O,0,0\n"
        assert HapticBridge.translate_to_firmware("OFF") == "O,0,0\n"
        assert HapticBridge.translate_to_firmware("STOP") == "O,0,0\n"
        assert HapticBridge.translate_to_firmware("O") == "O,0,0\n"

    def test_translate_raw_csv_passthrough(self):
        assert HapticBridge.translate_to_firmware("L,7,2") == "L,7,2\n"
        assert HapticBridge.translate_to_firmware("R,3,1\n") == "R,3,1\n"
        assert HapticBridge.translate_to_firmware("B,9,3") == "B,9,3\n"
        assert HapticBridge.translate_to_firmware("O,0,0") == "O,0,0\n"

    def test_translate_clamping(self):
        # Intensity clamped to 0..9, pattern clamped to 0..3
        assert HapticBridge.translate_to_firmware("L,25,9") == "L,9,3\n"

    def test_translate_empty_or_invalid_defaults_to_off(self):
        assert HapticBridge.translate_to_firmware("") == "O,0,0\n"
        assert HapticBridge.translate_to_firmware("gibberish") == "O,0,0\n"


# ─── Mocked Serial Transport Tests ────────────────────────────────────────────

class TestHapticBridgeTransport:
    @pytest.fixture
    def mock_serial(self):
        mock_instance = MagicMock()
        mock_instance.is_open = True
        return mock_instance

    def test_connect_success(self, mock_serial):
        with patch("serial.Serial", return_value=mock_serial):
            bridge = HapticBridge()
            success = bridge.connect("COM5", baudrate=115200)
            assert success is True
            assert bridge.is_connected is True
            assert bridge.port == "COM5"
            bridge.close()

    def test_connect_failure(self):
        with patch("serial.Serial", side_effect=Exception("Port not found")):
            bridge = HapticBridge()
            success = bridge.connect("COM99", baudrate=115200)
            assert success is False
            assert bridge.is_connected is False
            assert bridge.error_count == 1
            bridge.close()

    def test_send_haptic_writes_to_serial(self, mock_serial):
        with patch("serial.Serial", return_value=mock_serial):
            bridge = HapticBridge()
            bridge.connect("COM5")
            bridge.send_haptic("L7P2")

            # Allow background worker thread to process queue
            time.sleep(0.3)
            mock_serial.write.assert_called_with(b"L,7,3\n")
            assert bridge.tx_count >= 1
            assert bridge.last_cmd == "L,7,3"
            bridge.close()

    def test_send_raw_writes_to_serial(self, mock_serial):
        with patch("serial.Serial", return_value=mock_serial):
            bridge = HapticBridge()
            bridge.connect("COM5")
            bridge.send_raw("B,9,2\n")

            time.sleep(0.3)
            mock_serial.write.assert_called_with(b"B,9,2\n")
            assert bridge.last_cmd == "B,9,2"
            bridge.close()

    def test_silence_sends_off_command(self, mock_serial):
        with patch("serial.Serial", return_value=mock_serial):
            bridge = HapticBridge()
            bridge.connect("COM5")
            bridge.silence()

            time.sleep(0.3)
            mock_serial.write.assert_called_with(b"O,0,0\n")
            bridge.close()

    def test_disconnect_cleans_up(self, mock_serial):
        with patch("serial.Serial", return_value=mock_serial):
            bridge = HapticBridge()
            bridge.connect("COM5")
            bridge.disconnect()
            assert bridge.is_connected is False
            mock_serial.close.assert_called_once()
            bridge.close()

    def test_serial_write_error_handling(self, mock_serial):
        mock_serial.write.side_effect = Exception("Write timeout")
        with patch("serial.Serial", return_value=mock_serial):
            bridge = HapticBridge()
            bridge.connect("COM5")
            bridge.send_haptic("B9P3")

            time.sleep(0.3)
            assert bridge.error_count >= 1
            assert bridge.is_connected is False
            bridge.close()


# ─── Port Discovery Tests ─────────────────────────────────────────────────────

class TestHapticBridgePortDiscovery:
    def test_list_ports_empty(self):
        with patch("serial.tools.list_ports.comports", return_value=[]):
            ports = HapticBridge.list_ports()
            assert ports == []

    def test_find_wristband_port_by_name(self):
        mock_port = MagicMock()
        mock_port.device = "COM7"
        mock_port.description = "CampusEcho-Wristband Serial"
        mock_port.hwid = "USB\\VID_303A&PID_1001"

        with patch("serial.tools.list_ports.comports", return_value=[mock_port]):
            detected = HapticBridge.find_wristband_port()
            assert detected == "COM7"

    def test_find_wristband_port_by_bluetooth_desc(self):
        mock_port = MagicMock()
        mock_port.device = "COM4"
        mock_port.description = "Standard Serial over Bluetooth link (COM4)"
        mock_port.hwid = "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}"

        with patch("serial.tools.list_ports.comports", return_value=[mock_port]):
            detected = HapticBridge.find_wristband_port()
            assert detected == "COM4"


# ─── ModeRouter Integration Tests ─────────────────────────────────────────────

def make_test_decision(tier: ConfidenceTier, spoken: str = "Test instruction") -> PolicyDecision:
    return PolicyDecision(
        tier=tier,
        obstacle_label="pothole",
        effective_confidence=0.85,
        raw_confidence=0.85,
        shadow_likelihood=0.0,
        in_walking_lane=True,
        distance_m=2.0,
        spoken_instruction=spoken,
        reroute_triggered=(tier == ConfidenceTier.BLOCKED),
        escalation_triggered=(tier == ConfidenceTier.ESCALATE),
        decay_tau_s=120.0,
    )


class TestHapticBridgeModeRouterIntegration:
    @pytest.fixture
    def bridge(self):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        with patch("serial.Serial", return_value=mock_serial):
            b = HapticBridge()
            b.connect("COM5")
            b._mock_serial = mock_serial
            yield b
            b.close()

    def test_mode_router_nav_event_fires_bridge(self, bridge):
        router = ModeRouter(mode=OutputMode.DUAL)
        router.register_callback(bridge.on_dispatch)

        step = NavigationStep(
            step_number=1,
            from_node_id="golden_gate",
            from_node_label="Golden Gate",
            to_node_id="golden_gate_turn",
            to_node_label="Turn to ATC",
            distance_m=58.0,
            turn_direction="left",
            instruction="Turn left towards ATC Building",
        )
        event = NavigationEvent(
            event_type="TURN_INSTRUCTION",
            node_id="golden_gate_turn",
            node_label="Turn to ATC",
            matched_sign="ATC Sign",
            current_step=step,
            voice_instruction=step.instruction,
            remaining_distance_m=58.0,
        )
        router.handle_nav_event(event)

        time.sleep(0.3)
        # Turn left is L7P2 -> translates to L,7,3\n
        bridge._mock_serial.write.assert_called_with(b"L,7,3\n")

    def test_mode_router_blocked_decision_fires_bridge(self, bridge):
        router = ModeRouter(mode=OutputMode.HAPTIC_ONLY)
        router.register_callback(bridge.on_dispatch)

        decision = make_test_decision(ConfidenceTier.BLOCKED, "Warning! Obstacle blocking corridor.")
        router.handle_decision(decision)

        time.sleep(0.3)
        # BLOCKED is B9P3 -> translates to B,9,2\n
        bridge._mock_serial.write.assert_called_with(b"B,9,2\n")

    def test_voice_only_mode_silences_bridge(self, bridge):
        router = ModeRouter(mode=OutputMode.VOICE_ONLY)
        router.register_callback(bridge.on_dispatch)

        decision = make_test_decision(ConfidenceTier.BLOCKED, "Warning!")
        router.handle_decision(decision)

        time.sleep(0.3)
        # In VOICE_ONLY mode, physical motors are silenced with O,0,0\n
        bridge._mock_serial.write.assert_called_with(b"O,0,0\n")

    def test_switching_to_voice_only_mode_emits_silence(self, bridge):
        router = ModeRouter(mode=OutputMode.DUAL)
        router.register_callback(bridge.on_dispatch)
        router.set_mode(OutputMode.VOICE_ONLY)

        time.sleep(0.3)
        bridge._mock_serial.write.assert_called_with(b"O,0,0\n")


# ─── FastAPI REST Endpoint Tests ──────────────────────────────────────────────

class TestHapticBridgeApiEndpoints:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_get_haptic_ports(self, client):
        resp = client.get("/haptic/ports")
        assert resp.status_code == 200
        data = resp.json()
        assert "ports" in data
        assert "detected" in data

    def test_get_haptic_status(self, client):
        resp = client.get("/haptic/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "connected" in data
        assert "tx_count" in data
        assert "error_count" in data

    def test_post_haptic_test_command(self, client):
        resp = client.post("/haptic/test", json={"cmd": "B5P2"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "dispatched"
        assert data["command"] == "B5P2"

    def test_post_haptic_test_raw(self, client):
        resp = client.post("/haptic/test", json={"raw": "L,7,2"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "dispatched"
        assert data["command"] == "L,7,2"

    def test_post_haptic_disconnect(self, client):
        resp = client.post("/haptic/disconnect")
        assert resp.status_code == 200
        assert resp.json()["status"] == "disconnected"
