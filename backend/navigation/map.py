"""
Indoor Map Graph Model.
Loads landmarks and topological connectivity from indoor_map.json and landmarks.json.
"""
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set


class IndoorMap:
    """
    Represents the topological graph of the indoor environment.
    Provides node positions, adjacency relations, and distance metrics.
    """

    def __init__(
        self,
        map_path: Optional[str] = None,
        landmarks_path: Optional[str] = None,
    ):
        self.nodes: Set[str] = set()
        self.adjacency: Dict[str, Set[str]] = {}
        self.landmarks: Dict[str, Dict[str, Any]] = {}

        if map_path or landmarks_path:
            self.load(map_path, landmarks_path)

    def load(
        self,
        map_path: Optional[str] = None,
        landmarks_path: Optional[str] = None,
    ) -> None:
        """Loads indoor map configuration and landmarks."""
        # 1. Load Landmarks
        l_path = self._resolve_path(
            landmarks_path,
            ["config/landmarks.json", "data/landmarks.json"],
        )
        if l_path and l_path.exists():
            with open(l_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.landmarks = {item["id"]: item for item in data}

        # 2. Load Topological Map
        m_path = self._resolve_path(
            map_path,
            ["config/indoor_map.json", "data/indoor_map.json"],
        )
        if m_path and m_path.exists():
            with open(m_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.nodes = set(data.get("nodes", []))
                self.adjacency = {node: set() for node in self.nodes}
                for u, v in data.get("edges", []):
                    self.nodes.add(u)
                    self.nodes.add(v)
                    if u not in self.adjacency:
                        self.adjacency[u] = set()
                    if v not in self.adjacency:
                        self.adjacency[v] = set()
                    self.adjacency[u].add(v)
                    self.adjacency[v].add(u)  # Bidirectional

    def _resolve_path(self, user_path: Optional[str], default_candidates: List[str]) -> Optional[Path]:
        if user_path:
            p = Path(user_path)
            if p.exists():
                return p
        root = Path(__file__).parent.parent.parent
        for candidate in default_candidates:
            p = root / candidate
            if p.exists():
                return p
        return None

    def get_landmark(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.landmarks.get(node_id)

    def get_neighbors(self, node_id: str) -> List[str]:
        return list(self.adjacency.get(node_id, []))

    def get_distance(self, u: str, v: str) -> float:
        """Euclidean distance between two landmarks, or 1.0 if coordinates missing."""
        lm_u = self.landmarks.get(u)
        lm_v = self.landmarks.get(v)
        if lm_u and lm_v:
            dx = lm_v.get("x", 0) - lm_u.get("x", 0)
            dy = lm_v.get("y", 0) - lm_u.get("y", 0)
            return math.hypot(dx, dy)
        return 1.0

    def get_vector(self, u: str, v: str) -> Tuple[float, float]:
        """Direction vector (dx, dy) from node u to node v."""
        lm_u = self.landmarks.get(u)
        lm_v = self.landmarks.get(v)
        if lm_u and lm_v:
            return (
                float(lm_v.get("x", 0) - lm_u.get("x", 0)),
                float(lm_v.get("y", 0) - lm_u.get("y", 0)),
            )
        return (0.0, 0.0)

    def to_dict(self) -> Dict[str, Any]:
        """Serialized representation for API / Dashboard."""
        edges = []
        seen = set()
        for u in self.adjacency:
            for v in self.adjacency[u]:
                edge_pair = tuple(sorted([u, v]))
                if edge_pair not in seen:
                    seen.add(edge_pair)
                    edges.append([edge_pair[0], edge_pair[1]])
        return {
            "nodes": sorted(list(self.nodes)),
            "edges": edges,
            "landmarks": list(self.landmarks.values()),
        }
