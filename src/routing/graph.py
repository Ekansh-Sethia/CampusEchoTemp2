"""Campus graph data structures and penalty management."""
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import networkx as nx
from pydantic import BaseModel, Field, ConfigDict


class Node(BaseModel):
    """Represents a landmark or junction in the campus graph."""
    id: str
    name: str
    type: str  # entrance, building, junction, hall, waypoint, landmark
    label: str
    expected_signs: List[str] = Field(default_factory=list)
    landmark_image: Optional[str] = None
    landmark_images: List[str] = Field(default_factory=list)


class Edge(BaseModel):
    """Represents a walkable pathway connecting two nodes."""
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    distance_m: float
    direction_forward: str = "straight"   # direction when moving from -> to
    direction_backward: str = "straight"  # direction when moving to -> from
    description: str = ""


class ObstaclePenalty(BaseModel):
    """Represents an active penalty applied to an edge due to an obstacle."""
    obstacle_id: str
    edge_id: str
    penalty_weight: float
    description: str = ""


class CampusGraph:
    """Manages the campus topological map, edge weights, and dynamic obstacle penalties."""

    def __init__(self, json_path: Optional[str] = None):
        self.nx_graph: nx.Graph = nx.Graph()
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[str, Edge] = {}
        self.edge_by_nodes: Dict[Tuple[str, str], str] = {}
        self.penalties: Dict[str, List[ObstaclePenalty]] = {}
        self.metadata: dict = {}

        if json_path:
            self.load_from_json(json_path)

    def load_from_json(self, json_path: str) -> None:
        """Loads nodes, edges, and metadata from a campus_graph.json file."""
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Campus graph file not found at: {json_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.metadata = data.get("metadata", {})
        self.nx_graph.clear()
        self.nodes.clear()
        self.edges.clear()
        self.edge_by_nodes.clear()
        self.penalties.clear()

        # Load nodes
        for node_dict in data.get("nodes", []):
            node = Node(**node_dict)
            self.nodes[node.id] = node
            self.nx_graph.add_node(node.id, **node.model_dump())

        # Load edges
        for edge_dict in data.get("edges", []):
            edge = Edge(**edge_dict)
            self.edges[edge.id] = edge
            self.edge_by_nodes[(edge.from_node, edge.to_node)] = edge.id
            self.edge_by_nodes[(edge.to_node, edge.from_node)] = edge.id
            self.penalties[edge.id] = []

            # Add to networkx with base distance weight
            self.nx_graph.add_edge(
                edge.from_node,
                edge.to_node,
                edge_id=edge.id,
                base_distance=edge.distance_m,
                weight=edge.distance_m,
                edge_obj=edge
            )

    def get_edge_id(self, u: str, v: str) -> Optional[str]:
        """Returns the edge ID for an edge connecting u and v."""
        return self.edge_by_nodes.get((u, v))

    def get_edge(self, u: str, v: str) -> Optional[Edge]:
        """Returns the Edge object connecting u and v."""
        edge_id = self.get_edge_id(u, v)
        return self.edges.get(edge_id) if edge_id else None

    def add_edge_penalty(
        self,
        u: str,
        v: str,
        penalty_weight: float,
        obstacle_id: str = "obstacle_manual",
        description: str = ""
    ) -> float:
        """
        Adds a penalty weight to an edge between nodes u and v.
        Returns the new effective weight of the edge.
        """
        edge_id = self.get_edge_id(u, v)
        if not edge_id:
            raise ValueError(f"No edge connects {u} and {v}")

        penalty = ObstaclePenalty(
            obstacle_id=obstacle_id,
            edge_id=edge_id,
            penalty_weight=penalty_weight,
            description=description
        )
        self.penalties[edge_id].append(penalty)
        return self._recalculate_edge_weight(u, v)

    def remove_edge_penalty(
        self,
        u: str,
        v: str,
        obstacle_id: Optional[str] = None
    ) -> float:
        """
        Removes penalties for an edge. If obstacle_id is given, removes only that obstacle's penalty.
        Returns the updated effective weight.
        """
        edge_id = self.get_edge_id(u, v)
        if not edge_id:
            raise ValueError(f"No edge connects {u} and {v}")

        if obstacle_id:
            self.penalties[edge_id] = [
                p for p in self.penalties[edge_id] if p.obstacle_id != obstacle_id
            ]
        else:
            self.penalties[edge_id] = []

        return self._recalculate_edge_weight(u, v)

    def clear_penalties(self) -> None:
        """Clears all dynamic penalties and restores base distance weights."""
        for edge_id in self.penalties:
            self.penalties[edge_id] = []
        for u, v in self.nx_graph.edges():
            base_dist = self.nx_graph[u][v]["base_distance"]
            self.nx_graph[u][v]["weight"] = base_dist

    def _recalculate_edge_weight(self, u: str, v: str) -> float:
        """Internal helper to update the effective weight of an edge in the graph."""
        edge_id = self.get_edge_id(u, v)
        base_dist = self.edges[edge_id].distance_m
        total_penalties = sum(p.penalty_weight for p in self.penalties[edge_id])
        effective_weight = base_dist + total_penalties
        self.nx_graph[u][v]["weight"] = effective_weight
        return effective_weight

    def get_effective_weight(self, u: str, v: str) -> float:
        """Returns the current effective weight (distance + penalties) of an edge."""
        if not self.nx_graph.has_edge(u, v):
            raise ValueError(f"No edge between {u} and {v}")
        return self.nx_graph[u][v]["weight"]

    def get_turn_direction(self, from_node: str, to_node: str) -> str:
        """
        Determines the directional turn instruction when traversing from from_node to to_node.
        Returns 'straight', 'left', or 'right'.
        """
        edge = self.get_edge(from_node, to_node)
        if not edge:
            return "straight"
        if from_node == edge.from_node:
            return edge.direction_forward
        return edge.direction_backward

    def find_node_by_sign(self, detected_text: str) -> Optional[Node]:
        """
        Searches for a node whose expected_signs match or contain the detected text.
        Case-insensitive matching.
        """
        cleaned_text = detected_text.strip().upper()
        for node in self.nodes.values():
            for sign in node.expected_signs:
                if sign.upper() in cleaned_text or cleaned_text in sign.upper():
                    return node
        return None
