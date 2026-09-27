"""
GPS Localization Provider for Indoor/Outdoor Transition.
Simulates/interfaces with GPS receiver to detect signal degradation when moving indoors.
"""
import time
from typing import Dict, Any, Optional


class GPSSystem:
    """
    Monitors GPS signal quality, accuracy, and reliability.
    When a user moves indoors, satellite signal attenuation reduces confidence,
    triggering transition to indoor BLE/QR recovery.
    """

    def __init__(
        self,
        initial_reliable: bool = True,
        initial_confidence: float = 0.90,
        lat: float = 22.7244,
        lon: float = 75.8712,
    ):
        self._reliable = initial_reliable
        self._confidence = initial_confidence
        self._lat = lat
        self._lon = lon
        self._last_update = time.time()

    @property
    def is_reliable(self) -> bool:
        """True if GPS has a solid outdoor fix with confidence >= 0.60."""
        return self._reliable and self._confidence >= 0.60

    @property
    def confidence(self) -> float:
        return self._confidence

    def set_status(
        self,
        reliable: bool,
        confidence: Optional[float] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> None:
        """Explicitly update GPS state (useful for simulations and sensor updates)."""
        self._reliable = reliable
        if confidence is not None:
            self._confidence = max(0.0, min(1.0, confidence))
        else:
            self._confidence = 0.90 if reliable else 0.20
        if lat is not None:
            self._lat = lat
        if lon is not None:
            self._lon = lon
        self._last_update = time.time()

    def set_indoor(self, is_indoor: bool = True) -> None:
        """Convenience method to simulate entering or leaving an indoor space."""
        if is_indoor:
            self.set_status(reliable=False, confidence=0.15)
        else:
            self.set_status(reliable=True, confidence=0.92)

    def get_status(self) -> Dict[str, Any]:
        return {
            "source": "GPS",
            "reliable": self.is_reliable,
            "confidence": round(self._confidence, 2),
            "lat": self._lat,
            "lon": self._lon,
            "timestamp": self._last_update,
        }
