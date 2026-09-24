"""
Signpost and Landmark OCR Reader for CampusEcho.
Uses EasyOCR with keyframe throttling and upper-frame ROI optimization.
"""
import re
import time
from typing import List, Optional, Tuple
import cv2
import numpy as np
from pydantic import BaseModel, Field


class SignDetection(BaseModel):
    """Represents a detected signboard or text banner."""
    text: str                                    # Normalized clean text (UPPERCASE)
    raw_text: str                                # Verbatim OCR string
    confidence: float                            # OCR model confidence [0.0 - 1.0]
    bbox: Tuple[int, int, int, int]              # (xmin, ymin, xmax, ymax) in full-frame coords


class SignpostReader:
    """
    Extracts text from video keyframes targeting campus signage,
    overhead boards, door plaques, and building markers.
    """

    def __init__(
        self,
        languages: Optional[List[str]] = None,
        gpu: Optional[bool] = None,
        min_confidence: float = 0.35,
        min_token_length: int = 2,
        keyframe_interval_s: float = 1.2
    ):
        self.languages = languages or ["en"]
        self.min_confidence = min_confidence
        self.min_token_length = min_token_length
        self.keyframe_interval_s = keyframe_interval_s
        self._last_ocr_time: float = 0.0
        self._reader = None

        # GPU auto-detection
        if gpu is None:
            try:
                import torch
                self.gpu = torch.cuda.is_available()
            except Exception:
                self.gpu = False
        else:
            self.gpu = gpu

    def _get_reader(self):
        """Lazy load EasyOCR reader so modules import instantly."""
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(self.languages, gpu=self.gpu)
        return self._reader

    def should_process_keyframe(self, now: Optional[float] = None) -> bool:
        """Determines if enough time has elapsed to process a new keyframe."""
        current_time = now if now is not None else time.time()
        return (current_time - self._last_ocr_time) >= self.keyframe_interval_s

    def read_signs(
        self,
        frame: np.ndarray,
        roi_upper_fraction: float = 0.65,
        force: bool = False,
        now: Optional[float] = None
    ) -> List[SignDetection]:
        """
        Reads signage from the upper portion of the frame where signs and plaques are located.
        
        Args:
            frame: BGR image frame
            roi_upper_fraction: Fraction of frame height from top to scan (default: top 65%)
            force: If True, bypasses keyframe throttling timer
            now: Current timestamp (optional, for simulation/testing)
        """
        current_time = now if now is not None else time.time()
        if not force and not self.should_process_keyframe(current_time):
            return []

        self._last_ocr_time = current_time

        h, w = frame.shape[:2]
        roi_h = max(30, int(h * roi_upper_fraction))
        roi = frame[0:roi_h, 0:w]

        reader = self._get_reader()
        # EasyOCR returns: [([ [x1,y1],[x2,y1],[x2,y2],[x1,y2] ], text, prob), ...]
        try:
            raw_results = reader.readtext(roi)
        except Exception as e:
            print(f"[SignpostReader] OCR reading error: {e}")
            return []

        detections: List[SignDetection] = []
        for bbox_coords, raw_text, prob in raw_results:
            if prob < self.min_confidence:
                continue

            cleaned_text = self.normalize_text(raw_text)
            if len(cleaned_text) < self.min_token_length:
                continue

            # Convert 4-point polygon to (xmin, ymin, xmax, ymax) in full-frame coords
            xs = [pt[0] for pt in bbox_coords]
            ys = [pt[1] for pt in bbox_coords]
            xmin = max(0, int(min(xs)))
            xmax = min(w, int(max(xs)))
            ymin = max(0, int(min(ys)))
            ymax = min(h, int(max(ys)))

            detections.append(
                SignDetection(
                    text=cleaned_text,
                    raw_text=raw_text.strip(),
                    confidence=float(prob),
                    bbox=(xmin, ymin, xmax, ymax)
                )
            )

        return detections

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalizes OCR text:
        - Uppercase
        - Strips noise characters while keeping letters, digits, spaces, and ampersands
        - Collapses repeated whitespace
        """
        text = text.upper().strip()
        text = re.sub(r'[^A-Z0-9\s&/-]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
