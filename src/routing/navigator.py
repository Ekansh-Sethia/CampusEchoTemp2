"""
CampusNavigator: Stateful navigation tracking, landmark event handling,
and turn-by-turn guidance synchronization.
"""
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

from .graph import CampusGraph, Node
from .router import DijkstraRouter, RouteResult, NavigationStep
from .landmark_matcher import LandmarkMatcher, LandmarkMatchResult


class NavigationEvent(BaseModel):
    """Event emitted when the user's position updates or landmark is reached."""
    event_type: str                 # "DESTINATION_REACHED", "WAYPOINT_REACHED", "OFF_ROUTE_LANDMARK"
    node_id: str
    node_label: str
    matched_sign: str
    voice_instruction: str
    remaining_distance_m: float
    current_step: Optional[NavigationStep] = None


class CampusNavigator:
    """
    Tracks real-time user progress through the campus topological graph.
    Updates position when landmarks are recognized via OCR and provides
    context-aware voice guidance instructions.
    """

    def __init__(self, graph: CampusGraph):
        self.graph = graph
        self.router = DijkstraRouter(graph)
        self.matcher = LandmarkMatcher(graph)

        self.current_node_id: Optional[str] = None
        self.destination_node_id: Optional[str] = None
        self.active_route: Optional[RouteResult] = None
        self.current_step_index: int = 0
        self.passed_nodes: List[str] = []

    def start_navigation(self, start_node_id: str, destination_node_id: str) -> RouteResult:
        """
        Initializes a navigation route from start to destination.
        """
        if start_node_id not in self.graph.nodes:
            raise ValueError(f"Unknown start node: {start_node_id}")
        if destination_node_id not in self.graph.nodes:
            raise ValueError(f"Unknown destination node: {destination_node_id}")

        self.current_node_id = start_node_id
        self.destination_node_id = destination_node_id
        self.active_route = self.router.find_route(start_node_id, destination_node_id)
        self.current_step_index = 0
        self.passed_nodes = [start_node_id]

        return self.active_route

    def get_expected_forward_nodes(self) -> List[str]:
        """
        Returns upcoming node IDs along the active route that have not been passed yet.
        Used to prioritize OCR fuzzy matching for anticipated landmarks.
        """
        if not self.active_route:
            return list(self.graph.nodes.keys())

        path = self.active_route.path
        if self.current_node_id in path:
            current_idx = path.index(self.current_node_id)
            return path[current_idx + 1:]
        return path

    def get_current_instruction(self) -> str:
        """Returns the current step's voice instruction."""
        if not self.active_route or not self.active_route.steps:
            return "No active route."

        if self.current_step_index < len(self.active_route.steps):
            return self.active_route.steps[self.current_step_index].instruction
        return f"Arrived at destination: {self.graph.nodes[self.destination_node_id].label}"

    def get_remaining_distance(self) -> float:
        """Calculates remaining physical distance in meters to destination."""
        if not self.active_route or not self.active_route.steps:
            return 0.0

        remaining = 0.0
        for step in self.active_route.steps[self.current_step_index:]:
            remaining += step.distance_m
        return round(remaining, 1)

    def process_sign_detections(self, detections: List) -> Optional[NavigationEvent]:
        """
        Processes OCR sign detections against anticipated campus landmarks.
        If a recognized sign matches an upcoming waypoint or destination,
        updates the navigator's current location and returns a NavigationEvent.
        """
        if not detections or not self.active_route:
            return None

        # Prioritize forward nodes along the current path
        forward_nodes = self.get_expected_forward_nodes()
        match = self.matcher.match_best_detection(detections, candidate_node_ids=forward_nodes)

        # Fall back to searching any graph node if no forward node matched
        if not match:
            match = self.matcher.match_best_detection(detections, candidate_node_ids=None)

        if not match:
            return None

        return self._handle_landmark_match(match)

    def _handle_landmark_match(self, match: LandmarkMatchResult) -> NavigationEvent:
        """Advances route progress and constructs audio guidance."""
        matched_node_id = match.node_id
        node_label = match.node_label
        remaining_dist = self.get_remaining_distance()

        # Case 1: Reached Final Destination
        if matched_node_id == self.destination_node_id:
            self.current_node_id = matched_node_id
            self.current_step_index = len(self.active_route.steps) if self.active_route else 0
            if matched_node_id not in self.passed_nodes:
                self.passed_nodes.append(matched_node_id)

            voice = f"Destination confirmed! You have arrived at {node_label}."
            return NavigationEvent(
                event_type="DESTINATION_REACHED",
                node_id=matched_node_id,
                node_label=node_label,
                matched_sign=match.matched_sign,
                voice_instruction=voice,
                remaining_distance_m=0.0,
                current_step=None
            )

        # Case 2: Reached a waypoint along the active route
        path = self.active_route.path if self.active_route else []
        if matched_node_id in path:
            matched_idx = path.index(matched_node_id)
            self.current_node_id = matched_node_id
            self.current_step_index = matched_idx
            if matched_node_id not in self.passed_nodes:
                self.passed_nodes.append(matched_node_id)

            next_instruction = self.get_current_instruction()
            remaining_dist = self.get_remaining_distance()
            current_step = (
                self.active_route.steps[self.current_step_index]
                if self.current_step_index < len(self.active_route.steps)
                else None
            )

            voice = f"Confirmed landmark: {node_label}. {next_instruction}"
            return NavigationEvent(
                event_type="WAYPOINT_REACHED",
                node_id=matched_node_id,
                node_label=node_label,
                matched_sign=match.matched_sign,
                voice_instruction=voice,
                remaining_distance_m=remaining_dist,
                current_step=current_step
            )

        # Case 3: Off-route landmark observed
        return NavigationEvent(
            event_type="OFF_ROUTE_LANDMARK",
            node_id=matched_node_id,
            node_label=node_label,
            matched_sign=match.matched_sign,
            voice_instruction=f"Observed nearby landmark: {node_label}.",
            remaining_distance_m=remaining_dist,
            current_step=None
        )
