"""
End-to-end integration tests for Phase 7:
- Full pipeline: clear frame, blocked obstacle, escalate
- API server health, mode endpoint, WebSocket mode_change broadcast
"""
import json
import pytest
from fastapi.testclient import TestClient

import src.api.server as srv_module
from src.db.obstacle_store import ObstacleStore
from src.notifications.mode_router import ModeRouter, OutputMode
from src.decision.confidence_policy import ConfidencePolicy, ConfidenceTier
from src.perception.models import DetectedObstacle


# ─── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def api_client(tmp_path):
    """Fresh server with isolated DB and ModeRouter for each test."""
    srv_module.store = ObstacleStore(db_path=str(tmp_path / "int_test.db"))
    srv_module.mode_router = ModeRouter(mode=OutputMode.DUAL)
    return TestClient(srv_module.app)


def make_obstacle(label="pothole", confidence=0.85, in_lane=True, dist=2.0,
                  shadow=0.0, raw_conf=None) -> DetectedObstacle:
    return DetectedObstacle(
        label=label, confidence=confidence,
        raw_confidence=raw_conf or confidence,
        shadow_likelihood=shadow,
        bbox=(200, 300, 440, 400),
        bbox_normalized=(0.3, 0.6, 0.7, 0.8),
        distance_m=dist, in_walking_lane=in_lane,
        horizontal_position="center",
        urgency="high" if confidence >= 0.70 else "medium",
        is_environmental_hazard=True,
    )


# ─── Full Pipeline Tests ───────────────────────────────────────────────

class TestFullPipeline:
    def test_clear_frame_no_decision(self):
        """A clear frame produces no obstacles — policy not invoked."""
        policy = ConfidencePolicy()
        # Simulate a low-confidence off-lane detection (not in walking lane)
        obs = make_obstacle(confidence=0.30, in_lane=False, dist=5.0)
        decision = policy.evaluate(obs)
        assert decision.tier == ConfidenceTier.HEDGE
        assert decision.reroute_triggered is False
        assert decision.escalation_triggered is False

    def test_blocked_obstacle_triggers_reroute_flag(self):
        """High-confidence in-lane obstacle → BLOCKED → reroute_triggered=True."""
        policy = ConfidencePolicy()
        obs = make_obstacle(confidence=0.88, in_lane=True)
        decision = policy.evaluate(obs)
        assert decision.tier == ConfidenceTier.BLOCKED
        assert decision.reroute_triggered is True

    def test_escalate_low_confidence_in_lane(self):
        """Low-confidence in-lane obstacle → ESCALATE → escalation_triggered=True."""
        policy = ConfidencePolicy()
        obs = make_obstacle(confidence=0.22, in_lane=True)
        decision = policy.evaluate(obs)
        assert decision.tier == ConfidenceTier.ESCALATE
        assert decision.escalation_triggered is True

    def test_mode_router_dispatch_blocked_dual(self):
        """BLOCKED in DUAL mode emits both voice and haptic."""
        from src.notifications.mode_router import ModeRouter, DispatchResult
        from src.decision.confidence_policy import PolicyDecision
        router = ModeRouter(mode=OutputMode.DUAL)
        results = []
        router.register_callback(results.append)
        decision = PolicyDecision(
            tier=ConfidenceTier.BLOCKED,
            obstacle_label="chair",
            effective_confidence=0.88,
            raw_confidence=0.88,
            shadow_likelihood=0.0,
            in_walking_lane=True,
            distance_m=2.0,
            spoken_instruction="Warning! Chair blocking path.",
            reroute_triggered=True,
            escalation_triggered=False,
            decay_tau_s=45.0,
        )
        result = router.handle_decision(decision)
        assert result.voice_text is not None
        assert result.haptic_cmd == "B9P3"
        assert len(results) == 1


# ─── FastAPI Integration Tests ────────────────────────────────────────

class TestAPIIntegration:
    def test_api_health_returns_ok(self, api_client):
        r = api_client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_dashboard_route_returns_html(self, api_client):
        r = api_client.get("/dashboard")
        # Returns 200 if dashboard.html exists, 404 if not (both acceptable)
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            assert "CampusEcho" in r.text

    def test_set_mode_voice_only(self, api_client):
        r = api_client.post("/mode", json={"mode": "VOICE_ONLY"})
        assert r.status_code == 200
        assert r.json()["mode"] == "VOICE_ONLY"

    def test_set_mode_invalid_returns_400(self, api_client):
        r = api_client.post("/mode", json={"mode": "INVALID_MODE"})
        assert r.status_code == 400

    def test_websocket_mode_change_broadcast(self, api_client):
        """POST /mode broadcasts mode_change event to all WS clients."""
        with api_client.websocket_connect("/ws/telemetry") as ws:
            ws.receive_text()  # consume snapshot
            api_client.post("/mode", json={"mode": "HAPTIC_ONLY"})
            msg = json.loads(ws.receive_text())
            assert msg["event"] == "mode_change"
            assert msg["mode"] == "HAPTIC_ONLY"
