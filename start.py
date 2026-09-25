"""
CampusEcho Master Startup Script
Launches the full system with a single command:
  .\.venv\Scripts\python.exe start.py
  .\.venv\Scripts\python.exe start.py --mode haptic
  .\.venv\Scripts\python.exe start.py --video data/test_walk.mp4
  .\.venv\Scripts\python.exe start.py --start golden_gate --destination silveria_hall
"""
import argparse
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

# ── Path setup ────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def start_api_server(host: str = "127.0.0.1", port: int = 8000):
    """Starts the FastAPI server in this thread (blocks until stopped)."""
    import src.api.server as srv_module
    uvicorn.run(
        srv_module.app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )


def wait_for_server(host: str, port: int, timeout: float = 8.0):
    """Polls until the server accepts connections or timeout expires."""
    import httpx
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://{host}:{port}/health", timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    parser = argparse.ArgumentParser(
        description="CampusEcho — Accessible Campus Navigation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python start.py                          # Start with webcam, DUAL mode
  python start.py --mode voice             # Voice-only output
  python start.py --mode haptic            # Haptic-only output
  python start.py --video campus.mp4       # Use recorded video
  python start.py --no-browser             # Don't auto-open dashboard
        """,
    )
    parser.add_argument("--host",        default="127.0.0.1")
    parser.add_argument("--port",        default=8000, type=int)
    parser.add_argument("--mode",        default="dual",
                        choices=["dual", "voice", "haptic"],
                        help="Output mode (default: dual)")
    parser.add_argument("--video",       default=None,
                        help="Path to video file (omit for live webcam)")
    parser.add_argument("--graph",       default="data/campus_graph.json")
    parser.add_argument("--start",       default="golden_gate")
    parser.add_argument("--destination", default="silveria_hall")
    parser.add_argument("--no-browser",  action="store_true",
                        help="Don't auto-open the dashboard in the browser")
    parser.add_argument("--haptic-port", default=None,
                        help="COM port for ESP32 Bluetooth wristband (e.g. COM5 or 'auto')")
    parser.add_argument("--haptic-baud", default=115200, type=int,
                        help="Baud rate for ESP32 Bluetooth wristband (default: 115200)")
    args = parser.parse_args()

    # Map mode shorthand
    mode_map = {"dual": "DUAL", "voice": "VOICE_ONLY", "haptic": "HAPTIC_ONLY"}
    output_mode = mode_map[args.mode]

    print()
    print("=" * 65)
    print("  CampusEcho  |  Accessible Campus Navigation System")
    print("=" * 65)
    print(f"  Output Mode  : {output_mode}")
    print(f"  Video Source : {args.video or 'Live Webcam (index 0)'}")
    print(f"  Route        : {args.start} --> {args.destination}")
    print(f"  Haptic HW    : {args.haptic_port or 'Web Simulator (Fallback)'}")
    print(f"  Dashboard    : http://{args.host}:{args.port}/dashboard")
    print("=" * 65)

    # ── 1. Initialise database ─────────────────────────────────────────
    from src.db.schema import db_init
    db_init()
    print("[DB] Initialised obstacle database (WAL mode).")

    # ── 2. Start FastAPI server in background thread ────────────────────
    srv_thread = threading.Thread(
        target=start_api_server, args=(args.host, args.port), daemon=True
    )
    srv_thread.start()
    print(f"[Server] Starting on http://{args.host}:{args.port} ...", end=" ", flush=True)
    if wait_for_server(args.host, args.port):
        print("ready.")
    else:
        print("WARNING: Server may not be ready yet.")

    # ── 3. Set initial output mode via API ─────────────────────────────
    import httpx
    try:
        httpx.post(
            f"http://{args.host}:{args.port}/mode",
            json={"mode": output_mode}, timeout=2.0
        )
        print(f"[Mode] Output mode set to {output_mode}.")
    except Exception as e:
        print(f"[Mode] Could not set mode: {e}")

    # ── 3b. Connect ESP32 Haptic Wristband (if requested) ─────────────
    if args.haptic_port:
        port_to_connect = args.haptic_port
        if port_to_connect.lower() == "auto":
            try:
                r = httpx.get(f"http://{args.host}:{args.port}/haptic/ports", timeout=2.0)
                port_to_connect = r.json().get("detected")
            except Exception:
                port_to_connect = None

        if port_to_connect:
            try:
                r = httpx.post(
                    f"http://{args.host}:{args.port}/haptic/connect",
                    json={"port": port_to_connect, "baud": args.haptic_baud},
                    timeout=3.0,
                )
                if r.status_code == 200:
                    print(f"[HapticBridge] Connected to ESP32 Wristband on {port_to_connect}.")
                else:
                    print(f"[HapticBridge] Notice: Could not connect to {port_to_connect}. Using Web Simulator.")
            except Exception as e:
                print(f"[HapticBridge] Notice: Connection to {port_to_connect} failed ({e}). Using Web Simulator.")
        else:
            print("[HapticBridge] Notice: Auto-detect found no ESP32 wristband. Using Web Simulator.")

    # ── 4. Open dashboard in browser ───────────────────────────────────
    if not args.no_browser:
        dashboard_url = f"http://{args.host}:{args.port}/dashboard"
        webbrowser.open(dashboard_url)
        print(f"[Dashboard] Opened in browser: {dashboard_url}")

    # ── 5. Print ready status ──────────────────────────────────────────
    print()
    print("  CampusEcho is running.")
    print(f"  Dashboard  : http://{args.host}:{args.port}/dashboard")
    print(f"  API Docs   : http://{args.host}:{args.port}/docs")
    print(f"  API Status : http://{args.host}:{args.port}/status")
    print()
    print("  Press Ctrl+C to stop.")
    print()

    # ── 6. Keep main thread alive ──────────────────────────────────────
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[CampusEcho] Shutting down. Goodbye.")


if __name__ == "__main__":
    main()
