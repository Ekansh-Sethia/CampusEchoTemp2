"""
BLE Landmark Localization & Smoothing Engine.
Implements:
- Strongest stable landmark -> Zone matching
- Consecutive scan hysteresis (prevents rapid jumping from noisy frames)
- Multi-factor confidence metric (0.0 to 1.0; High, Medium, Low)
- Scan history tracking
"""
import time
from typing import Dict, List, Optional, Tuple, Any


class BLELandmarkManager:
    """
    Processes incoming BLE scan data (landmark IDs and RSSI readings).
    Applies smoothing hysteresis and calculates localization confidence.
    """

    # Threshold constants
    CONF_HIGH_MIN = 0.75
    CONF_MEDIUM_MIN = 0.50

    # RSSI normalization boundaries (dBm)
    RSSI_EXCELLENT = -50.0  # >= -50 dBm -> 1.0 signal factor
    RSSI_POOR = -90.0       # <= -90 dBm -> 0.0 signal factor

    # Minimum consecutive matching scans required to switch active landmark
    REQUIRED_CONSECUTIVE_SWITCH = 3

    # Scan staleness timeout (seconds)
    STALE_TIMEOUT_S = 5.0

    def __init__(self, landmarks_config: Optional[List[Dict[str, Any]]] = None):
        """
        landmarks_config: list of dicts with keys 'id', 'name', 'floor', 'zone', 'x', 'y'
        """
        self.landmarks_by_id: Dict[str, Dict[str, Any]] = {}
        if landmarks_config:
            for lm in landmarks_config:
                self.landmarks_by_id[lm["id"]] = lm

        # Active smoothed state
        self._current_landmark_id: Optional[str] = None
        self._current_rssi: float = -100.0
        self._consecutive_matching_count: int = 0
        self._last_scan_time: float = 0.0

        # Candidate buffer for switching hysteresis
        self._candidate_landmark_id: Optional[str] = None
        self._candidate_consecutive_count: int = 0

        # Recent history of raw scans for stability calculation
        self._recent_scans: List[Dict[str, float]] = []
        self._max_history = 10

    def load_landmarks(self, landmarks_config: List[Dict[str, Any]]) -> None:
        """Loads or reloads landmark metadata."""
        self.landmarks_by_id.clear()
        for lm in landmarks_config:
            self.landmarks_by_id[lm["id"]] = lm

    def process_scan(self, scan_readings: Dict[str, float]) -> Optional[Dict[str, Any]]:
        """
        Processes a raw scan dictionary: { landmark_id: rssi_in_dbm, ... }
        Example: { "B1": -58.0, "B2": -82.0 }

        Returns the resolved landmark dictionary or None if no valid landmark.
        """
        now = time.time()
        self._last_scan_time = now

        # Filter only known registered landmarks
        valid_readings = {
            k: v for k, v in scan_readings.items()
            if (not self.landmarks_by_id or k in self.landmarks_by_id) and v > -120.0
        }

        if not valid_readings:
            # No landmarks detected in this scan
            self._consecutive_matching_count = max(0, self._consecutive_matching_count - 1)
            return self.get_current_estimate()

        # Append to sliding history window
        self._recent_scans.append(valid_readings)
        if len(self._recent_scans) > self._max_history:
            self._recent_scans.pop(0)

        # Identify strongest landmark in this scan
        sorted_beacons = sorted(valid_readings.items(), key=lambda item: item[1], reverse=True)
        strongest_id, strongest_rssi = sorted_beacons[0]

        # Apply consecutive scan hysteresis (Section 12 of spec)
        if self._current_landmark_id is None:
            # First initialization
            self._current_landmark_id = strongest_id
            self._current_rssi = strongest_rssi
            self._consecutive_matching_count = 1
            self._candidate_landmark_id = None
            self._candidate_consecutive_count = 0
        elif strongest_id == self._current_landmark_id:
            # Confirmation of current landmark
            self._consecutive_matching_count += 1
            # Exponential moving average for RSSI to reduce jitter
            alpha = 0.4
            self._current_rssi = (alpha * strongest_rssi) + ((1.0 - alpha) * self._current_rssi)
            # Reset switch candidate
            self._candidate_landmark_id = None
            self._candidate_consecutive_count = 0
        else:
            # Different candidate observed
            if strongest_id == self._candidate_landmark_id:
                self._candidate_consecutive_count += 1
            else:
                self._candidate_landmark_id = strongest_id
                self._candidate_consecutive_count = 1

            # Check if candidate satisfies required hysteresis threshold
            if self._candidate_consecutive_count >= self.REQUIRED_CONSECUTIVE_SWITCH:
                self._current_landmark_id = self._candidate_landmark_id
                self._current_rssi = strongest_rssi
                self._consecutive_matching_count = self._candidate_consecutive_count
                self._candidate_landmark_id = None
                self._candidate_consecutive_count = 0
            else:
                # Still holding current landmark until threshold met
                # Slight decay on current match count
                self._consecutive_matching_count = max(1, self._consecutive_matching_count - 1)

        return self.get_current_estimate()

    def calculate_confidence(self) -> float:
        """
        Calculates confidence score between 0.0 and 1.0 based on:
        1. RSSI signal strength factor (normalized -90 dBm to -50 dBm)
        2. Consecutive scan stability factor (up to 1.0 at >= 3 scans)
        3. Freshness / age penalty
        4. Multi-beacon margin (bonus if top beacon clearly dominates)
        """
        if self._current_landmark_id is None:
            return 0.0

        now = time.time()
        age = now - self._last_scan_time if self._last_scan_time > 0 else 999.0
        if age > self.STALE_TIMEOUT_S:
            # Decays linearly to 0 if stale
            decay = max(0.0, 1.0 - ((age - self.STALE_TIMEOUT_S) / 5.0))
            return round(0.20 * decay, 2)

        # 1. RSSI factor (0.0 to 1.0)
        rssi_clamped = max(self.RSSI_POOR, min(self.RSSI_EXCELLENT, self._current_rssi))
        rssi_factor = (rssi_clamped - self.RSSI_POOR) / (self.RSSI_EXCELLENT - self.RSSI_POOR)

        # 2. Stability factor (0.0 to 1.0)
        # 1 scan = 0.4, 2 scans = 0.7, 3+ scans = 1.0
        stability_factor = min(1.0, 0.4 + (0.3 * (self._consecutive_matching_count - 1)))

        # 3. Margin bonus / penalty: if multiple beacons detected, check margin between top 2
        margin_factor = 1.0
        if self._recent_scans:
            latest = self._recent_scans[-1]
            if len(latest) >= 2:
                top_values = sorted(latest.values(), reverse=True)
                margin = top_values[0] - top_values[1]  # dBm difference
                if margin < 3.0:
                    # Very close beacons -> ambiguous zone boundary
                    margin_factor = 0.85
                elif margin > 10.0:
                    margin_factor = 1.05

        # Combined raw confidence
        raw_conf = (0.55 * rssi_factor + 0.45 * stability_factor) * margin_factor
        return round(max(0.0, min(1.0, raw_conf)), 2)

    def get_confidence_level(self, confidence: Optional[float] = None) -> str:
        """Returns 'HIGH', 'MEDIUM', or 'LOW'."""
        c = confidence if confidence is not None else self.calculate_confidence()
        if c >= self.CONF_HIGH_MIN:
            return "HIGH"
        elif c >= self.CONF_MEDIUM_MIN:
            return "MEDIUM"
        return "LOW"

    def get_current_estimate(self) -> Optional[Dict[str, Any]]:
        """
        Returns structured localization object matching spec Section 15:
        {
          "source": "BLE",
          "landmark_id": "B3",
          "zone": "Computer Lab",
          "floor": 0,
          "x": 10,
          "y": 0,
          "rssi": -62.0,
          "confidence": 0.82,
          "confidence_level": "HIGH",
          "consecutive_scans": 4,
          "timestamp": 1720000000
        }
        """
        if self._current_landmark_id is None:
            return None

        conf = self.calculate_confidence()
        conf_level = self.get_confidence_level(conf)

        lm_info = self.landmarks_by_id.get(self._current_landmark_id, {})
        name = lm_info.get("name", self._current_landmark_id)
        zone = lm_info.get("zone", name)
        floor = lm_info.get("floor", 0)
        x = lm_info.get("x", 0)
        y = lm_info.get("y", 0)

        return {
            "source": "BLE",
            "landmark_id": self._current_landmark_id,
            "name": name,
            "zone": zone,
            "floor": floor,
            "x": x,
            "y": y,
            "rssi": round(self._current_rssi, 1),
            "confidence": conf,
            "confidence_level": conf_level,
            "consecutive_scans": self._consecutive_matching_count,
            "timestamp": self._last_scan_time,
        }

    def reset(self) -> None:
        """Resets smoothed state."""
        self._current_landmark_id = None
        self._current_rssi = -100.0
        self._consecutive_matching_count = 0
        self._candidate_landmark_id = None
        self._candidate_consecutive_count = 0
        self._recent_scans.clear()
        self._last_scan_time = 0.0
