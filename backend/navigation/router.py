"""
Indoor Topological Router.
Finds shortest paths across the indoor landmark graph.
"""
from collections import deque
from typing import List, Optional, Dict, Any, Tuple
from backend.navigation.map import IndoorMap


class IndoorRouter:
    """
    Computes shortest topological paths between landmarks.
    Uses BFS / Dijkstra to guarantee optimal hop routes.
    """

    def __init__(self, indoor_map: IndoorMap):
        self.indoor_map = indoor_map

    def find_route(self, start_node: str, destination_node: str) -> Optional[List[str]]:
        """
        Calculates shortest path node list from start_node to destination_node.
        Returns e.g. ['B1', 'B2', 'B3'] or None if unreachable.
        """
        if not start_node or not destination_node:
            return None

        start_node = start_node.upper()
        destination_node = destination_node.upper()

        if start_node not in self.indoor_map.nodes or destination_node not in self.indoor_map.nodes:
            return None

        if start_node == destination_node:
            return [start_node]

        queue = deque([[start_node]])
        visited = {start_node}

        while queue:
            path = queue.popleft()
            current = path[-1]

            if current == destination_node:
                return path

            for neighbor in sorted(self.indoor_map.get_neighbors(current)):
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = list(path)
                    new_path.append(neighbor)
                    queue.append(new_path)

        return None

    def get_route_details(self, start_node: str, destination_node: str) -> Dict[str, Any]:
        """
        Returns rich route metadata including names, zones, distance, and waypoint list.
        """
        path = self.find_route(start_node, destination_node)
        if not path:
            return {
                "success": False,
                "start": start_node,
                "destination": destination_node,
                "path": [],
                "waypoints": [],
                "total_distance": 0.0,
                "step_count": 0,
            }

        waypoints = []
        total_dist = 0.0

        for i, node in enumerate(path):
            lm = self.indoor_map.get_landmark(node) or {}
            waypoints.append({
                "index": i,
                "id": node,
                "name": lm.get("name", node),
                "zone": lm.get("zone", node),
                "floor": lm.get("floor", 0),
                "x": lm.get("x", 0),
                "y": lm.get("y", 0),
            })
            if i > 0:
                total_dist += self.indoor_map.get_distance(path[i - 1], node)

        return {
            "success": True,
            "start": start_node,
            "destination": destination_node,
            "path": path,
            "waypoints": waypoints,
            "total_distance": round(total_dist, 2),
            "step_count": len(path),
        }
