"""Unit tests for CampusGraph and DijkstraRouter."""
import pytest
from pathlib import Path
from src.routing.graph import CampusGraph
from src.routing.router import DijkstraRouter


GRAPH_PATH = Path(__file__).parent.parent / "data" / "campus_graph.json"


@pytest.fixture
def graph():
    """Initializes a CampusGraph from the real campus_graph.json."""
    return CampusGraph(str(GRAPH_PATH))


@pytest.fixture
def router(graph):
    """Initializes a DijkstraRouter instance."""
    return DijkstraRouter(graph)


def test_graph_loading(graph):
    """Verifies that all nodes and edges from campus_graph.json are correctly loaded."""
    assert len(graph.nodes) == 8
    assert len(graph.edges) == 8

    # Verify specific landmark nodes
    assert "golden_gate" in graph.nodes
    assert "atc_building" in graph.nodes
    assert "plus_point" in graph.nodes
    assert "silveria_hall" in graph.nodes
    assert "admin_building" in graph.nodes

    # Check node signs
    assert "ATC BUILDING" in graph.nodes["atc_building"].expected_signs
    assert "PLUS POINT" in graph.nodes["plus_point"].expected_signs


def test_route_golden_gate_to_atc(router):
    """
    Verifies user's exact measurement:
    golden gate to atc building = 58 m straight + 50 m left (total 108 m).
    """
    result = router.find_route("golden_gate", "atc_building")
    assert result.path == ["golden_gate", "golden_gate_turn", "atc_building"]
    assert result.total_distance_m == 108.0
    assert len(result.steps) == 2

    # Step 1: 58m straight
    assert result.steps[0].turn_direction == "straight"
    assert result.steps[0].distance_m == 58.0

    # Step 2: 50m left
    assert result.steps[1].turn_direction == "left"
    assert result.steps[1].distance_m == 50.0


def test_route_atc_to_silveria(router):
    """
    Verifies user's exact measurement:
    atc building to silveria hall = 13 m straight + 127 m right (total 140 m).
    """
    result = router.find_route("atc_building", "silveria_hall")
    assert result.path == ["atc_building", "atc_junction", "silveria_hall"]
    assert result.total_distance_m == 140.0
    assert len(result.steps) == 2

    # Step 1: 13m straight
    assert result.steps[0].turn_direction == "straight"
    assert result.steps[0].distance_m == 13.0

    # Step 2: 127m right
    assert result.steps[1].turn_direction == "right"
    assert result.steps[1].distance_m == 127.0


def test_route_atc_to_admin(router):
    """
    Verifies user's exact measurement:
    atc building to administrative building =
    13 m straight + 35 m right (plus point) + 68 m left + 151 m right (total 267 m).
    """
    result = router.find_route("atc_building", "admin_building")
    expected_path = [
        "atc_building",
        "atc_junction",
        "plus_point",
        "admin_path_turn",
        "admin_building"
    ]
    assert result.path == expected_path
    assert result.total_distance_m == 267.0
    assert len(result.steps) == 4

    # Step 1: 13m straight to junction
    assert result.steps[0].turn_direction == "straight"
    assert result.steps[0].distance_m == 13.0

    # Step 2: 35m right to Plus Point
    assert result.steps[1].turn_direction == "right"
    assert result.steps[1].distance_m == 35.0

    # Step 3: 68m left
    assert result.steps[2].turn_direction == "left"
    assert result.steps[2].distance_m == 68.0

    # Step 4: 151m right to Admin Building
    assert result.steps[3].turn_direction == "right"
    assert result.steps[3].distance_m == 151.0


def test_route_golden_gate_to_silveria_full(router):
    """Verifies end-to-end path from Golden Gate to Silveria Hall."""
    result = router.find_route("golden_gate", "silveria_hall")
    expected_path = [
        "golden_gate",
        "golden_gate_turn",
        "atc_building",
        "atc_junction",
        "silveria_hall"
    ]
    assert result.path == expected_path
    assert result.total_distance_m == 248.0
    assert "Heading to Silveria Hall" in result.voice_summary


def test_dynamic_rerouting_around_obstacle(graph, router):
    """
    Tests dynamic rerouting when the direct path between ATC junction
    and Silveria Hall is blocked by an obstacle.
    Should reroute via Plus Point courtyard alternate path.
    """
    # 1. Normal route
    normal_route = router.find_route("atc_building", "silveria_hall")
    assert normal_route.path == ["atc_building", "atc_junction", "silveria_hall"]
    assert normal_route.total_distance_m == 140.0

    # 2. Block the direct corridor with a high penalty
    rerouted = router.recalculate_route(
        current_node="atc_building",
        destination="silveria_hall",
        blocked_edge=("atc_junction", "silveria_hall"),
        penalty_weight=300.0,
        obstacle_id="obs_corridor_chair"
    )

    assert rerouted.is_rerouted is True
    # Alternate path traverses: atc_building -> atc_junction -> plus_point -> silveria_hall
    assert rerouted.path == ["atc_building", "atc_junction", "plus_point", "silveria_hall"]
    # Physical distance: 13 + 35 + 115 = 163m
    assert rerouted.total_distance_m == 163.0

    # 3. Clear the penalty and verify route reverts back
    graph.clear_penalties()
    reverted_route = router.find_route("atc_building", "silveria_hall")
    assert reverted_route.path == ["atc_building", "atc_junction", "silveria_hall"]
    assert reverted_route.total_distance_m == 140.0


def test_landmark_sign_search(graph):
    """Tests landmark lookup by OCR recognized text."""
    node_atc = graph.find_node_by_sign("ATC BUILDING")
    assert node_atc is not None
    assert node_atc.id == "atc_building"

    node_gate = graph.find_node_by_sign("Welcome at MAIN GATE")
    assert node_gate is not None
    assert node_gate.id == "golden_gate"

    node_plus = graph.find_node_by_sign("Meet at PLUS POINT")
    assert node_plus is not None
    assert node_plus.id == "plus_point"

    node_admin = graph.find_node_by_sign("ADMIN BLOCK")
    assert node_admin is not None
    assert node_admin.id == "admin_building"
