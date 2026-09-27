r"""
Indoor Landmark Position Recovery — Interactive Simulator & Judge Demo CLI.
Implements the exact terminal dashboard (Spec Section 24) and all 5 Judge Tests (Spec Section 26).

Usage:
  .\.venv\Scripts\python.exe scripts/demo_indoor_recovery.py
  .\.venv\Scripts\python.exe scripts/demo_indoor_recovery.py --test 1
  .\.venv\Scripts\python.exe scripts/demo_indoor_recovery.py --esp32 192.168.1.100
"""
import argparse
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.localization.gps import GPSSystem
from backend.localization.visual import VisualLocalizationSystem
from backend.localization.ble import BLELandmarkManager
from backend.localization.qr import QRValidator
from backend.localization.manager import LocalizationManager
from backend.navigation.map import IndoorMap
from backend.navigation.router import IndoorRouter
from backend.navigation.instructions import InstructionGenerator
from backend.communication.esp32 import ESP32Client


def render_dashboard(
    current_location: dict,
    destination: str,
    instruction: dict,
    subsystems: dict,
    esp32_status: str = "Connected",
):
    """Renders the exact ASCII Dashboard required by Spec Section 24."""
    conf = current_location.get("confidence", 0.0)
    conf_pct = int(conf * 100)
    conf_level = current_location.get("confidence_level", "LOW")
    source = current_location.get("source", "UNKNOWN")
    lm_id = current_location.get("landmark_id") or "Unknown"
    zone = current_location.get("zone") or current_location.get("name") or "Unknown"
    cmd = instruction.get("command", "UNKNOWN")
    safe_mode = instruction.get("safe_mode", False) or conf < 0.50

    print("\n" + "=" * 41)
    if safe_mode or source == "UNKNOWN":
        print("      LOCALIZATION UNCERTAIN")
        print("=" * 41)
        print(f"Current Location:\n{zone}")
        print(f"\nConfidence:\n{conf_pct}% {conf_level}")
        print(f"\nAction:\nScan nearby QR landmark or move near beacon")
        print(f"\nNavigation:\nPAUSED")
        print(f"\nHaptic:\nUNKNOWN pattern (Double Pulse)")
    else:
        print("        INDOOR NAVIGATION")
        print("=" * 41)
        print(f"Current Location:\n{zone}")
        print(f"\nSource:\n{source} Landmark {lm_id}")
        print(f"\nFloor:\nGround Floor")
        print(f"\nConfidence:\n{conf_pct}% {conf_level}")
        print(f"\nDestination:\n{destination or 'None'}")
        print(f"\nNext Action:\n{cmd}")
        print(f"\nGPS:\n{subsystems.get('gps', 'Unavailable')}")
        print(f"\nBLE:\n{subsystems.get('ble', 'Connected')}")
        print(f"\nQR:\n{subsystems.get('qr', 'Standby')}")
        print(f"\nESP32:\n{esp32_status}")
    print("=" * 41 + "\n")


