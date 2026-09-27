"""
QR Marker Landmark Fallback Validator.
Decodes and validates QR code markers for explicit localization recovery.
Supports text payloads ("B3"), JSON payloads ({"type":"indoor_landmark","id":"B3"}),
and direct camera frame decoding with OpenCV.
"""
import json
import re
import time
from typing import Dict, List, Optional, Any, Union
import cv2
import numpy as np


class QRValidator:
    """
    Validates QR code scans to recover landmark position.
    QR scanning acts as a deterministic ground-truth position reset.
    """

    QR_VALID_DURATION_S = 20.0  # Time in seconds that a QR scan remains fresh

    def __init__(self, landmarks_config: Optional[List[Dict[str, Any]]] = None):
        self.landmarks_by_id: Dict[str, Dict[str, Any]] = {}
        if landmarks_config:
            for lm in landmarks_config:
                self.landmarks_by_id[lm["id"]] = lm

        self._detector: Optional[cv2.QRCodeDetector] = None
        self._last_qr_scan: Optional[Dict[str, Any]] = None
        self._last_scan_time: float = 0.0

    def _get_detector(self) -> cv2.QRCodeDetector:
        if self._detector is None:
            self._detector = cv2.QRCodeDetector()
        return self._detector

    def load_landmarks(self, landmarks_config: List[Dict[str, Any]]) -> None:
        self.landmarks_by_id.clear()
        for lm in landmarks_config:
            self.landmarks_by_id[lm["id"]] = lm

    def parse_payload(self, raw_text: str) -> Optional[str]:
        """
        Extracts landmark ID from QR payload string.
        Examples:
          "B3"
          "{"type": "indoor_landmark", "id": "B3"}"
          "campusecho://landmark/B3"
        """
        if not raw_text:
            return None
        text = raw_text.strip()

        # 1. Direct ID match (e.g. "B1", "B2", "B3", "B4", "B5")
        if text.upper() in self.landmarks_by_id:
            return text.upper()

        # 2. JSON format
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                lm_id = data.get("id") or data.get("landmark_id")
                if lm_id and str(lm_id).upper() in self.landmarks_by_id:
                    return str(lm_id).upper()
            except Exception:
                pass

        # 3. URI or path format e.g. landmark/B3 or #B3
        match = re.search(r"\b(B[1-9][0-9]?)\b", text, re.IGNORECASE)
        if match:
            found_id = match.group(1).upper()
            if not self.landmarks_by_id or found_id in self.landmarks_by_id:
                return found_id

        return None

    def scan_image(self, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        Detects and decodes QR code from a camera frame / numpy image.
        Returns the resolved landmark dictionary or None.
        """
        if frame is None or frame.size == 0:
            return None

        detector = self._get_detector()
        val, pts, _ = detector.detectAndDecode(frame)
        if val:
            return self.process_qr_text(val)
        return None

    def process_qr_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Processes scanned string payload, updates last scan state, and returns position.
        """
        landmark_id = self.parse_payload(text)
        if not landmark_id:
            return None

        lm_info = self.landmarks_by_id.get(landmark_id, {})
        now = time.time()
        self._last_scan_time = now

        result = {
            "source": "QR",
            "landmark_id": landmark_id,
            "name": lm_info.get("name", landmark_id),
            "zone": lm_info.get("zone", landmark_id),
            "floor": lm_info.get("floor", 0),
            "x": lm_info.get("x", 0),
            "y": lm_info.get("y", 0),
            "confidence": 1.0,
            "confidence_level": "HIGH",
            "raw_payload": text,
            "timestamp": now,
        }
        self._last_qr_scan = result
        return result

    def get_fresh_qr_position(self) -> Optional[Dict[str, Any]]:
        """
        Returns recent QR position if scanned within QR_VALID_DURATION_S,
        otherwise None.
        """
        if not self._last_qr_scan:
            return None
        now = time.time()
        if (now - self._last_scan_time) <= self.QR_VALID_DURATION_S:
            return self._last_qr_scan
        return None

    def clear(self) -> None:
        self._last_qr_scan = None
        self._last_scan_time = 0.0
