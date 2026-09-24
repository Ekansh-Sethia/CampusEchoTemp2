"""
Unit tests for Phase 5:
- ObstacleStore (SQLite persistence & decay)
- FastAPI REST + WebSocket sync (multi-user simulation)
"""
import json
import math
import os
import tempfile
import time
import pytest
from fastapi.testclient import TestClient

from src.db.obstacle_store import ObstacleStore
from src.decision.hazard_memory import HazardRecord


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_store(tmp_path):
    """Creates a temporary ObstacleStore backed by a temp SQLite file."""
    db_path = str(tmp_path / "test_obstacles.db")
    return ObstacleStore(db_path=db_path)


def make_record(
    obstacle_id="obs_001",
    edge_id="edge_turn_to_atc",
    label="pothole",
    confidence=0.85,
    initial_weight=300.0,
    decay_tau_s=120.0,
    reported_by="user_1",
) -> HazardRecord:
    now = time.time()
    return HazardRecord(
        obstacle_id=obstacle_id,
        edge_id=edge_id,
        label=label,
        confidence=confidence,
        initial_weight=initial_weight,
        active_weight=initial_weight,
        decay_tau_s=decay_tau_s,
        first_seen=now,
        last_confirmed=now,
        reported_by=reported_by,
    )


# ─── ObstacleStore Tests ───────────────────────────────────────────────────────

class TestObstacleStore:
    def test_upsert_and_retrieve(self, tmp_store):
        rec = make_record()
        tmp_store.upsert(rec)
        active = tmp_store.get_active()
        assert len(active) == 1
        assert active[0].label == "pothole"
        assert active[0].obstacle_id == "obs_001"

    def test_upsert_updates_existing(self, tmp_store):
        rec = make_record(confidence=0.70)
        tmp_store.upsert(rec)
        # Upsert again with higher confidence
        rec2 = make_record(confidence=0.90)
        tmp_store.upsert(rec2)
        active = tmp_store.get_active()
        assert len(active) == 1
        assert active[0].confidence == 0.90  # MAX(0.70, 0.90)

    def test_decay_reduces_weight(self, tmp_store):
        rec = make_record(decay_tau_s=120.0, initial_weight=300.0)
        tmp_store.upsert(rec)
        # Simulate 120 seconds passed (one τ → ~37% weight)
        future_time = rec.last_confirmed + 120.0
        tmp_store.decay_tick(now=future_time)
        active = tmp_store.get_active()
        assert len(active) == 1
        expected = round(300.0 * math.exp(-1.0), 3)
        assert abs(active[0].active_weight - expected) < 2.0

    def test_decay_prunes_stale_records(self, tmp_store):
        rec = make_record(decay_tau_s=90.0, initial_weight=300.0)
        tmp_store.upsert(rec)
        far_future = rec.last_confirmed + 90.0 * 15  # Way past stale floor
        pruned = tmp_store.decay_tick(now=far_future)
        assert rec.obstacle_id in pruned
        assert tmp_store.count() == 0

    def test_manual_remove(self, tmp_store):
        rec = make_record()
        tmp_store.upsert(rec)
        removed = tmp_store.remove(rec.obstacle_id)
        assert removed is True
        assert tmp_store.count() == 0

    def test_remove_nonexistent_returns_false(self, tmp_store):
        removed = tmp_store.remove("does_not_exist")
        assert removed is False

    def test_clear_edge(self, tmp_store):
        r1 = make_record(obstacle_id="o1", edge_id="edge_a")
        r2 = make_record(obstacle_id="o2", edge_id="edge_a")
        r3 = make_record(obstacle_id="o3", edge_id="edge_b")
        tmp_store.upsert(r1)
        tmp_store.upsert(r2)
        tmp_store.upsert(r3)
        removed_count = tmp_store.clear_edge("edge_a")
        assert removed_count == 2
        assert tmp_store.count() == 1  # Only edge_b remains

    def test_multiple_users_upsert(self, tmp_store):
        r1 = make_record(obstacle_id="u1_obs", edge_id="edge_a", reported_by="user_1")
        r2 = make_record(obstacle_id="u2_obs", edge_id="edge_b", reported_by="user_2")
        tmp_store.upsert(r1)
        tmp_store.upsert(r2)
        active = tmp_store.get_active()
        assert len(active) == 2
        reporters = {r.reported_by for r in active}
        assert "user_1" in reporters
        assert "user_2" in reporters


# ─── FastAPI Server Tests ──────────────────────────────────────────────────────

@pytest.fixture
def api_client(tmp_path):
    """Creates a TestClient with a fresh temporary database."""
    import src.api.server as srv_module
    # Override the store with a temp one for testing isolation
    srv_module.store = ObstacleStore(db_path=str(tmp_path / "api_test.db"))
    from fastapi.testclient import TestClient
    return TestClient(srv_module.app)


class TestFastAPIServer:
    def test_health_check(self, api_client):
        r = api_client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_get_status_empty(self, api_client):
        r = api_client.get("/status")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["hazards"] == []

    def test_post_obstacle_and_retrieve(self, api_client):
        payload = {
            "edge_id": "edge_turn_to_atc",
            "label": "pothole",
            "confidence": 0.88,
            "decay_tau_s": 120.0,
            "penalty_weight": 300.0,
            "reported_by": "user_1",
        }
        r = api_client.post("/obstacles", json=payload)
        assert r.status_code == 200
        obs = r.json()
        assert obs["label"] == "pothole"
        assert obs["edge_id"] == "edge_turn_to_atc"
        assert obs["active_weight"] == 300.0

        # Verify it appears in /status
        r2 = api_client.get("/status")
        assert r2.json()["count"] == 1

    def test_clear_obstacle(self, api_client):
        payload = {
            "edge_id": "edge_a",
            "label": "car",
            "confidence": 0.85,
            "obstacle_id": "test_car_001",
        }
        api_client.post("/obstacles", json=payload)
        r = api_client.post("/obstacles/test_car_001/clear")
        assert r.status_code == 200
        assert r.json()["status"] == "cleared"
        # Confirm removed
        r2 = api_client.get("/status")
        assert r2.json()["count"] == 0

    def test_clear_nonexistent_returns_404(self, api_client):
        r = api_client.post("/obstacles/does_not_exist/clear")
        assert r.status_code == 404

    def test_websocket_snapshot_on_connect(self, api_client):
        """WebSocket client receives a snapshot immediately on connection."""
        with api_client.websocket_connect("/ws/telemetry") as ws:
            data = ws.receive_text()
            msg = json.loads(data)
            assert msg["event"] == "snapshot"
            assert "hazards" in msg

    def test_websocket_receives_obstacle_broadcast(self, api_client):
        """Posting an obstacle broadcasts to connected WebSocket clients."""
        with api_client.websocket_connect("/ws/telemetry") as ws:
            ws.receive_text()  # consume initial snapshot

            # Post obstacle via REST (from "User 1")
            api_client.post("/obstacles", json={
                "edge_id": "edge_x",
                "label": "stone",
                "confidence": 0.82,
            })

            # WebSocket client ("User 2") receives broadcast
            broadcast = json.loads(ws.receive_text())
            assert broadcast["event"] == "obstacle_reported"
            assert broadcast["obstacle"]["label"] == "stone"

    def test_websocket_ping_pong(self, api_client):
        with api_client.websocket_connect("/ws/telemetry") as ws:
            ws.receive_text()  # consume snapshot
            ws.send_text(json.dumps({"cmd": "ping"}))
            response = json.loads(ws.receive_text())
            assert response["event"] == "pong"
