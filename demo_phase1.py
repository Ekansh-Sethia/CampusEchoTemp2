"""Interactive CLI Demo for Phase 1: CampusEcho Campus Graph & Dijkstra Routing."""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from src.routing.graph import CampusGraph
from src.routing.router import DijkstraRouter


def print_banner(title: str):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def display_route(result):
    print(f"\n[Route]: {' -> '.join(result.path_labels)}")
    print(f"[Physical Distance]: {result.total_distance_m} meters")
    print(f"[Voice Summary]: \"{result.voice_summary}\"")
    print("\n[Turn-by-Turn Guidance]:")
    for step in result.steps:
        hazard_tag = " [!] HAZARD WARNING" if step.has_active_hazard else ""
        print(f"   Step {step.step_number}: {step.instruction}{hazard_tag}")


def main():
    graph_path = Path(__file__).parent / "data" / "campus_graph.json"
    graph = CampusGraph(str(graph_path))
    router = DijkstraRouter(graph)

    print_banner("CampusEcho - Phase 1 Routing Engine Demo")
    print(f"Loaded Campus Graph: {len(graph.nodes)} landmarks/nodes, {len(graph.edges)} walkable pathways.")

    print("\nAvailable Landmarks:")
    for node_id, node in graph.nodes.items():
        print(f"  - {node_id:<18} : {node.label}")

    # 1. Golden Gate to ATC Building
    print_banner("1. Route: Golden Gate -> ATC Building")
    route1 = router.find_route("golden_gate", "atc_building")
    display_route(route1)

    # 2. ATC Building to Administrative Building
    print_banner("2. Route: ATC Building -> Administrative Building")
    route2 = router.find_route("atc_building", "admin_building")
    display_route(route2)

    # 3. ATC Building to Silveria Hall (Normal Path)
    print_banner("3. Normal Route: ATC Building -> Silveria Hall")
    route3 = router.find_route("atc_building", "silveria_hall")
    display_route(route3)

    # 4. Dynamic Obstacle Rerouting
    print_banner("4. Dynamic Rerouting: Obstacle Placed at ATC Junction -> Silveria Hall")
    print(">> Simulating YOLOv8 detecting obstacle (Chair) on pathway (atc_junction -> silveria_hall)...")
    print(">> Triggering Tier 1 (BLOCKED) -> Dijkstra recalculates path with +300m edge penalty...")

    rerouted = router.recalculate_route(
        current_node="atc_building",
        destination="silveria_hall",
        blocked_edge=("atc_junction", "silveria_hall"),
        penalty_weight=300.0,
        obstacle_id="obs_demo_chair"
    )
    display_route(rerouted)
    print("\n>> Notice how Dijkstra dynamically diverted through Plus Point (163m) instead of dead-ending!")

    # 5. Clearing Obstacle
    print_banner("5. Clearing Obstacle: Route Reverts to Optimal Path")
    print(">> Obstacle cleared. Resetting penalties...")
    graph.clear_penalties()
    reverted = router.find_route("atc_building", "silveria_hall")
    display_route(reverted)

    print_banner("Phase 1 Verification Complete!")


if __name__ == "__main__":
    main()
