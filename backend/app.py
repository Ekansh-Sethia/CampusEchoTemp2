"""
Indoor Landmark Position Recovery — Backend Application.
Provides REST and WebSocket endpoints for localization management,
BLE ingestion, QR fallback, graph routing, ESP32 Wi-Fi haptic dispatch,
and interactive dashboard telemetry.
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.localization.gps import GPSSystem
from backend.localization.visual import VisualLocalizationSystem
from backend.localization.ble import BLELandmarkManager
from backend.localization.qr import QRValidator
from backend.localization.manager import LocalizationManager
from backend.navigation.map import IndoorMap
from backend.navigation.router import IndoorRouter
from backend.navigation.instructions import InstructionGenerator
from backend.communication.esp32 import ESP32Client

# ── Initialization & State ──────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
STATIC_DIR = ROOT / "static"
DASHBOARD_DIR = ROOT / "dashboard"

# Load Maps & Landmarks
indoor_map = IndoorMap()
indoor_map.load()

# Core Subsystems
gps_sys = GPSSystem(initial_reliable=False, initial_confidence=0.15)
vis_sys = VisualLocalizationSystem(initial_reliable=False, initial_confidence=0.20)
ble_mgr = BLELandmarkManager(list(indoor_map.landmarks.values()))
qr_val = QRValidator(list(indoor_map.landmarks.values()))

loc_manager = LocalizationManager(
    landmarks_config=list(indoor_map.landmarks.values()),
    gps=gps_sys,
    visual=vis_sys,
    ble=ble_mgr,
    qr=qr_val,
)

router = IndoorRouter(indoor_map)
instruction_gen = InstructionGenerator(indoor_map)

# Connect to ESP32 Client (Wi-Fi with optional serial bridge fallback)
esp32_client = ESP32Client()

# Active Navigation State
_active_destination: Optional[str] = None
_active_route: List[str] = []
_last_instruction: Dict[str, Any] = {}
_ws_clients: Set[WebSocket] = set()

# ── Pydantic Request Models ─────────────────────────────────────────────
class BLEScanRequest(BaseModel):
    readings: Dict[str, float]  # e.g. {"B1": -60.0, "B2": -85.0}

class QRScanRequest(BaseModel):
    payload: str  # e.g. "B3" or '{"id":"B3"}'

class DestinationRequest(BaseModel):
    destination: str  # e.g. "B5"

class LandmarkItem(BaseModel):
    id: str
    name: str
    floor: int = 0
    zone: str
    x: float
    y: float

class UpdateLandmarksRequest(BaseModel):
    landmarks: List[LandmarkItem]

class GPSStatusRequest(BaseModel):
    reliable: bool
    confidence: Optional[float] = None

class ESP32ConfigRequest(BaseModel):
    ip: str

class TestPresetRequest(BaseModel):
    preset: str  # test1_normal, test2_gps_loss, test3_ble_recovery, test4_confidence_drop, test5_qr_recovery

# ── Helper Functions ───────────────────────────────────────────────────
def update_navigation_state(dispatch_hardware: bool = True) -> Dict[str, Any]:
    """Recalculates location, route, next action, and optionally sends to ESP32."""
    global _active_destination, _active_route, _last_instruction

    current_loc = loc_manager.get_current_location()

    # If we have a destination and a valid current landmark, ensure route is fresh
    current_node = current_loc.get("landmark_id")
    if _active_destination and current_node:
        _active_route = router.find_route(current_node, _active_destination) or []
    elif not _active_destination:
        _active_route = []

    # Generate next instruction
    instruction = instruction_gen.generate_instruction(
        current_location=current_loc,
        destination_id=_active_destination,
        full_route=_active_route,
    )
    _last_instruction = instruction

    # Dispatch to ESP32 wearable if commanded
    if dispatch_hardware and instruction.get("command"):
        cmd = instruction["command"]
        esp32_client.send_command(cmd)

    return get_system_snapshot()


def get_system_snapshot() -> Dict[str, Any]:
    """Returns the complete dashboard-ready system state (Spec Section 24)."""
    current_loc = loc_manager.get_current_location()
    dest_lm = indoor_map.get_landmark(_active_destination) if _active_destination else None

    # Subsystem statuses
    gps_status = "Available" if gps_sys.is_reliable else "Unavailable"
    ble_est = ble_mgr.get_current_estimate()
    ble_status = "Connected" if ble_est else "Scanning"
    qr_status = "Recent Scan" if qr_val.get_fresh_qr_position() else "Standby"
    esp32_status = "Connected" if esp32_client.is_connected else "Standby / Not Configured"

    return {
        "timestamp": time.time(),
        "current_location": current_loc,
        "destination": {
            "id": _active_destination,
            "name": dest_lm.get("name", _active_destination) if dest_lm else None,
            "zone": dest_lm.get("zone", None) if dest_lm else None,
        } if _active_destination else None,
        "route": _active_route,
        "instruction": _last_instruction or instruction_gen.generate_instruction(current_loc, _active_destination, _active_route),
        "subsystems": {
            "gps": gps_status,
            "ble": ble_status,
            "qr": qr_status,
            "esp32": esp32_status,
        },
        "esp32_client": esp32_client.status_summary,
        "map": indoor_map.to_dict(),
    }


async def broadcast_state():
    """Pushes state update to all connected WebSocket clients."""
    if not _ws_clients:
        return
    snapshot = get_system_snapshot()
    payload = json.dumps(snapshot)
    dead_clients = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead_clients.add(ws)
    _ws_clients.difference_update(dead_clients)


# ── App Definition ──────────────────────────────────────────────────────
app = FastAPI(
    title="CampusEcho — Indoor Landmark Position Recovery API",
    description="Backend service for indoor localization, BLE hysteresis, QR recovery, and ESP32 haptic guidance.",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── REST Endpoints ─────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Indoor Landmark Recovery"}


@app.get("/api/indoor/status")
def get_indoor_status():
    return get_system_snapshot()


@app.get("/api/indoor/landmarks")
def list_landmarks():
    return list(indoor_map.landmarks.values())


@app.post("/api/indoor/landmarks")
async def update_landmarks_endpoint(req: UpdateLandmarksRequest):
    """
    Updates the active landmarks list, persists to config and data files,
    re-initializes the map graph, updates localization engines, and notifies dashboard.
    """
    raw_list = [item.model_dump() for item in req.landmarks]
    if not raw_list:
        raise HTTPException(status_code=400, detail="Landmarks list cannot be empty.")

    # 1. Persist to config/landmarks.json and data/landmarks.json
    paths = [
        ROOT / "config" / "landmarks.json",
        ROOT / "data" / "landmarks.json",
    ]
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(raw_list, f, indent=2)

    # 2. Also ensure nodes exist in indoor_map.json
    node_ids = [item["id"] for item in raw_list]
    map_paths = [
        ROOT / "config" / "indoor_map.json",
        ROOT / "data" / "indoor_map.json",
    ]
    for mp in map_paths:
        if mp.exists():
            try:
                with open(mp, "r", encoding="utf-8") as f:
                    mdata = json.load(f)
                existing_nodes = set(mdata.get("nodes", []))
                for nid in node_ids:
                    existing_nodes.add(nid)
                mdata["nodes"] = sorted(list(existing_nodes))
                with open(mp, "w", encoding="utf-8") as f:
                    json.dump(mdata, f, indent=2)
            except Exception:
                pass

    # 3. Reload map & manager
    indoor_map.load()
    loc_manager.update_landmarks(list(indoor_map.landmarks.values()))

    # 4. Generate QR markers for new landmarks
    try:
        from scripts.generate_qr_markers import generate_markers
        generate_markers()
    except Exception as e:
        print(f"[QR] Marker generation note: {e}")

    update_navigation_state(dispatch_hardware=False)
    await broadcast_state()
    return {
        "status": "landmarks_updated",
        "count": len(raw_list),
        "landmarks": list(indoor_map.landmarks.values()),
        "map": indoor_map.to_dict(),
    }


@app.post("/api/indoor/landmarks/reset")
async def reset_landmarks_default():
    """Resets landmarks back to default B1-B5 Hackathon specification."""
    default_landmarks = [
        {"id": "B1", "name": "Main Entrance", "floor": 0, "zone": "Entrance", "x": 0, "y": 0},
        {"id": "B2", "name": "Central Corridor", "floor": 0, "zone": "Corridor", "x": 5, "y": 0},
        {"id": "B3", "name": "Computer Lab", "floor": 0, "zone": "Lab", "x": 10, "y": 0},
        {"id": "B4", "name": "Staircase", "floor": 0, "zone": "Staircase", "x": 5, "y": 5},
        {"id": "B5", "name": "Library", "floor": 0, "zone": "Library", "x": 10, "y": 5},
    ]
    req = UpdateLandmarksRequest(landmarks=[LandmarkItem(**item) for item in default_landmarks])
    return await update_landmarks_endpoint(req)


@app.get("/api/indoor/map")
def get_map():
    return indoor_map.to_dict()


@app.post("/api/indoor/destination")
async def set_destination(req: DestinationRequest):
    global _active_destination
    dest = req.destination.strip().upper()
    if dest not in indoor_map.nodes:
        raise HTTPException(status_code=400, detail=f"Landmark {dest} not found in indoor map.")
    _active_destination = dest
    update_navigation_state(dispatch_hardware=True)
    await broadcast_state()
    return {"status": "destination_set", "destination": _active_destination, "route": _active_route}


@app.post("/api/indoor/ble-scan")
async def ingest_ble_scan(req: BLEScanRequest):
    """
    Ingests BLE scan readings, applies hysteresis smoothing, and updates navigation.
    Example: {"readings": {"B2": -62.0, "B1": -85.0}}
    """
    loc_manager.feed_ble_scan(req.readings)
    update_navigation_state(dispatch_hardware=True)
    await broadcast_state()
    return get_system_snapshot()


@app.post("/api/indoor/qr-scan")
async def ingest_qr_scan(req: QRScanRequest):
    """
    Ingests QR payload (e.g. "B3" or JSON), immediately restoring high confidence.
    """
    result = loc_manager.feed_qr_payload(req.payload)
    if not result:
        raise HTTPException(status_code=400, detail=f"Invalid QR landmark payload: {req.payload}")
    update_navigation_state(dispatch_hardware=True)
    await broadcast_state()
    return {"status": "qr_recovered", "location": result}


@app.post("/api/indoor/gps-status")
async def update_gps_status(req: GPSStatusRequest):
    """Controls outdoor GPS state to simulate entering or exiting buildings."""
    gps_sys.set_status(reliable=req.reliable, confidence=req.confidence)
    update_navigation_state(dispatch_hardware=True)
    await broadcast_state()
    return {"gps": gps_sys.get_status()}


@app.post("/api/indoor/esp32/config")
def configure_esp32(req: ESP32ConfigRequest):
    """Sets the target Wi-Fi IP address for the ESP32 wristband."""
    esp32_client.set_ip(req.ip)
    connected = esp32_client.check_connection()
    return {"esp32_ip": req.ip, "connected": connected}


@app.post("/api/indoor/esp32/command")
def send_esp32_command(command: str = Body(..., embed=True)):
    """Manually test an ESP32 command: LEFT, RIGHT, FORWARD, STOP, ARRIVED, UNKNOWN."""
    success = esp32_client.send_command(command)
    return {"command": command, "success": success, "esp32": esp32_client.status_summary}


@app.post("/api/indoor/reset")
async def reset_all():
    """Resets all filters, active destination, and hardware."""
    global _active_destination, _active_route
    loc_manager.reset_state()
    _active_destination = None
    _active_route = []
    esp32_client.send_command("STOP")
    await broadcast_state()
    return {"status": "reset_complete"}


@app.post("/api/indoor/test-preset")
async def run_judge_preset(req: TestPresetRequest):
    """
    Runs one of the 5 official Hackathon Challenge Judge Test Cases (Spec Section 26).
    """
    global _active_destination
    preset = req.preset.lower().strip()

    if preset == "test1_normal":
        # Test 1: Normal localization B1 -> B3
        loc_manager.reset_state()
        gps_sys.set_indoor(True)
        # Feed 3 stable scans for B1 to establish location
        for _ in range(3):
            loc_manager.feed_ble_scan({"B1": -55.0, "B2": -85.0})
        _active_destination = "B3"
        desc = "Test 1: Normal Localization B1 -> B3 (Route: B1 -> B2 -> B3)"

    elif preset == "test2_gps_loss":
        # Test 2: GPS Loss transition -> BLE B2 recovery
        gps_sys.set_status(reliable=True, confidence=0.90)
        # Simulate walking inside: GPS drops, BLE picks up B2
        gps_sys.set_indoor(True)
        for _ in range(3):
            loc_manager.feed_ble_scan({"B2": -52.0, "B1": -78.0, "B3": -80.0})
        _active_destination = "B5"
        desc = "Test 2: GPS Loss -> BLE Recovery at B2 (Central Corridor)"

    elif preset == "test3_ble_recovery":
        # Test 3: At B3, route recalculated to B5
        gps_sys.set_indoor(True)
        for _ in range(3):
            loc_manager.feed_ble_scan({"B3": -50.0, "B2": -75.0})
        _active_destination = "B5"
        desc = "Test 3: BLE Recovery at B3 (Computer Lab) -> Route to B5 (Library)"

    elif preset == "test4_confidence_drop":
        # Test 4: BLE Confidence drops -> Safe UNKNOWN state (no guessing)
        gps_sys.set_indoor(True)
        loc_manager.reset_state()
        # Feed weak, ambiguous signal
        loc_manager.feed_ble_scan({"B2": -92.0, "B4": -93.0})
        _active_destination = "B5"
        desc = "Test 4: BLE Confidence Drop -> Safe UNKNOWN State (Suppresses direction)"

    elif preset == "test5_qr_recovery":
        # Test 5: Scan B4 QR -> Staircase position restored -> Navigation resumes
        gps_sys.set_indoor(True)
        loc_manager.feed_qr_payload("B4")
        _active_destination = "B5"
        desc = "Test 5: Explicit QR Recovery at B4 (Staircase) -> Confidence restored"

    else:
        raise HTTPException(status_code=400, detail=f"Unknown test preset: {preset}")

    update_navigation_state(dispatch_hardware=True)
    await broadcast_state()
    return {
        "preset": preset,
        "description": desc,
        "snapshot": get_system_snapshot(),
    }


# ── WebSocket ──────────────────────────────────────────────────────────
@app.websocket("/ws/indoor")
async def websocket_indoor_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        # Send initial snapshot immediately
        await websocket.send_text(json.dumps(get_system_snapshot()))
        while True:
            data = await websocket.receive_text()
            # Client can send commands e.g. {"action": "refresh"}
            try:
                msg = json.loads(data)
                if msg.get("action") == "scan_ble":
                    loc_manager.feed_ble_scan(msg.get("readings", {}))
                    update_navigation_state(dispatch_hardware=True)
                    await broadcast_state()
                elif msg.get("action") == "scan_qr":
                    loc_manager.feed_qr_payload(msg.get("payload", ""))
                    update_navigation_state(dispatch_hardware=True)
                    await broadcast_state()
            except Exception:
                pass
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
    except Exception:
        _ws_clients.discard(websocket)


# ── Static UI Mounting ─────────────────────────────────────────────────
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if DASHBOARD_DIR.exists():
    app.mount("/dashboard-files", StaticFiles(directory=str(DASHBOARD_DIR)), name="dashboard_files")

@app.get("/")
@app.get("/indoor")
def serve_dashboard():
    # If custom indoor dashboard exists, serve it, otherwise serve fallback
    indoor_html = DASHBOARD_DIR / "indoor_dashboard.html"
    if indoor_html.exists():
        return FileResponse(str(indoor_html))
    return FileResponse(str(STATIC_DIR / "dashboard.html"))
