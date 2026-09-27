"""Tests for the complete SGSITS Indore campus navigation graph."""
from pathlib import Path
import pytest
from src.routing.graph import CampusGraph
from src.routing.router import DijkstraRouter

GRAPH_PATH = Path(__file__).parent.parent / "data" / "sgsits_campus_graph_full.json"


@pytest.fixture
def sgsits_graph():
    return CampusGraph(str(GRAPH_PATH))


@pytest.fixture
def sgsits_router(sgsits_graph):
    return DijkstraRouter(sgsits_graph)


def test_sgsits_graph_structure(sgsits_graph):
    """Verifies that all 33 SGSITS campus nodes and 39 edges are loaded."""
    assert len(sgsits_graph.nodes) == 33
    assert len(sgsits_graph.edges) == 39

    # Key gates confirmed by user
    assert "golden_gate" in sgsits_graph.nodes
    assert "green_gate" in sgsits_graph.nodes
    assert "pnb_gate" in sgsits_graph.nodes

    # Core academic & student landmarks
    assert "atc_building" in sgsits_graph.nodes
    assert "silveria_hall" in sgsits_graph.nodes
    assert "plus_point" in sgsits_graph.nodes
    assert "canteen_gym" in sgsits_graph.nodes
    assert "lecture_theatres" in sgsits_graph.nodes
    assert "sports_complex" in sgsits_graph.nodes
    assert "ncc_unit" in sgsits_graph.nodes
    assert "dept_biomedical" in sgsits_graph.nodes
    assert "dept_ei" in sgsits_graph.nodes
    assert "admin_building" in sgsits_graph.nodes
    assert "central_library" in sgsits_graph.nodes
    assert "hostel_visvesvaraya" in sgsits_graph.nodes


def test_landmark_photos_mapped(sgsits_graph):
    """Verifies that user's GS Photos are attached to their corresponding nodes."""
    # Golden Gate
    gg = sgsits_graph.nodes["golden_gate"]
    assert "GS Photos/goldenGate_ag1.jpg" in gg.landmark_images
    assert len(gg.landmark_images) == 3

    # Green Gate & PNB Gate
    assert len(sgsits_graph.nodes["green_gate"].landmark_images) == 2
    assert len(sgsits_graph.nodes["pnb_gate"].landmark_images) == 4

    # Plus Point & Cafe
    assert len(sgsits_graph.nodes["plus_point"].landmark_images) == 4
    assert len(sgsits_graph.nodes["canteen_gym"].landmark_images) == 3

    # LT & Sports Complex
    assert len(sgsits_graph.nodes["lecture_theatres"].landmark_images) == 4
    assert len(sgsits_graph.nodes["sports_complex"].landmark_images) == 4

    # Departments & NCC
    assert sgsits_graph.nodes["atc_building"].landmark_image == "GS Photos/Atc.jpg"
    assert sgsits_graph.nodes["dept_biomedical"].landmark_image == "GS Photos/BMDept.jpg"
    assert sgsits_graph.nodes["dept_ei"].landmark_image == "GS Photos/EIDept.jpg"
    assert sgsits_graph.nodes["ncc_unit"].landmark_image == "GS Photos/NCC.jpg"


def test_core_measurements_preserved(sgsits_router):
    """Ensures user's verified field measurements are preserved in the full graph."""
    route_gg_atc = sgsits_router.find_route("golden_gate", "atc_building")
    assert route_gg_atc.total_distance_m == 108.0

    route_atc_silveria = sgsits_router.find_route("atc_building", "silveria_hall")
    assert route_atc_silveria.total_distance_m == 140.0

    route_atc_admin = sgsits_router.find_route("atc_building", "admin_building")
    assert route_atc_admin.total_distance_m == 267.0


def test_user_confirmed_pedestrian_routes(sgsits_router):
    """Verifies routes user explicitly confirmed: Plus Point to Cafe, dual gate entries, hostel avenue."""
    # 1. Plus Point directly to Cafe (open courtyard)
    route_pp_cafe = sgsits_router.find_route("plus_point", "canteen_gym")
    assert route_pp_cafe.total_distance_m == 65.0
    assert route_pp_cafe.path == ["plus_point", "canteen_gym"]

    # 2. Green Gate (Main Gate) dual paths
    # Via CS/IT
    route_gg_cs = sgsits_router.find_route("green_gate", "dept_cs_it")
    assert route_gg_cs.total_distance_m == 105.0

    # Via Sports / Volleyball
    route_gg_sports = sgsits_router.find_route("green_gate", "sports_complex")
    assert route_gg_sports.total_distance_m == 60.0

    # 3. PNB Gate entry to ATC
    route_pnb_atc = sgsits_router.find_route("pnb_gate", "atc_building")
    assert "sports_complex" in route_pnb_atc.path
    assert "lecture_theatres" in route_pnb_atc.path

    # 4. Hostels routed via Canteen & Sports ground (no route behind Silveria)
    route_atc_hostel = sgsits_router.find_route("atc_building", "hostel_visvesvaraya")
    assert "canteen_gym" in route_atc_hostel.path
    assert "silveria_hall" not in route_atc_hostel.path
