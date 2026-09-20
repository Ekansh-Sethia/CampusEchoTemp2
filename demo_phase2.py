"""Interactive CLI & Visual Demo for Phase 2: CampusEcho Perception Loop."""
import argparse
import sys
import time
from pathlib import Path
import cv2

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from src.perception.detector import ObstacleDetector
from src.perception.video_source import VideoSource


def run_perception_demo(source_arg: str, no_gui: bool = False, max_frames: int = 100):
    print("=" * 65)
    print("  CampusEcho - Phase 2 Perception Engine Demo")
    print("  (YOLOv8n + Hazard Heuristics + Distance Estimation)")
    print("=" * 65)

    test_frames_dir = Path(__file__).parent / "data" / "test_frames"

    # Resolve source
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

    print("\nStarting perception loop...")
    print("Press 'q' in the OpenCV window to exit.\n")

    frame_idx = 0
    try:
        for frame in video_source.stream():
            frame_idx += 1

            # Process frame through perception pipeline
            result = detector.process_frame(frame, debounce_frames=2)

            # Print telemetry to terminal
            hud_status = (
                f"[HAZARD] {result.primary_obstacle.label.upper()} "
                f"({result.primary_obstacle.distance_m}m, {result.primary_obstacle.urgency.upper()})"
                if result.primary_obstacle
                else "[CLEAR] Path is safe"
            )

            print(
                f"Frame {frame_idx:03d} | {hud_status:<40} | "
                f"Latency: {result.processing_time_ms:4.1f}ms | FPS: {result.fps:4.1f} | "
                f"Obstacles in Frame: {len(result.obstacles)}"
            )

            for obs in result.obstacles:
                lane_flag = "IN LANE" if obs.in_walking_lane else "off-path"
                print(
                    f"    -> {obs.label:<12} | Conf: {obs.confidence:.2f} | "
                    f"Dist: {obs.distance_m:4.1f}m | Pos: {obs.horizontal_position:<6} | {lane_flag}"
                )

            # Visual Display
            if not no_gui:
                annotated = detector.annotate_frame(frame, result)
                cv2.imshow("CampusEcho Perception Feed (Phase 2)", annotated)

                key = cv2.waitKey(100) & 0xFF
                if key == ord('q'):
                    print("\nExiting visual preview...")
                    break

            if max_frames and frame_idx >= max_frames:
                print(f"\nReached max demo frames ({max_frames}).")
                break

    finally:
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
        default=25,
        help="Maximum frames to process in demo (default: 25)"
    )
    args = parser.parse_args()

    run_perception_demo(source_arg=args.source, no_gui=args.no_gui, max_frames=args.max_frames)
