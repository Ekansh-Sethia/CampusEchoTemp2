"""Interactive CLI & Visual Demo for Phase 2: CampusEcho Perception Loop."""
import argparse
import sys
import time
from pathlib import Path
from typing import Optional
import cv2

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from src.perception.detector import ObstacleDetector
from src.perception.models import DetectedObstacle
from src.perception.video_source import VideoSource
from src.notifications.haptic_bridge import HapticBridge


def map_obstacle_to_haptic(obstacle: Optional[DetectedObstacle]) -> str:
    """Maps a detected primary obstacle to an ESP32 firmware CSV vibration command."""
    if not obstacle or not obstacle.in_walking_lane:
        return "O,0,0\n"

    # Determine motor side
    pos = (obstacle.horizontal_position or "center").lower()
    if pos == "left":
        side = "L"
    elif pos == "right":
        side = "R"
    else:
        side = "B"

    # Determine intensity and pattern based on urgency
    urgency = (obstacle.urgency or "low").lower()
    if urgency == "critical":
        return f"{side},9,2\n"  # Max strength, rapid pulse
    elif urgency == "high":
        return f"{side},7,3\n"  # Strong strength, double-pulse
    else:
        return f"{side},5,1\n"  # Medium strength, slow pulse


def run_perception_demo(
    source_arg: str,
    no_gui: bool = False,
    max_frames: int = 1000,
    haptic_port: str = "auto",
    haptic_baud: int = 115200,
):
    print("=" * 65)
    print("  CampusEcho - Phase 2 Perception Engine Demo")
    print("  (YOLOv8 + Hazard Heuristics + ESP32 Haptic Wristband)")
    print("=" * 65)

    test_frames_dir = Path(__file__).parent / "data" / "test_frames"

    # Resolve video/camera source
    if source_arg == "test_frames":
        source = test_frames_dir
        print(f">> Using test frames directory: {test_frames_dir}")
    elif source_arg.isdigit():
        source = int(source_arg)
        print(f">> Using live webcam device index: {source}")
    else:
        source = Path(source_arg)
        print(f">> Using video file / image source: {source}")

    video_source = VideoSource(source=source, loop_file=True, target_fps=10.0)
    detector = ObstacleDetector(confidence_threshold=0.35, enable_heuristics=True)

    # Initialize ESP32 Haptic Bridge
    bridge = HapticBridge()
    hardware_active = False

    if haptic_port and haptic_port.lower() not in ("none", "disabled", "false"):
        resolved_port = haptic_port
        if resolved_port.lower() == "auto":
            resolved_port = HapticBridge.find_wristband_port()

        if resolved_port:
            print(f">> Connecting to ESP32 Wristband on {resolved_port} @ {haptic_baud} baud...")
            connected = bridge.connect(resolved_port, baudrate=haptic_baud)
            if connected:
                hardware_active = True
                print(f">> [SUCCESS] ESP32 Haptic Wristband connected on {resolved_port}!")
                # Give user a brief 200ms power-on confirmation pulse
                bridge.send_raw("B,5,1\n")
                time.sleep(0.3)
                bridge.silence()
            else:
                print(f">> [WARNING] Could not connect to {resolved_port}. Is Arduino IDE Serial Monitor open?")
                print(">> Continuing with visual simulation...")
        else:
            print(">> [NOTICE] No ESP32 serial port detected. Running in visual-only mode.")
    else:
        print(">> Haptic hardware output disabled by user.")

    win_name = "CampusEcho Perception Feed (Phase 2)"
    if not no_gui:
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, 800, 600)
        # Force window to stay visible on top of IDE/terminal
        try:
            cv2.setWindowProperty(win_name, cv2.WND_PROP_TOPMOST, 1)
        except Exception:
            pass

    print("\nStarting perception loop...")
    print("Press 'q' in the OpenCV window or close it to exit.\n")

    frame_idx = 0
    try:
        for frame in video_source.stream():
            frame_idx += 1

            # Process frame through perception pipeline
            result = detector.process_frame(frame, debounce_frames=2)

            # Dispatch haptic feedback to ESP32 Wristband
            haptic_cmd = map_obstacle_to_haptic(result.primary_obstacle)
            if hardware_active:
                bridge.send_raw(haptic_cmd)

            # Print telemetry to terminal
            haptic_tag = f" | Haptic: {haptic_cmd.strip():<5}" if hardware_active else ""
            hud_status = (
                f"[HAZARD] {result.primary_obstacle.label.upper()} "
                f"({result.primary_obstacle.distance_m}m, {result.primary_obstacle.urgency.upper()})"
                if result.primary_obstacle
                else "[CLEAR] Path is safe"
            )

            print(
                f"Frame {frame_idx:03d} | {hud_status:<40} | "
                f"Latency: {result.processing_time_ms:4.1f}ms | FPS: {result.fps:4.1f}{haptic_tag} | "
                f"Obstacles: {len(result.obstacles)}"
            )

            for obs in result.obstacles:
                lane_flag = "IN LANE" if obs.in_walking_lane else "off-path"
                shd_str = f" | ShdLikelihood: {obs.shadow_likelihood:.2f}" if obs.shadow_likelihood > 0 else ""
                print(
                    f"    -> {obs.label:<12} | Conf: {obs.confidence:.2f}{shd_str} | "
                    f"Dist: {obs.distance_m:4.1f}m | Pos: {obs.horizontal_position:<6} | {lane_flag}"
                )

            # Visual Display
            if not no_gui:
                annotated = detector.annotate_frame(frame, result)
                if hardware_active:
                    cv2.putText(
                        annotated,
                        f"Haptic HW: {haptic_cmd.strip()}",
                        (10, 85),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 255, 255),
                        2
                    )
                cv2.imshow(win_name, annotated)

                key = cv2.waitKey(10) & 0xFF
                if key == ord('q'):
                    print("\nExiting visual preview...")
                    break

                # If the window was closed with 'X', exit loop
                try:
                    if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
                        print("\nWindow closed by user. Exiting...")
                        break
                except Exception:
                    pass

            if max_frames and frame_idx >= max_frames:
                print(f"\nReached max demo frames ({max_frames}).")
                break

    finally:
        if hardware_active:
            print("Silencing and closing ESP32 Haptic Bridge...")
            bridge.silence()
            bridge.close()
        video_source.release()
        if not no_gui:
            cv2.destroyAllWindows()

    print("\nPhase 2 Perception Demo finished successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CampusEcho Perception Demo")
    parser.add_argument(
        "--source",
        type=str,
        default="test_frames",
        help="Source: 'test_frames', webcam index '0', or path to video file"
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run in headless terminal-only mode without opening OpenCV window"
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=1000,
        help="Maximum frames to process in demo (default: 1000)"
    )
    parser.add_argument(
        "--haptic-port",
        type=str,
        default="auto",
        help="COM port for ESP32 wristband (default: 'auto', or 'COM8', 'none' to disable)"
    )
    parser.add_argument(
        "--haptic-baud",
        type=int,
        default=115200,
        help="Baud rate for ESP32 wristband (default: 115200)"
    )
    args = parser.parse_args()

    run_perception_demo(
        source_arg=args.source,
        no_gui=args.no_gui,
        max_frames=args.max_frames,
        haptic_port=args.haptic_port,
        haptic_baud=args.haptic_baud,
    )
