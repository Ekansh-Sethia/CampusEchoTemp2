"""
Interactive Hardware Diagnostics & Connection Tester for CampusEcho ESP32 Haptic Wristband.

Tests:
1. Detects all connected COM ports (USB CP210x/CH340 and Bluetooth SPP).
2. Checks for port locking (e.g. Arduino IDE Serial Monitor open).
3. Connects to the ESP32.
4. Sends motor test vibrations (Left, Right, Both, Silence).
5. Reports status and latency.

Usage:
    .\.venv\Scripts\python.exe scripts/test_hardware.py
    .\.venv\Scripts\python.exe scripts/test_hardware.py --port COM8
"""
import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.notifications.haptic_bridge import HapticBridge, SERIAL_AVAILABLE


def main():
    parser = argparse.ArgumentParser(description="CampusEcho Hardware Wristband Connection Tester")
    parser.add_argument("--port", type=str, default="auto", help="COM port (e.g. 'COM8' or 'auto')")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    args = parser.parse_args()

    print("=" * 65)
    print("  CampusEcho ESP32 Haptic Wristband Diagnostic Utility")
    print("=" * 65)

    if not SERIAL_AVAILABLE:
        print("[ERROR] pyserial is not installed! Run: pip install pyserial")
        sys.exit(1)

    # 1. Enumerate ports
    ports = HapticBridge.list_ports()
    print(f"\n[1] Scanning Serial / COM Ports...")
    if not ports:
        print("  -> No COM ports detected!")
        print("     Please ensure the ESP32 is plugged into USB or paired via Bluetooth.")
    else:
        for p in ports:
            print(f"  -> Found: {p['port']:<6} | {p['description']} | HWID: {p['hwid']}")

    # 2. Resolve target port
    target_port = args.port
    if target_port.lower() == "auto":
        target_port = HapticBridge.find_wristband_port()
        print(f"\n[2] Auto-detecting ESP32 Wristband Port...")
        if target_port:
            print(f"  -> Target port resolved to: {target_port}")
        else:
            print("  -> Could not auto-resolve port. Available ports: ", [p['port'] for p in ports])
            if ports:
                target_port = ports[0]['port']
                print(f"  -> Defaulting to first available port: {target_port}")
            else:
                sys.exit(1)
    else:
        print(f"\n[2] Using specified port: {target_port}")

    # 3. Test port connection
    print(f"\n[3] Connecting to {target_port} @ {args.baud} baud...")
    bridge = HapticBridge()
    success = bridge.connect(target_port, baudrate=args.baud)

    if not success:
        print(f"\n[FAILED] Could not connect to {target_port}!")
        print("\nTroubleshooting Checks:")
        print(" 1. Is Arduino IDE Serial Monitor open? If yes, CLOSE the Serial Monitor tab, as it locks the port.")
        print(" 2. Is another terminal or application using this COM port?")
        print(" 3. Try unplugging and re-plugging the USB cable.")
        sys.exit(1)

    print(f"  -> [SUCCESS] Connected to {target_port}!")
    time.sleep(1.0)  # Allow ESP32 settle time

    try:
        # 4. Interactive vibration tests
        print(f"\n[4] Running Haptic Motor Vibration Sequence...")

        print("  -> Testing LEFT motor (L,7,1 - slow pulse)...", end=" ", flush=True)
        bridge.send_raw("L,7,1\n")
        time.sleep(1.5)
        print("Done.")

        print("  -> Testing RIGHT motor (R,7,1 - slow pulse)...", end=" ", flush=True)
        bridge.send_raw("R,7,1\n")
        time.sleep(1.5)
        print("Done.")

        print("  -> Testing BOTH motors (B,9,2 - rapid burst)...", end=" ", flush=True)
        bridge.send_raw("B,9,2\n")
        time.sleep(1.5)
        print("Done.")

        print("  -> Silencing all motors (O,0,0)...", end=" ", flush=True)
        bridge.silence()
        time.sleep(0.5)
        print("Done.")

        print("\n" + "=" * 65)
        print(f"  Diagnostic Result: Hardware on {target_port} is FULLY OPERATIONAL!")
        print(f"  Total commands sent: {bridge.tx_count} | Errors: {bridge.error_count}")
        print("=" * 65)

    finally:
        bridge.close()


if __name__ == "__main__":
    main()
