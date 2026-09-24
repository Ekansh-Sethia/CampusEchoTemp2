"""
Phase 3 Demo: Signpost Reading & Landmark Localization Engine
Processes images, video feeds, or webcams to read campus signage, match landmarks,
and update topological navigation progress in real time.
"""
import argparse
from pathlib import Path
import time
import cv2
import numpy as np

from src.perception.text_reader import SignpostReader
from src.routing.graph import CampusGraph
from src.routing.navigator import CampusNavigator


def parse_args():
    parser = argparse.ArgumentParser(
        description="CampusEcho Phase 3 Demo: EasyOCR Sign Reading & Landmark Localization"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="data/landmarks",
        help="Path to an image file, an image directory, a video file, or camera index (e.g., '0')"
    )
    parser.add_argument(
        "--start",
        type=str,
        default="golden_gate",
        help="Starting node ID from campus_graph.json (default: 'golden_gate')"
    )
    parser.add_argument(
        "--destination",
        type=str,
        default="silveria_hall",
        help="Destination node ID from campus_graph.json (default: 'silveria_hall')"
    )
    parser.add_argument(
        "--graph",
        type=str,
        default="data/campus_graph.json",
        help="Path to campus_graph.json"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.2,
        help="Seconds between keyframe OCR extraction (default: 1.2s)"
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run in headless terminal-only mode without OpenCV GUI window"
    )
    return parser.parse_args()


def load_images_or_stream(source: str):
    """
    Yields (frame, source_name, is_single_image) from the specified input source.
    """
    path = Path(source)

    # 1. Image Directory
    if path.is_dir():
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        files = sorted([f for f in path.iterdir() if f.suffix.lower() in image_extensions])
        if not files:
            raise FileNotFoundError(f"No image files found in directory: {source}")
        for f in files:
            img = cv2.imread(str(f))
            if img is not None:
                yield img, f.name, True
        return

    # 2. Single Image File
    if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"Failed to read image at: {source}")
        yield img, path.name, True
        return

    # 3. Video File or Webcam
    is_cam = source.isdigit()
    cap = cv2.VideoCapture(int(source) if is_cam else source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")

    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1
            yield frame, f"Frame {frame_idx:04d}", False
    finally:
        cap.release()


def draw_hud(
    frame: np.ndarray,
    navigator: CampusNavigator,
    detections: list,
    last_event_msg: str,
    fps: float
) -> np.ndarray:
    """Renders real-time HUD with sign bounding boxes and navigation status."""
    vis = frame.copy()
    h, w = vis.shape[:2]

    # Draw OCR bounding boxes
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 120), 2)
        label = f"{det.text} ({det.confidence:.2f})"
        cv2.putText(
            vis, label, (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 120), 2, cv2.LINE_AA
        )

    # Top Status Banner (Dark Translucent Bar)
    banner_h = 75
    overlay = vis.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), (20, 20, 25), -1)
    cv2.addWeighted(overlay, 0.75, vis, 0.25, 0, vis)

    curr_label = navigator.graph.nodes[navigator.current_node_id].label if navigator.current_node_id else "Unknown"
    dest_label = navigator.graph.nodes[navigator.destination_node_id].label if navigator.destination_node_id else "None"
    rem_dist = navigator.get_remaining_distance()

    cv2.putText(
        vis, f"LOCATION: {curr_label}", (15, 25),
        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA
    )
    cv2.putText(
        vis, f"DESTINATION: {dest_label} | REMAINING: {rem_dist}m | FPS: {fps:.1f}", (15, 55),
        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (220, 220, 220), 1, cv2.LINE_AA
    )

    # Bottom Audio Guidance Banner
    bottom_h = 55
    overlay2 = vis.copy()
    cv2.rectangle(overlay2, (0, h - bottom_h), (w, h), (15, 20, 35), -1)
    cv2.addWeighted(overlay2, 0.80, vis, 0.20, 0, vis)

    instruction = last_event_msg or navigator.get_current_instruction()
    cv2.putText(
        vis, f">> {instruction}", (15, h - 20),
        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (100, 255, 200), 1, cv2.LINE_AA
    )

    return vis


def run_demo():
    args = parse_args()
    print("=" * 70)
    print("CampusEcho Phase 3 Demo: Signpost Reading & Landmark Localization")
    print("=" * 70)

    # Load Graph & Navigator
    graph_path = Path(args.graph)
    if not graph_path.exists():
        print(f"Error: Graph file not found: {graph_path}")
        return

    graph = CampusGraph(str(graph_path))
    navigator = CampusNavigator(graph)
    route = navigator.start_navigation(args.start, args.destination)

    print(f"Planned Route: {' -> '.join(route.path)}")
    print(f"Total Distance: {route.total_distance_m}m")
    print(f"Initial Instruction: {navigator.get_current_instruction()}\n")

    # Initialize OCR Reader
    print("[SignpostReader] Loading OCR engine (English)...")
    reader = SignpostReader(languages=["en"], keyframe_interval_s=args.interval)
    print("[SignpostReader] Ready.\n")

    window_name = "CampusEcho Phase 3: Landmark Localization"
    if not args.no_gui:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 960, 720)

    last_event_msg = ""
    last_ocr_time = 0.0
    frame_count = 0
    t_start = time.time()

    try:
        for frame, source_name, is_single_image in load_images_or_stream(args.source):
            frame_count += 1
            now = time.time()

            # For static images or image directories, force OCR on every frame
            should_ocr = is_single_image or reader.should_process_keyframe(now)
            detections = []
            if should_ocr:
                t0 = time.time()
                detections = reader.read_signs(frame, force=is_single_image)
                ocr_dt = time.time() - t0

                if detections:
                    print(f"[{source_name}] OCR detected {len(detections)} sign(s) ({ocr_dt*1000:.1f}ms):")
                    for d in detections:
                        print(f"    - \"{d.text}\" (conf: {d.confidence:.2f})")

                    event = navigator.process_sign_detections(detections)
                    if event:
                        last_event_msg = event.voice_instruction
                        print(f"  >>> [NAV EVENT: {event.event_type}]")
                        print(f"      Matched: \"{event.matched_sign}\" -> Node: {event.node_id}")
                        print(f"      Voice: \"{event.voice_instruction}\"")
                        print(f"      Remaining Distance: {event.remaining_distance_m}m\n")

            fps = frame_count / max(0.001, (time.time() - t_start))

            if not args.no_gui:
                vis = draw_hud(frame, navigator, detections, last_event_msg, fps)
                cv2.imshow(window_name, vis)

                # Pause longer for static images so user can inspect
                wait_time = 1500 if is_single_image else 1
                key = cv2.waitKey(wait_time) & 0xFF
                if key == ord('q') or key == 27:
                    print("Exiting demo...")
                    break
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        if not args.no_gui:
            cv2.destroyAllWindows()

    print("=" * 70)
    print("Phase 3 Localization Demo completed!")
    print(f"Final Node: {navigator.current_node_id} ({navigator.graph.nodes[navigator.current_node_id].label})")
    print(f"Destination: {navigator.destination_node_id} | Completed: {navigator.current_node_id == navigator.destination_node_id}")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