def run_judge_test(test_num: int, esp32_ip: str = None):
    """Executes one of the 5 Judge Tests according to Spec Section 26."""
    indoor_map = IndoorMap()
    indoor_map.load()

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
    esp32 = ESP32Client(esp32_ip=esp32_ip)

    print(f"\n>>> EXECUTING JUDGE TEST {test_num} <<<")

    if test_num == 1:
        print("\n--- TEST 1: Normal Localization (B1 -> B3) ---")
        print("1. User stands near Main Entrance (B1).")
        print("2. BLE scanner detects B1 with 3 consecutive scans for stability...")
        for i in range(1, 4):
            time.sleep(0.3)
            loc_manager.feed_ble_scan({"B1": -54.0, "B2": -85.0})
            print(f"   [Scan {i}] B1 RSSI: -54 dBm (Consecutive: {i})")

        loc = loc_manager.get_current_location()
        dest = "B3"
        route = router.find_route(loc["landmark_id"], dest)
        inst = instruction_gen.generate_instruction(loc, dest, route)

        render_dashboard(
            loc,
            destination="Computer Lab (B3)",
            instruction=inst,
            subsystems={"gps": "Unavailable", "ble": "Connected", "qr": "Standby"},
            esp32_status="Online" if esp32.is_connected else "Standby (Simulated)",
        )
        print(f"Calculated Route: {' -> '.join(route)}")
        print(f"Expected: Current=B1, Route=B1 -> B2 -> B3, Next Action={inst['command']}")
        assert route == ["B1", "B2", "B3"], f"Route mismatch: {route}"
        print(">>> TEST 1 PASSED! <<<\n")

    elif test_num == 2:
        print("\n--- TEST 2: GPS/Visual Loss Transition ---")
        print("1. User starts outside with reliable GPS.")
        gps_sys.set_status(reliable=True, confidence=0.92)
        loc = loc_manager.get_current_location()
        print(f"   Outdoor status: Source={loc['source']}, Confidence={int(loc['confidence']*100)}%")

        print("2. User walks into Central Corridor. Satellites drop...")
        gps_sys.set_indoor(True)
        print("   GPS confidence dropped to 15% (Unreliable).")

        print("3. Indoor BLE recovery activates. Scanning...")
        for i in range(1, 4):
            time.sleep(0.3)
            loc_manager.feed_ble_scan({"B2": -52.0, "B1": -78.0, "B3": -82.0})
            print(f"   [Scan {i}] BLE Landmark B2 detected at -52 dBm")

        loc = loc_manager.get_current_location()
        dest = "B5"
        route = router.find_route(loc["landmark_id"], dest)
        inst = instruction_gen.generate_instruction(loc, dest, route)

        render_dashboard(
            loc,
            destination="Library (B5)",
            instruction=inst,
            subsystems={"gps": "Unavailable (Signal Lost)", "ble": "Recovered (B2)", "qr": "Standby"},
            esp32_status="Online" if esp32.is_connected else "Standby (Simulated)",
        )
        print(f"Expected: Switched to BLE, Current=Central Corridor (B2), Route={' -> '.join(route)}")
        assert loc["source"] == "BLE" and loc["landmark_id"] == "B2"
        print(">>> TEST 2 PASSED! <<<\n")

    elif test_num == 3:
        print("\n--- TEST 3: BLE Position Recovery (At B3) ---")
        print("1. User reaches Computer Lab (B3).")
        for i in range(1, 4):
            time.sleep(0.3)
            loc_manager.feed_ble_scan({"B3": -50.0, "B2": -75.0})
            print(f"   [Scan {i}] Stable B3 detection (RSSI: -50 dBm)")

        loc = loc_manager.get_current_location()
        dest = "B5"
        route = router.find_route(loc["landmark_id"], dest)
        inst = instruction_gen.generate_instruction(loc, dest, route)

        render_dashboard(
            loc,
            destination="Library (B5)",
            instruction=inst,
            subsystems={"gps": "Unavailable", "ble": "Connected (B3)", "qr": "Standby"},
            esp32_status="Online" if esp32.is_connected else "Standby (Simulated)",
        )
        print(f"Expected: Current=B3, Recalculated Route={' -> '.join(route)}")
        assert route == ["B3", "B2", "B4", "B5"]
        print(">>> TEST 3 PASSED! <<<\n")

    elif test_num == 4:
        print("\n--- TEST 4: BLE Confidence Drop & Safe Low-Confidence Behavior ---")
        print("1. User moves into dead zone between landmarks.")
        loc_manager.reset_state()
        # Weak and ambiguous signal (< -90 dBm)
        loc_manager.feed_ble_scan({"B2": -92.0, "B4": -94.0})
        loc = loc_manager.get_current_location()
        inst = instruction_gen.generate_instruction(loc, destination_id="B5")

        render_dashboard(
            loc,
            destination="Library (B5)",
            instruction=inst,
            subsystems={"gps": "Unavailable", "ble": "Weak / Unreliable", "qr": "Standby"},
            esp32_status="Online" if esp32.is_connected else "Standby (Simulated)",
        )
        print("Verification:")
        print(f" - Safe mode active: {inst['safe_mode']}")
        print(f" - Command issued: {inst['command']} (Safe pattern, NOT guessing LEFT/RIGHT)")
        assert inst["safe_mode"] is True
        assert inst["command"] in ("UNKNOWN", "STOP")
        print(">>> TEST 4 PASSED (Safe behavior verified)! <<<\n")

    elif test_num == 5:
        print("\n--- TEST 5: QR Marker Explicit Fallback Recovery ---")
        print("1. User was in low-confidence UNKNOWN state.")
        print("2. User locates physical QR code on wall near Staircase (B4) and scans it...")
        loc_manager.feed_qr_payload("B4")
        loc = loc_manager.get_current_location()
        dest = "B5"
        route = router.find_route(loc["landmark_id"], dest)
        inst = instruction_gen.generate_instruction(loc, dest, route)

        render_dashboard(
            loc,
            destination="Library (B5)",
            instruction=inst,
            subsystems={"gps": "Unavailable", "ble": "Resuming", "qr": "Scanned (B4)"},
            esp32_status="Online" if esp32.is_connected else "Standby (Simulated)",
        )
        print(f"Verification:")
        print(f" - Source recovered: {loc['source']}")
        print(f" - Current landmark: {loc['landmark_id']} ({loc['name']})")
        print(f" - Confidence restored: {int(loc['confidence']*100)}%")
        print(f" - Navigation resumed. Next action: {inst['command']}")
        assert loc["source"] == "QR" and loc["landmark_id"] == "B4"
        assert loc["confidence"] >= 0.75
        print(">>> TEST 5 PASSED! <<<\n")


