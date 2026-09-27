"""
Unified Localization Manager.
Arbitrates between GPS, Visual, BLE Landmark Recovery, QR Code Fallback,
Last-Known Position timeout, and UNKNOWN safe state.
"""
import time
from typing import Dict, List, Optional, Any

from backend.localization.gps import GPSSystem
from backend.localization.visual import VisualLocalizationSystem
from backend.localization.ble import BLELandmarkManager
from backend.localization.qr import QRValidator


class LocalizationManager:
    """
    Central localization arbiter implementing the priority chain:
    1. GPS / Visual (if outdoor fix is reliable)
    2. BLE Landmark Recovery (smoothed zone matching)
    3. QR Fallback (explicit optical scan)
    4. Last-Known Position (time-decayed buffer, max 6s)
    5. UNKNOWN (safe state: triggers QR/landmark recovery prompt)
    """

    CONFIDENCE_HIGH_THRESHOLD = 0.75
    CONFIDENCE_MEDIUM_THRESHOLD = 0.50

    # How long last known position is retained before expiring to UNKNOWN
    LAST_KNOWN_TIMEOUT_S = 6.0

    def __init__(
        self,
        landmarks_config: Optional[List[Dict[str, Any]]] = None,
        gps: Optional[GPSSystem] = None,
        visual: Optional[VisualLocalizationSystem] = None,
        ble: Optional[BLELandmarkManager] = None,
        qr: Optional[QRValidator] = None,
    ):
        self.landmarks_config = landmarks_config or []
        self.gps = gps or GPSSystem(initial_reliable=False, initial_confidence=0.15)
        self.visual = visual or VisualLocalizationSystem(initial_reliable=False, initial_confidence=0.20)
        self.ble = ble or BLELandmarkManager(self.landmarks_config)
        self.qr = qr or QRValidator(self.landmarks_config)

        # Retained state
        self._last_known_location: Optional[Dict[str, Any]] = None
        self._last_known_timestamp: float = 0.0

    def update_landmarks(self, landmarks_config: List[Dict[str, Any]]) -> None:
        self.landmarks_config = landmarks_config
        self.ble.load_landmarks(landmarks_config)
        self.qr.load_landmarks(landmarks_config)

    def get_current_location(self) -> Dict[str, Any]:
        """
        Determines current best location object based on priority:
        GPS/Visual -> BLE -> QR -> Last Known -> UNKNOWN
        """
        now = time.time()

        # 1. Check GPS & Visual (Outdoor)
        if self.gps.is_reliable:
            gps_status = self.gps.get_status()
            loc = {
                "source": "GPS",
                "landmark_id": None,
                "name": "Outdoor GPS Fix",
                "zone": "Outdoor Campus",
                "floor": 0,
                "x": 0,
                "y": 0,
                "lat": gps_status.get("lat"),
                "lon": gps_status.get("lon"),
                "confidence": gps_status["confidence"],
                "confidence_level": "HIGH" if gps_status["confidence"] >= self.CONFIDENCE_HIGH_THRESHOLD else "MEDIUM",
                "timestamp": now,
            }
            self._save_last_known(loc)
            return loc

        if self.visual.is_reliable:
            vis_status = self.visual.get_status()
            loc = {
                "source": "VISUAL",
                "landmark_id": None,
                "name": "Visual Odometry Fix",
                "zone": "Outdoor Campus",
                "floor": 0,
                "x": 0,
                "y": 0,
                "confidence": vis_status["confidence"],
                "confidence_level": "HIGH" if vis_status["confidence"] >= self.CONFIDENCE_HIGH_THRESHOLD else "MEDIUM",
                "timestamp": now,
            }
            self._save_last_known(loc)
            return loc

        # 2. Check BLE Landmark Recovery
        ble_estimate = self.ble.get_current_estimate()
        if ble_estimate and ble_estimate["confidence"] >= self.CONFIDENCE_MEDIUM_THRESHOLD:
            self._save_last_known(ble_estimate)
            return ble_estimate

        # 3. Check QR Fallback
        fresh_qr = self.qr.get_fresh_qr_position()
        if fresh_qr:
            self._save_last_known(fresh_qr)
            return fresh_qr

        # 4. Check Fresh Last-Known Position (Grace period with degraded confidence)
        if self._last_known_location and (now - self._last_known_timestamp) <= self.LAST_KNOWN_TIMEOUT_S:
            elapsed = now - self._last_known_timestamp
            degraded_conf = max(0.20, 0.49 - (0.05 * elapsed))
            return {
                "source": "LAST_KNOWN",
                "landmark_id": self._last_known_location.get("landmark_id"),
                "name": self._last_known_location.get("name", "Unknown"),
                "zone": self._last_known_location.get("zone", "Unknown"),
                "floor": self._last_known_location.get("floor", 0),
                "x": self._last_known_location.get("x", 0),
                "y": self._last_known_location.get("y", 0),
                "confidence": round(degraded_conf, 2),
                "confidence_level": "LOW",
                "last_confirmed_source": self._last_known_location.get("source"),
                "age_seconds": round(elapsed, 1),
                "timestamp": now,
            }

        # 5. UNKNOWN State (Spec Section 16: Safe low-confidence behavior)
        # Low confidence -> Never guess LEFT or RIGHT.
        return {
            "source": "UNKNOWN",
            "landmark_id": None,
            "name": "Location Uncertain",
            "zone": "Unknown",
            "floor": 0,
            "x": None,
            "y": None,
            "confidence": 0.0,
            "confidence_level": "LOW",
            "action_required": "Scan nearby QR landmark or move toward beacon",
            "timestamp": now,
        }

    def _save_last_known(self, loc: Dict[str, Any]) -> None:
        if loc and loc.get("source") not in ("LAST_KNOWN", "UNKNOWN"):
            self._last_known_location = loc
            self._last_known_timestamp = time.time()

    def feed_ble_scan(self, scan_readings: Dict[str, float]) -> Optional[Dict[str, Any]]:
        """Feeds a BLE scan batch to the manager."""
        return self.ble.process_scan(scan_readings)

    def feed_qr_payload(self, payload: str) -> Optional[Dict[str, Any]]:
        """Feeds a QR code text payload to the manager."""
        return self.qr.process_qr_text(payload)

    def reset_state(self) -> None:
        """Full reset of all sensors and history."""
        self.ble.reset()
        self.qr.clear()
        self._last_known_location = None
        self._last_known_timestamp = 0.0
