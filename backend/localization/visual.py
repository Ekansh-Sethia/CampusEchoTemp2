"""
Visual Localization Provider.
Monitors visual odometry / camera landmark tracking status.
"""
import time
from typing import Dict, Any, Optional


class VisualLocalizationSystem:
    """
    Simulates / wraps visual odometry or camera landmark matching.
    Provides reliability and confidence metrics based on feature tracking quality.
    """

    def __init__(
        self,
        initial_reliable: bool = True,
        initial_confidence: float = 0.85,
        tracked_features: int = 42,
    ):
        self._reliable = initial_reliable
        self._confidence = initial_confidence
        self._tracked_features = tracked_features
        self._last_update = time.time()

    @property
    def is_reliable(self) -> bool:
        return self._reliable and self._confidence >= 0.60

    @property
    def confidence(self) -> float:
        return self._confidence

    def set_status(
        self,
        reliable: bool,
        confidence: Optional[float] = None,
        tracked_features: Optional[int] = None,
    ) -> None:
        self._reliable = reliable
        if confidence is not None:
            self._confidence = max(0.0, min(1.0, confidence))
        else:
            self._confidence = 0.85 if reliable else 0.25
        if tracked_features is not None:
            self._tracked_features = tracked_features
        self._last_update = time.time()

    def get_status(self) -> Dict[str, Any]:
        return {
            "source": "VISUAL",
            "reliable": self.is_reliable,
            "confidence": round(self._confidence, 2),
            "tracked_features": self._tracked_features,
            "timestamp": self._last_update,
        }
