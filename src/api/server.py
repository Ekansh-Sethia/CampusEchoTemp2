"""
FastAPI server for CampusEcho's Shared Obstacle Database, Multi-User Sync,
Mode Control, and Dashboard static file serving.
"""
import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.db.obstacle_store import ObstacleStore
from src.decision.hazard_memory import HazardRecord
from src.notifications.mode_router import ModeRouter, OutputMode
from src.api.telemetry import (
    make_voice_event, make_haptic_event, make_escalation_event,
    EVENT_MODE_CHANGE,
)


# ─── Global State ──────────────────────────────────────────────────────────────

store = ObstacleStore()
mode_router = ModeRouter(mode=OutputMode.DUAL)
_ws_clients: Set[WebSocket] = set()
_decay_task: Optional[asyncio.Task] = None

DECAY_TICK_INTERVAL_S = 10.0
STATIC_DIR = Path(__file__).parent.parent.parent / "static"


# ─── Lifespan: Start/stop background decay worker ──────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Starts the background decay worker on server startup."""
    global _decay_task
    _decay_task = asyncio.create_task(_decay_worker())
    print("[DecayWorker] Started — ticking every 10s.")
    yield
    if _decay_task:
        _decay_task.cancel()
        try:
            await _decay_task
        except asyncio.CancelledError:
            pass
    print("[DecayWorker] Stopped.")


# ─── App Definition ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="CampusEcho Obstacle API",
    description="Shared obstacle database, multi-user WebSocket sync, mode control, and dashboard for CampusEcho.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (dashboard)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─── Request / Response Schemas ─────────────────────────────────────────────────

class ObstacleReportRequest(BaseModel):
    """JSON body for POST /obstacles."""
    edge_id: str
    label: str
    confidence: float
    decay_tau_s: float = 90.0
    penalty_weight: float = 300.0
    reported_by: str = "user_1"
    obstacle_id: Optional[str] = None


class ActiveHazardsResponse(BaseModel):
    """Response body for GET /status."""
    count: int
    hazards: List[HazardRecord]
    timestamp: float


class ModeRequest(BaseModel):
    """JSON body for POST /mode."""
    mode: str  # "VOICE_ONLY" | "HAPTIC_ONLY" | "DUAL"


# ─── REST Endpoints ──────────────────────────────────────────────────────────────

@app.get("/dashboard", tags=["Dashboard"], include_in_schema=False)
def serve_dashboard():
    """Serves the Mission Control Dashboard HTML file."""
    dashboard_path = STATIC_DIR / "dashboard.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found. Run from project root.")
    return FileResponse(str(dashboard_path), media_type="text/html")


