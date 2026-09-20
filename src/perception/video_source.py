"""Video capture source supporting live webcams, pre-recorded videos, and test image sequences."""
import time
from pathlib import Path
from typing import Iterator, Optional, Tuple, Union
import cv2
import numpy as np


class VideoSource:
    """Provides video frames from a live webcam, video file, or looping image directory."""

    def __init__(
        self,
        source: Union[int, str, Path] = 0,
        loop_file: bool = True,
        target_fps: float = 15.0
    ):
        self.source = source
        self.loop_file = loop_file
        self.target_fps = target_fps
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_image_dir: bool = False
        self.image_files: list[Path] = []
        self.image_index: int = 0
        self.is_opened: bool = False
        self._init_source()

    def _init_source(self) -> None:
        """Initializes either the VideoCapture device or the image directory list."""
        if isinstance(self.source, (str, Path)):
            path = Path(self.source)
            if path.is_dir():
                # Directory of test images
                self.is_image_dir = True
                valid_exts = {".jpg", ".jpeg", ".png", ".bmp"}
                self.image_files = sorted([
                    p for p in path.iterdir() if p.suffix.lower() in valid_exts
                ])
                if not self.image_files:
                    raise ValueError(f"No image files found in directory: {path}")
                self.is_opened = True
                return

            if path.is_file():
                # Video file
                self.cap = cv2.VideoCapture(str(path))
                self.is_opened = self.cap.isOpened()
                if not self.is_opened:
                    raise ValueError(f"Could not open video file: {path}")
                return

        # Webcam device index
        device_id = int(self.source) if str(self.source).isdigit() else 0
        self.cap = cv2.VideoCapture(device_id)
        # Set common resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.is_opened = self.cap.isOpened()

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Reads the next available frame.
        Loops automatically if reading from a video file or image directory and loop_file=True.
        """
        if self.is_image_dir:
            if not self.image_files:
                return False, None
            img_path = self.image_files[self.image_index]
            frame = cv2.imread(str(img_path))
            if self.loop_file:
                self.image_index = (self.image_index + 1) % len(self.image_files)
            else:
                self.image_index = min(len(self.image_files) - 1, self.image_index + 1)
            return (frame is not None), frame

        if self.cap is None or not self.cap.isOpened():
            return False, None

        ret, frame = self.cap.read()
        if not ret and self.loop_file and isinstance(self.source, (str, Path)):
            # Loop video file back to beginning
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()

        return ret, frame

    def stream(self) -> Iterator[np.ndarray]:
        """Generator yielding frames at roughly target_fps rate."""
        frame_delay = 1.0 / self.target_fps
        while self.is_opened:
            start_t = time.time()
            ret, frame = self.read_frame()
            if not ret or frame is None:
                break
            yield frame
            elapsed = time.time() - start_t
            if elapsed < frame_delay:
                time.sleep(frame_delay - elapsed)

    def release(self) -> None:
        """Releases camera/video resources."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.is_opened = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
