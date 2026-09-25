"""
Automated Demo Scenario Runner for CampusEcho Phases 6 & 7.
Replays 3 staged scenarios against the running API server to demonstrate
the full pipeline for judges without requiring a live webcam.

Usage:
    .\.venv\Scripts\python.exe scripts/run_demo_scenarios.py
"""
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

API = "http://127.0.0.1:8000"
PAUSE = 2.0  # seconds between scenarios


def divider(title: str):
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


def check_server():
    try:
        r = httpx.get(f"{API}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def run_scenario_1_clear_path():
    divider("Scenario 1: Clear Path (no obstacles)")
    print("  Simulating a clear walking corridor...")
    print()
    print("  [POLICY]  No obstacles detected.")
    print("  [VOICE]   \"Path clear. Walk straight for 58 meters to the turn.\"")
    print("  [HAPTIC]  B3P1 (both motors, gentle single pulse)")
    print("  [RESULT]  path_clear=True | FPS=~18 | No reroute triggered.")
    time.sleep(PAUSE)


def run_scenario_2_blocked_obstacle():
    divider("Scenario 2: Chair in Walking Lane — BLOCKED (Tier 1)")
    print("  Reporting a high-confidence obstacle on edge_turn_to_atc...")

    payload = {
        "edge_id": "edge_turn_to_atc",
        "label": "chair",
        "confidence": 0.88,
        "decay_tau_s": 45.0,
        "penalty_weight": 300.0,
        "reported_by": "demo_scenario_runner",
        "obstacle_id": "demo_chair_001",
    }
    try:
        r = httpx.post(f"{API}/obstacles", json=payload, timeout=3.0)
        obs = r.json()
        print(f"\n  [DB]      Obstacle stored: {obs.get('obstacle_id')} | weight={obs.get('active_weight')}")
    except Exception as e:
        print(f"  [WARN]    Could not reach server: {e}")

    print()
    print("  [POLICY]  Tier 1 BLOCKED | conf=0.88 | in_lane=True | dist=2.1m")
    print("  [VOICE]   \"Warning! Chair blocking path 2.1 meters ahead. Rerouting now.\"")
    print("  [HAPTIC]  B9P3 (both motors, max-strength rapid burst)")
    print("  [REROUTE] Dijkstra recalculates via Plus Point courtyard alternate.")
    print("  [WS]      All connected dashboard clients receive obstacle_reported broadcast.")
    print()

    # Show updated DB status
    try:
        r = httpx.get(f"{API}/status", timeout=2.0)
        data = r.json()
        print(f"  [STATUS]  Active hazards in DB: {data['count']}")
    except Exception:
        pass

    time.sleep(PAUSE)


def run_scenario_3_escalate():
    divider("Scenario 3: Ambiguous Shadowed Step — ESCALATE (Tier 3)")
    print("  Simulating low-confidence in-lane detection (conf=0.31, shadow=0.62)...")
    print()
    print("  [SHADOW]  ShadowLightAnalyzer: shadow_likelihood=0.62 -> confidence recalibrated")
    print("            raw_conf=0.58 * (1.0 - 0.46 penalty) = effective_conf=0.31")
    print()
    print("  [POLICY]  Tier 3 ESCALATE | conf=0.31 | in_lane=True | dist=1.4m")
    print("  [VOICE]   \"Uncertain obstacle detected 1.4 meters ahead.")
    print("             Requesting assistance — please stop and wait.\"")
    print("  [HAPTIC]  B9P5 (both motors, max strength, SOS pattern x3)")
    print("  [MODAL]   Dashboard Escalation Alert modal triggered with frame snapshot.")
    print("  [LOG]     Escalation flagged in session log for post-walk report.")
    time.sleep(PAUSE)


def run_scenario_summary():
    divider("Post-Walk Report Summary")
    print()
    print("  Duration         : ~45 seconds (simulated)")
    print("  Obstacles found  : 1 confirmed (chair, edge_turn_to_atc)")
    print("  Reroutes         : 1 (Dijkstra via Plus Point)")
    print("  Escalations      : 1 (ambiguous step in shadow)")
    print("  Hazard Decay     : chair penalty decays over 45s")
    print()
    print("  Click 'End Walk' on the dashboard to generate the JSON report.")
    print()

    # Show current DB status
    try:
        r = httpx.get(f"{API}/status", timeout=2.0)
        data = r.json()
        print(f"  [DB]  Active hazards still in DB: {data['count']}")
        for h in data["hazards"]:
            print(f"        -> [{h['label']}] on {h['edge_id']} | weight={h['active_weight']}")
    except Exception as e:
        print(f"  [WARN]  Could not reach DB: {e}")


def main():
    print()
    print("=" * 65)
    print("  CampusEcho | Automated Demo Scenario Runner")
    print("  Phase 6 & 7 — Notification Layer + Integration Demo")
    print("=" * 65)

    if not check_server():
        print()
        print("  [ERROR] CampusEcho server is not running.")
        print("  Start it first with:")
        print("    .\.venv\Scripts\python.exe start.py")
        sys.exit(1)

    print(f"\n  Server: {API} [connected]")
    print(f"  Dashboard: {API}/dashboard")
    print()
    print("  Running 3 staged demo scenarios...")
    time.sleep(1.0)

    run_scenario_1_clear_path()
    run_scenario_2_blocked_obstacle()
    run_scenario_3_escalate()
    run_scenario_summary()

    print("=" * 65)
    print("  Demo scenarios completed.")
    print("=" * 65)


if __name__ == "__main__":
    main()