@app.post("/mode", tags=["Control"])
async def set_output_mode(body: ModeRequest):
    """
    Toggles the output mode (VOICE_ONLY / HAPTIC_ONLY / DUAL).
    Broadcasts a mode_change event to all connected WebSocket clients.
    """
    global mode_router
    try:
        new_mode = OutputMode(body.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid mode '{body.mode}'. Use VOICE_ONLY, HAPTIC_ONLY, or DUAL.")
    mode_router.set_mode(new_mode)
    await _broadcast({
        "event": EVENT_MODE_CHANGE,
        "mode": new_mode.value,
        "timestamp": time.time(),
    })
    return {"status": "ok", "mode": new_mode.value}


@app.get("/status", response_model=ActiveHazardsResponse, tags=["Obstacles"])
def get_status():
    """Returns the current list of all active (non-decayed) obstacles."""
    hazards = store.get_active()
    return ActiveHazardsResponse(
        count=len(hazards),
        hazards=hazards,
        timestamp=time.time(),
    )


@app.post("/obstacles", response_model=HazardRecord, tags=["Obstacles"])
async def report_obstacle(body: ObstacleReportRequest):
    """
    Reports a new obstacle or refreshes an existing one on the same edge+label.
    Immediately broadcasts the updated hazard map to all WebSocket clients.
    """
    # Build a HazardRecord using the request body
    now = time.time()
    record = HazardRecord(
        obstacle_id=body.obstacle_id or f"{body.label}_{body.edge_id[:8]}",
        edge_id=body.edge_id,
        label=body.label,
        confidence=body.confidence,
        initial_weight=body.penalty_weight,
        active_weight=body.penalty_weight,
        decay_tau_s=body.decay_tau_s,
        first_seen=now,
        last_confirmed=now,
        reported_by=body.reported_by,
    )
    store.upsert(record)

    # Broadcast to all connected WebSocket clients
    await _broadcast_hazard_update(event="obstacle_reported", record=record)

    return record


@app.post("/obstacles/{obstacle_id}/clear", tags=["Obstacles"])
async def clear_obstacle(obstacle_id: str):
    """
    Manually removes a specific obstacle (user confirms path is clear).
    Broadcasts the removal event to all connected clients.
    """
    removed = store.remove(obstacle_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Obstacle '{obstacle_id}' not found.")

    await _broadcast({"event": "obstacle_cleared", "obstacle_id": obstacle_id, "timestamp": time.time()})
    return {"status": "cleared", "obstacle_id": obstacle_id}


@app.get("/health", tags=["Meta"])
def health_check():
    return {"status": "ok", "active_obstacles": store.count()}


# ─── WebSocket Endpoint ──────────────────────────────────────────────────────────

@app.websocket("/ws/telemetry")
async def ws_telemetry(websocket: WebSocket):
    """
    WebSocket telemetry channel.
    - On connect: immediately sends current active hazard snapshot.
    - Receives: JSON commands (e.g., {"cmd": "ping"}).
    - Broadcasts: obstacle_reported, obstacle_decayed, decay_tick events.
    """
    await websocket.accept()
    _ws_clients.add(websocket)

    try:
        # Send initial snapshot
        hazards = store.get_active()
        await websocket.send_text(json.dumps({
            "event": "snapshot",
            "count": len(hazards),
            "hazards": [h.model_dump() for h in hazards],
            "timestamp": time.time(),
        }))

        # Listen for commands
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("cmd") == "ping":
                    await websocket.send_text(json.dumps({"event": "pong", "timestamp": time.time()}))
                elif msg.get("cmd") == "status":
                    hazards = store.get_active()
                    await websocket.send_text(json.dumps({
                        "event": "status_response",
                        "count": len(hazards),
                        "hazards": [h.model_dump() for h in hazards],
                        "timestamp": time.time(),
                    }))
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
    except Exception:
        _ws_clients.discard(websocket)


# ─── Background Decay Worker ─────────────────────────────────────────────────────

async def _decay_worker():
    """Periodically runs decay_tick and broadcasts updates to WebSocket clients."""
    while True:
        await asyncio.sleep(DECAY_TICK_INTERVAL_S)
        pruned_ids = store.decay_tick()
        active = store.get_active()

        payload = {
            "event": "decay_tick",
            "pruned_ids": pruned_ids,
            "active_count": len(active),
            "active_hazards": [h.model_dump() for h in active],
            "timestamp": time.time(),
        }
        await _broadcast(payload)

        if pruned_ids:
            print(f"[DecayWorker] Pruned {len(pruned_ids)} stale obstacle(s): {pruned_ids}")


async def _broadcast(payload: dict):
    """Broadcasts a JSON payload to all connected WebSocket clients."""
    global _ws_clients
    if not _ws_clients:
        return
    message = json.dumps(payload)
    dead_clients = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_text(message)
        except Exception:
            dead_clients.add(ws)
    _ws_clients -= dead_clients


async def _broadcast_hazard_update(event: str, record: HazardRecord):
    """Broadcasts a specific hazard event to all clients."""
    await _broadcast({
        "event": event,
        "obstacle": record.model_dump(),
        "timestamp": time.time(),
    })
