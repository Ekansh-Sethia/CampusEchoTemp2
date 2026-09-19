"""Dijkstra pathfinding and turn-by-turn guidance generator."""
from typing import List, Optional, Tuple
import networkx as nx
from pydantic import BaseModel
from .graph import CampusGraph


class NavigationStep(BaseModel):
    """A single turn-by-turn navigation step along a route."""
    step_number: int
    from_node_id: str
    from_node_label: str
    to_node_id: str
    to_node_label: str
    distance_m: float
    turn_direction: str  # straight, left, right
    instruction: str     # Spoken-friendly instruction
    landmark_label: Optional[str] = None
    has_active_hazard: bool = False
    hazard_description: Optional[str] = None


class RouteResult(BaseModel):
    """Complete route output with metadata, turn-by-turn steps, and audio summary."""
    source_id: str
    destination_id: str
    path: List[str]                  # List of node IDs
    path_labels: List[str]           # Human-readable labels
    total_distance_m: float          # Real physical distance
    effective_weight: float          # Distance + obstacle penalties
    steps: List[NavigationStep]
    is_rerouted: bool = False
    contains_hazards: bool = False
    voice_summary: str


class DijkstraRouter:
    """Computes shortest paths over the CampusGraph with dynamic obstacle penalties."""

    def __init__(self, graph: CampusGraph):
        self.graph = graph

    def find_route(self, source: str, destination: str) -> RouteResult:
        """
        Calculates the optimal route from source to destination using Dijkstra's algorithm.
        Incorporates any active obstacle penalties on edges.
        """
        if source not in self.graph.nodes:
            raise ValueError(f"Unknown source node: {source}")
        if destination not in self.graph.nodes:
            raise ValueError(f"Unknown destination node: {destination}")

        try:
            path = nx.dijkstra_path(
                self.graph.nx_graph,
                source=source,
                target=destination,
                weight="weight"
            )
        except nx.NetworkXNoPath:
            raise RuntimeError(f"No navigable path exists between {source} and {destination}")

        return self._build_route_result(source, destination, path)

    def recalculate_route(
        self,
        current_node: str,
        destination: str,
        blocked_edge: Optional[Tuple[str, str]] = None,
        penalty_weight: float = 300.0,
        obstacle_id: str = "obstacle_blocked"
    ) -> RouteResult:
        """
        Applies a penalty to the blocked edge and computes a rerouted path to the destination.
        """
        if blocked_edge:
            u, v = blocked_edge
            self.graph.add_edge_penalty(
                u, v,
                penalty_weight=penalty_weight,
                obstacle_id=obstacle_id,
                description="Dynamic rerouting triggered by obstacle"
            )

        result = self.find_route(current_node, destination)
        result.is_rerouted = True
        return result

    def _build_route_result(self, source: str, destination: str, path: List[str]) -> RouteResult:
        """Constructs detailed steps, physical distances, and spoken instructions for a path."""
        steps: List[NavigationStep] = []
        total_physical_distance = 0.0
        total_effective_weight = 0.0
        contains_hazards = False

        path_labels = [self.graph.nodes[n].label for n in path]

        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]

            edge = self.graph.get_edge(u, v)
            if not edge:
                continue

            phys_dist = edge.distance_m
            eff_weight = self.graph.get_effective_weight(u, v)
            total_physical_distance += phys_dist
            total_effective_weight += eff_weight

            direction = self.graph.get_turn_direction(u, v)
            to_node = self.graph.nodes[v]
            from_node = self.graph.nodes[u]

            # Check if this edge has active penalties
            edge_id = self.graph.get_edge_id(u, v)
            active_penalties = self.graph.penalties.get(edge_id, [])
            has_hazard = len(active_penalties) > 0
            hazard_desc = active_penalties[0].description if has_hazard else None
            if has_hazard:
                contains_hazards = True

            # Format natural turn instruction
            instruction = self._generate_step_instruction(
                direction=direction,
                distance_m=phys_dist,
                target_label=to_node.name,
                is_destination=(i == len(path) - 2),
                has_hazard=has_hazard
            )

            steps.append(NavigationStep(
                step_number=i + 1,
                from_node_id=u,
                from_node_label=from_node.label,
                to_node_id=v,
                to_node_label=to_node.label,
                distance_m=phys_dist,
                turn_direction=direction,
                instruction=instruction,
                landmark_label=to_node.label,
                has_active_hazard=has_hazard,
                hazard_description=hazard_desc
            ))

        dest_node = self.graph.nodes[destination]
        voice_summary = (
            f"Heading to {dest_node.name}. "
            f"Total distance: {int(total_physical_distance)} meters across {len(steps)} steps."
        )

        return RouteResult(
            source_id=source,
            destination_id=destination,
            path=path,
            path_labels=path_labels,
            total_distance_m=round(total_physical_distance, 1),
            effective_weight=round(total_effective_weight, 1),
            steps=steps,
            contains_hazards=contains_hazards,
            voice_summary=voice_summary
        )

    def _generate_step_instruction(
        self,
        direction: str,
        distance_m: float,
        target_label: str,
        is_destination: bool,
        has_hazard: bool = False
    ) -> str:
        """Generates concise, unambiguous spoken navigation commands."""
        dist_int = int(round(distance_m))
        hazard_prefix = "Caution: obstacle reported on this path. " if has_hazard else ""

        if direction == "straight":
            if is_destination:
                return f"{hazard_prefix}Walk straight for {dist_int} meters to reach {target_label}."
            return f"{hazard_prefix}Walk straight for {dist_int} meters towards {target_label}."
        elif direction in ("left", "right"):
            if is_destination:
                return f"{hazard_prefix}Turn {direction} and walk {dist_int} meters to arrive at {target_label}."
            return f"{hazard_prefix}Turn {direction} and walk {dist_int} meters towards {target_label}."
        else:
            return f"{hazard_prefix}Proceed {dist_int} meters to {target_label}."
