"""Interactive CLI & Visual Demo for Phase 2 & Phase 6: CampusEcho Perception & Voice Narration Loop."""
import argparse
import sys
import time
from pathlib import Path
from typing import Optional
import cv2
import numpy as np

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from src.perception.detector import ObstacleDetector
from src.perception.models import DetectedObstacle
from src.perception.video_source import VideoSource
from src.notifications.haptic_bridge import HapticBridge
from src.decision.confidence_policy import ConfidencePolicy, ConfidenceTier, PolicyDecision
from src.notifications.mode_router import ModeRouter, OutputMode


def run_perception_demo(
    source_arg: str,
    no_gui: bool = False,
    max_frames: int = 1000,
    haptic_port: str = "auto",
    haptic_baud: int = 115200,
    cadence: int = 2,
    target_fps: float = 12.0,
    enable_voice: bool = True,
    speech_rate: int = 2,
    mode_str: str = "DUAL",
    model_name: str = "yolov8n.pt",
    max_alert_dist: float = 3.6,
):
    print("=" * 70)
    print("  CampusEcho - Perception Engine & Spoken Audio Narrator Demo")
    print(f"  ({model_name} + Heuristics + Voice TTS + ESP32 Haptic Wristband)")
    print("=" * 70)

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

    video_source = VideoSource(source=source, loop_file=True, target_fps=target_fps)
    detector = ObstacleDetector(
        model_name=model_name,
        confidence_threshold=0.45,          # Balanced confidence gate to detect hazards early
        alert_confidence_threshold=0.50,    # Secondary gate before haptic/audio alert
        max_alert_distance_m=max_alert_dist,# Calibrated alert distance threshold (default 3.6m)
        stability_required_sec=0.3,         # Responsive 0.3s debouncing for fast hazard warning
        enable_heuristics=True,
        inference_cadence=cadence           # Multi-rate perception: keyframe every N frames
    )

    # Initialize Decision Policy & ModeRouter (Phase 4 & 6)
    policy = ConfidencePolicy()
    active_mode = OutputMode[mode_str.upper()] if mode_str.upper() in OutputMode.__members__ else OutputMode.DUAL
    mode_router = ModeRouter(mode=active_mode)

    if enable_voice:
        print(f">> Initializing native desktop voice narrator (Rate: {speech_rate}, Mode: {active_mode.value})...")
        mode_router.enable_local_audio(enabled=True, speech_rate=speech_rate)
        # Greet user with startup confirmation audio
        mode_router.voice.speak("CampusEcho perception voice active.", priority="normal")
    else:
        print(">> Spoken audio output disabled by user.")

    # Initialize ESP32 Haptic Bridge
    bridge = HapticBridge()
    hardware_active = False
    resolved_port = "None"

    if haptic_port and haptic_port.lower() not in ("none", "disabled", "false"):
        resolved_port = haptic_port
        if resolved_port.lower() == "auto":
            resolved_port = HapticBridge.find_wristband_port() or "COM8"

        if resolved_port:
            print(f">> Connecting to ESP32 Wristband on {resolved_port} @ {haptic_baud} baud...")
            connected = bridge.connect(resolved_port, baudrate=haptic_baud, retries=3, retry_delay=0.8)
            if not connected:
                # Attempt auto-fallback to alternative candidate ports on the machine
                ports = HapticBridge.list_ports()
                candidate_ports = [p["port"] for p in ports if p["port"].upper() != resolved_port.upper()]
                for alt_port in candidate_ports:
                    print(f">> [FALLBACK] Could not open {resolved_port}. Attempting fallback to {alt_port}...")
                    if bridge.connect(alt_port, baudrate=haptic_baud, retries=2, retry_delay=0.5):
                        connected = True
                        resolved_port = alt_port
                        break

            if connected:
                hardware_active = True
                print(f">> [SUCCESS] ESP32 Haptic Wristband connected on {resolved_port}!")
                # Immediate tactile greeting so user verifies hardware connection
                bridge.send_raw("B,5,1\n")
                time.sleep(0.3)
                bridge.silence()
            else:
                print(f">> [WARNING] Could not connect to {resolved_port} or fallback ports.")
                print(">> Continuing with visual simulation (simulated haptic & direction signals active)...")
        else:
            print(">> [NOTICE] No ESP32 serial port detected. Running in visual simulation mode.")
    else:
        print(">> Haptic hardware output disabled by user.")

    win_name = "CampusEcho Perception & Voice Feed"
    if not no_gui:
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, 800, 600)
        try:
            cv2.setWindowProperty(win_name, cv2.WND_PROP_TOPMOST, 1)
        except Exception:
            pass

    print(f"\nStarting perception loop (Target: {target_fps:.0f} FPS, Cadence: {cadence})...")
    print("Press 'q' in the OpenCV window or close it to exit.\n")

    frame_idx = 0
    had_previous_obstacle = False
    current_spoken_banner = "Path is safe"
    current_tier_label = "CLEAR"
    current_tier_color = (0, 255, 0)  # Green
    last_haptic_cmd = "O,0,0\n"
    last_haptic_send_time = 0.0
    current_steer_dir = "straight"

    try:
        for frame in video_source.stream():
            frame_idx += 1

            # Process frame through perception pipeline (with inference cadence for 10-12 FPS)
            result = detector.process_frame(frame, debounce_frames=2)

            haptic_cmd = "O,0,0\n"
            current_steer_dir = "straight"

            if result.primary_obstacle:
                current_steer_dir = getattr(result.primary_obstacle, "steer_direction", "center")
                # Evaluate Confidence Policy (Phase 4)
                decision = policy.evaluate(result.primary_obstacle)
                dispatch_res = mode_router.handle_decision(decision)

                if dispatch_res.haptic_cmd:
                    # Translate internal code to firmware CSV format
                    haptic_cmd = HapticBridge.translate_to_firmware(dispatch_res.haptic_cmd)

                current_spoken_banner = dispatch_res.voice_text or decision.spoken_instruction
                current_tier_label = decision.tier.value
                if decision.tier == ConfidenceTier.BLOCKED:
                    current_tier_color = (0, 0, 255)    # Red
                elif decision.tier == ConfidenceTier.HEDGE:
                    current_tier_color = (0, 215, 255)  # Amber
                else:
                    current_tier_color = (255, 0, 255)  # Magenta

                had_previous_obstacle = True
            else:
                haptic_cmd = "O,0,0\n"
                current_steer_dir = "straight"
                if had_previous_obstacle:
                    if enable_voice and active_mode in (OutputMode.VOICE_ONLY, OutputMode.DUAL):
                        mode_router.voice.speak("Path clear.", priority="low")
                    current_spoken_banner = "Path clear."
                    had_previous_obstacle = False
                else:
                    current_spoken_banner = "Path clear."

                current_tier_label = "CLEAR"
                current_tier_color = (0, 255, 0)  # Green

            # Dispatch haptic feedback to ESP32 Wristband (or simulator) with deduplication & heartbeat
            now_t = time.time()
            if hardware_active:
                if haptic_cmd != last_haptic_cmd:
                    if haptic_cmd == "O,0,0\n":
                        bridge.silence()
                        print(f"   [HAPTIC TX: {resolved_port}] -> SILENCE (O,0,0)")
                    else:
                        bridge.send_raw(haptic_cmd)
                        steer_label = f"STEER {current_steer_dir.upper()}" if current_steer_dir != "straight" else "ALERT"
                        print(f"   [HAPTIC TX: {resolved_port}] -> {haptic_cmd.strip()} | {steer_label}")
                    last_haptic_cmd = haptic_cmd
                    last_haptic_send_time = now_t
                elif haptic_cmd != "O,0,0\n" and (now_t - last_haptic_send_time) >= 1.2:
                    # Heartbeat: maintain active vibration pattern without flooding serial buffer
                    bridge.send_raw(haptic_cmd)
                    last_haptic_send_time = now_t
            else:
                # Simulated hardware output
                if haptic_cmd != last_haptic_cmd:
                    if haptic_cmd != "O,0,0\n":
                        steer_label = f"STEER {current_steer_dir.upper()}" if current_steer_dir != "straight" else "ALERT"
                        print(f"   [SIM HAPTIC] -> {haptic_cmd.strip()} | {steer_label}")
                    last_haptic_cmd = haptic_cmd

            # Print telemetry to terminal
            haptic_tag = f" | Haptic: {haptic_cmd.strip():<5}" if hardware_active else f" | SimHaptic: {haptic_cmd.strip():<5}"
            voice_tag = f" | Voice: \"{current_spoken_banner}\"" if enable_voice else ""
            steer_tag = f" | Steer: {current_steer_dir.upper():<8}"
            hud_status = (
                f"[{current_tier_label}] {result.primary_obstacle.label.upper()} "
                f"({result.primary_obstacle.distance_m}m, {result.primary_obstacle.horizontal_position.upper()})"
                if result.primary_obstacle
                else "[CLEAR] Path is safe"
            )

            print(
                f"Frame {frame_idx:03d} | {hud_status:<36}{steer_tag} | "
                f"Latency: {result.processing_time_ms:4.1f}ms | FPS: {result.fps:4.1f}{haptic_tag}{voice_tag}"
            )

            # Visual Display with stylish HUD & Voice Narration Banner
            if not no_gui:
                annotated = detector.annotate_frame(frame, result)
                h, w = annotated.shape[:2]

                # Top Telemetry Badges
                hw_str = f"ESP32 [{resolved_port}]: {haptic_cmd.strip()}" if hardware_active else f"SIM HW: {haptic_cmd.strip()}"
                voice_status = f"Voice: ON [{speech_rate}]" if enable_voice else "Voice: OFF"
                steer_badge = f" | STEER: {current_steer_dir.upper()}" if current_steer_dir != "straight" else " | STEER: NONE"
                top_badge_text = f"FPS: {result.fps:4.1f} | Latency: {result.processing_time_ms:3.0f}ms | Cadence: {cadence}{steer_badge} | {hw_str} | {voice_status}"
                cv2.putText(annotated, top_badge_text, (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 0), 1)

                # Prominent Steering Arrow overlay if active
                if current_steer_dir == "right":
                    cv2.putText(annotated, ">> MOVE RIGHT >>", (int(w * 0.28), 135), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 165, 255), 2)
                elif current_steer_dir == "left":
                    cv2.putText(annotated, "<< MOVE LEFT <<", (int(w * 0.28), 135), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 165, 255), 2)

                # Bottom Voice Narration Subtitle Banner
                banner_y1 = h - 55
                banner_y2 = h - 15
                banner_x1 = 20
                banner_x2 = w - 20

                # Translucent dark pill background
                overlay = annotated.copy()
                cv2.rectangle(overlay, (banner_x1, banner_y1), (banner_x2, banner_y2), (20, 20, 20), -1)
                cv2.addWeighted(overlay, 0.75, annotated, 0.25, 0, annotated)

                # Color-coded border
                cv2.rectangle(annotated, (banner_x1, banner_y1), (banner_x2, banner_y2), current_tier_color, 2)

                # Icon/Tier and spoken text
                display_msg = f"VOICE: \"{current_spoken_banner}\""
                cv2.putText(
                    annotated,
                    display_msg,
                    (banner_x1 + 15, banner_y1 + 26),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    2
                )

                cv2.imshow(win_name, annotated)

                key = cv2.waitKey(10) & 0xFF
                if key == ord('q'):
                    print("\nExiting visual preview...")
                    break

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
        mode_router.close()
        if hardware_active:
            print("Silencing and closing ESP32 Haptic Bridge...")
            bridge.silence()
            bridge.close()
        video_source.release()
        if not no_gui:
            cv2.destroyAllWindows()

    print("\nPhase 2 & Phase 6 Perception & Voice Demo finished successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CampusEcho Perception & Spoken Voice Demo")
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
    parser.add_argument(
        "--cadence",
        type=int,
        default=2,
        help="Inference cadence: run full YOLO every N frames for rapid responsiveness (default: 2)"
    )
    parser.add_argument(
        "--target-fps",
        type=float,
        default=12.0,
        help="Target video playback FPS (default: 12.0)"
    )
    parser.add_argument(
        "--voice",
        dest="enable_voice",
        action="store_true",
        default=True,
        help="Enable spoken voice narrations through PC speakers (default: True)"
    )
    parser.add_argument(
        "--no-voice",
        dest="enable_voice",
        action="store_false",
        help="Disable spoken voice narrations"
    )
    parser.add_argument(
        "--speech-rate",
        type=int,
        default=2,
        help="Speech speed rate (-10 to 10, default: 2 for concise navigation pace)"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="DUAL",
        choices=["DUAL", "VOICE_ONLY", "HAPTIC_ONLY"],
        help="Output mode: DUAL, VOICE_ONLY, or HAPTIC_ONLY (default: DUAL)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="YOLO model weights to use (default: yolov8n.pt for fast, stable CPU inference)"
    )
    parser.add_argument(
        "--max-dist",
        type=float,
        default=3.6,
        help="Maximum distance threshold for alerts in meters (default: 3.6m)"
    )
    args = parser.parse_args()

    run_perception_demo(
        source_arg=args.source,
        no_gui=args.no_gui,
        max_frames=args.max_frames,
        haptic_port=args.haptic_port,
        haptic_baud=args.haptic_baud,
        cadence=args.cadence,
        target_fps=args.target_fps,
        enable_voice=args.enable_voice,
        speech_rate=args.speech_rate,
        mode_str=args.mode,
        model_name=args.model,
        max_alert_dist=args.max_dist,
    )