def interactive_menu():
    """Interactive CLI testing shell."""
    indoor_map = IndoorMap()
    indoor_map.load()

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
    esp32 = ESP32Client()

    active_dest = "B5"

    while True:
        print("\n=======================================================")
        print(" CampusEcho — Indoor Position Recovery Interactive CLI")
        print("=======================================================")
        print(" [1] Run Judge Test 1: Normal Localization (B1 -> B3)")
        print(" [2] Run Judge Test 2: GPS Loss -> BLE Recovery at B2")
        print(" [3] Run Judge Test 3: BLE B3 -> Library Route")
        print(" [4] Run Judge Test 4: BLE Confidence Drop (Safe Mode)")
        print(" [5] Run Judge Test 5: Optical QR Marker Recovery")
        print(" [A] Run All 5 Judge Tests Sequentially")
        print(" [S] Simulate BLE Scan (e.g. Near B2)")
        print(" [Q] Simulate QR Scan (e.g. B4)")
        print(" [D] Set Destination Landmark")
        print(" [E] Configure ESP32 Wi-Fi IP")
        print(" [P] Print Current Live Dashboard")
        print(" [X] Exit")
        print("=======================================================")

        choice = input("Enter selection: ").strip().upper()

        if choice == "1":
            run_judge_test(1)
        elif choice == "2":
            run_judge_test(2)
        elif choice == "3":
            run_judge_test(3)
        elif choice == "4":
            run_judge_test(4)
        elif choice == "5":
            run_judge_test(5)
        elif choice == "A":
            for t in range(1, 6):
                run_judge_test(t)
                time.sleep(1.0)
            print(">>> ALL 5 HACKATHON CHALLENGE TESTS PASSED! <<<")
        elif choice == "S":
            lm = input("Enter landmark ID to simulate nearby (B1-B5): ").strip().upper()
            if lm in indoor_map.nodes:
                for _ in range(3):
                    loc_manager.feed_ble_scan({lm: -52.0})
                print(f"Fed 3 stable scans for {lm}.")
            else:
                print("Invalid landmark.")
        elif choice == "Q":
            payload = input("Enter QR payload (e.g. B3): ").strip()
            loc_manager.feed_qr_payload(payload)
            print("QR payload processed.")
        elif choice == "D":
            dest = input("Enter destination landmark (B1-B5): ").strip().upper()
            if dest in indoor_map.nodes:
                active_dest = dest
                print(f"Destination set to {active_dest}")
            else:
                print("Invalid landmark.")
        elif choice == "E":
            ip = input("Enter ESP32 IP address: ").strip()
            esp32.set_ip(ip)
            print(f"ESP32 IP set to {ip}")
        elif choice == "P":
            loc = loc_manager.get_current_location()
            route = router.find_route(loc.get("landmark_id"), active_dest) if loc.get("landmark_id") else []
            inst = instruction_gen.generate_instruction(loc, active_dest, route)
            render_dashboard(
                loc,
                destination=active_dest,
                instruction=inst,
                subsystems={"gps": "Unavailable" if not gps_sys.is_reliable else "Active", "ble": "Active", "qr": "Standby"},
                esp32_status="Online" if esp32.is_connected else "Standby (Simulated)",
            )
        elif choice == "X":
            break


def main():
    parser = argparse.ArgumentParser(description="CampusEcho Indoor Recovery CLI")
    parser.add_argument("--test", type=int, choices=[1, 2, 3, 4, 5], help="Run a specific Judge test (1-5)")
    parser.add_argument("--all-tests", action="store_true", help="Run all 5 Judge tests")
    parser.add_argument("--esp32", type=str, help="ESP32 IP address")
    args = parser.parse_args()

    if args.test:
        run_judge_test(args.test, esp32_ip=args.esp32)
    elif args.all_tests:
        for t in range(1, 6):
            run_judge_test(t, esp32_ip=args.esp32)
            time.sleep(0.5)
        print("\n>>> ALL 5 HACKATHON CHALLENGE TESTS PASSED SUCCESSFULLY! <<<\n")
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
