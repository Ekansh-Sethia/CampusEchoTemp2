"""Unit tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["nodes_loaded"] == 8


def test_get_landmarks(client):
    response = client.get("/api/landmarks")
    assert response.status_code == 200
    landmarks = response.json()
    assert len(landmarks) == 8
    landmark_ids = [l["id"] for l in landmarks]
    assert "golden_gate" in landmark_ids
    assert "atc_building" in landmark_ids
    assert "silveria_hall" in landmark_ids


def test_compute_route_api(client):
    # Route: Golden Gate -> ATC Building
    response = client.post("/api/route", json={
        "source": "golden_gate",
        "destination": "atc_building"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["path"] == ["golden_gate", "golden_gate_turn", "atc_building"]
    assert data["total_distance_m"] == 108.0
    assert len(data["steps"]) == 2


def test_dynamic_rerouting_api(client):
    # 1. Normal route: ATC -> Silveria
    resp1 = client.post("/api/route", json={
        "source": "atc_building",
        "destination": "silveria_hall"
    })
    assert resp1.status_code == 200
    assert resp1.json()["path"] == ["atc_building", "atc_junction", "silveria_hall"]

    # 2. Add penalty on direct path
    resp2 = client.post("/api/penalty", json={
        "from_node": "atc_junction",
        "to_node": "silveria_hall",
        "penalty_weight": 300.0,
        "obstacle_id": "test_chair",
        "description": "Chair blocking hallway"
    })
    assert resp2.status_code == 200

    # 3. Request route again - should divert via Plus Point
    resp3 = client.post("/api/route", json={
        "source": "atc_building",
        "destination": "silveria_hall"
    })
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["path"] == ["atc_building", "atc_junction", "plus_point", "silveria_hall"]
    assert data3["total_distance_m"] == 163.0

    # 4. Clear penalties
    resp4 = client.delete("/api/penalty")
    assert resp4.status_code == 200

    # 5. Route reverts to normal
    resp5 = client.post("/api/route", json={
        "source": "atc_building",
        "destination": "silveria_hall"
    })
    assert resp5.json()["path"] == ["atc_building", "atc_junction", "silveria_hall"]
