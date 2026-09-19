"""FastAPI Application for CampusEcho Navigation & Routing Engine."""
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.routing.graph import CampusGraph, Node
from src.routing.router import DijkstraRouter, RouteResult


GRAPH_PATH = Path(__file__).parent.parent / "data" / "campus_graph.json"

app = FastAPI(
    title="CampusEcho API",
    description="Accessible Navigation Assistant with Dynamic Rerouting for Visually Impaired Users",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global graph and router instances
graph = CampusGraph(str(GRAPH_PATH))
router = DijkstraRouter(graph)


class RouteRequest(BaseModel):
    source: str = Field(..., examples=["golden_gate"], description="Source landmark node ID")
    destination: str = Field(..., examples=["silveria_hall"], description="Destination landmark node ID")


class PenaltyRequest(BaseModel):
    from_node: str = Field(..., examples=["atc_junction"], description="Starting node of blocked edge")
    to_node: str = Field(..., examples=["silveria_hall"], description="Ending node of blocked edge")
    penalty_weight: float = Field(300.0, examples=[300.0], description="Virtual penalty in meters")
    obstacle_id: str = Field("obs_manual", examples=["obs_chair_1"], description="Identifier of the obstacle")
    description: str = Field("Obstacle detected on pathway", examples=["Chair blocking corridor"])


@app.get("/", tags=["Health"])
def health_check():
    """Confirms API status and loaded campus graph metadata."""
    return {
        "status": "healthy",
        "service": "CampusEcho Navigation Engine",
        "nodes_loaded": len(graph.nodes),
        "edges_loaded": len(graph.edges),
        "docs_url": "/docs"
    }


@app.get("/api/landmarks", response_model=List[Node], tags=["Campus Graph"])
def get_landmarks():
    """Lists all landmark nodes available for navigation."""
    return list(graph.nodes.values())


@app.get("/api/graph", tags=["Campus Graph"])
def get_graph_overview():
    """Returns nodes, edges, and currently active obstacle penalties."""
    return {
        "nodes": [n.model_dump() for n in graph.nodes.values()],
        "edges": [e.model_dump() for e in graph.edges.values()],
        "active_penalties": {
            edge_id: [p.model_dump() for p in penalties]
            for edge_id, penalties in graph.penalties.items()
            if penalties
        }
    }


@app.post("/api/route", response_model=RouteResult, tags=["Navigation & Routing"])
def compute_route(request: RouteRequest):
    """
    Computes optimal path and turn-by-turn guidance between two landmarks.
    Automatically accounts for active obstacle penalties.
    """
    try:
        return router.find_route(request.source, request.destination)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/penalty", tags=["Obstacle Management"])
def add_obstacle_penalty(request: PenaltyRequest):
    """
    Simulates or logs an obstacle on a pathway by adding an edge penalty.
    Subsequent route requests will automatically avoid this path if an alternative exists.
    """
    try:
        new_weight = graph.add_edge_penalty(
            u=request.from_node,
            v=request.to_node,
            penalty_weight=request.penalty_weight,
            obstacle_id=request.obstacle_id,
            description=request.description
        )
        return {
            "status": "penalty_applied",
            "edge": f"{request.from_node} <-> {request.to_node}",
            "new_effective_weight_meters": new_weight,
            "obstacle_id": request.obstacle_id
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/penalty", tags=["Obstacle Management"])
def clear_penalties():
    """Clears all active obstacle penalties, resetting paths to their base physical distances."""
    graph.clear_penalties()
    return {"status": "all_penalties_cleared"}
