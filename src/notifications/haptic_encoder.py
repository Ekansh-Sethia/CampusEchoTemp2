"""
HapticEncoder: Encodes navigation and obstacle events into the CampusEcho
haptic command protocol.

Protocol format:  {side}{intensity}P{pattern}
  side      : L (left motor), R (right motor), B (both)
  intensity : 1-9  (vibration strength; 9 = strongest)
  pattern   : 1-5  (1=single, 2=double-tap, 3=rapid-burst, 4=long-hold, 5=SOS)

Examples:
  L7P2  = Left motor, strength 7, double-tap  (turn left)
  R7P2  = Right motor, strength 7, double-tap (turn right)
  B3P1  = Both motors, strength 3, single     (walk straight confirmation)
  B9P3  = Both motors, strength 9, rapid      (BLOCKED alert)
  B5P2  = Both motors, strength 5, double-tap (HEDGE caution)
  B9P5  = Both motors, strength 9, SOS        (ESCALATE — stop and wait)
  B7P4  = Both motors, strength 7, long-hold  (destination arrived)
"""
import re
from typing import Optional
from src.decision.confidence_policy import ConfidenceTier


# Pattern descriptions for simulator UI rendering
PATTERN_DESCRIPTIONS = {
    "1": "single pulse",
    "2": "double-tap",
    "3": "rapid burst",
    "4": "long hold",
    "5": "SOS pattern",
}

SIDE_DESCRIPTIONS = {
    "L": "left motor",
    "R": "right motor",
    "B": "both motors",
}


class HapticCommand:
    """A single parsed haptic command with human-readable description."""

    def __init__(self, raw: str):
        self.raw = raw.upper()
        self._parse()

    def _parse(self):
        match = re.fullmatch(r"([LRB])(\d)P(\d)", self.raw)
        if not match:
            raise ValueError(f"Invalid haptic command format: '{self.raw}'. Expected e.g. 'L7P2'")
        self.side = match.group(1)
        self.intensity = int(match.group(2))
        self.pattern = match.group(3)

    @property
    def description(self) -> str:
        side_str = SIDE_DESCRIPTIONS.get(self.side, self.side)
        pat_str = PATTERN_DESCRIPTIONS.get(self.pattern, f"pattern {self.pattern}")
        return f"{side_str}, intensity {self.intensity}/9, {pat_str}"

    def __str__(self) -> str:
        return self.raw

    def __repr__(self) -> str:
        return f"HapticCommand({self.raw!r})"


class HapticEncoder:
    """
    Encodes navigation and decision events into haptic protocol command strings.
    All command strings can be forwarded via WebSocket to:
      1. The Web Haptic Simulator (dashboard visual/audio animation)
      2. An optional ESP32 Bluetooth Classic SPP serial bridge
    """

    # ── Turn commands ─────────────────────────────────────────────────────────
    @staticmethod
    def encode_turn(direction: str) -> str:
        """
        Returns a haptic command for a navigation turn instruction.
        direction: "left", "right", "straight"
        """
        d = direction.strip().lower()
        if d == "left":
            return "L7P2"   # Left double-tap
        elif d == "right":
            return "R7P2"   # Right double-tap
        else:
            return "B3P1"   # Both, gentle single pulse (walk straight)

    # ── Alert commands ────────────────────────────────────────────────────────
    @staticmethod
    def encode_alert(tier: ConfidenceTier) -> str:
        """
        Returns a haptic alert command based on the confidence decision tier.
        BLOCKED   → strong rapid burst (urgent stop/reroute)
        HEDGE     → medium double-tap (caution)
        ESCALATE  → max-strength SOS (stop, help requested)
        """
        if tier == ConfidenceTier.BLOCKED:
            return "B9P3"   # Both, max-minus-one, rapid burst
        elif tier == ConfidenceTier.HEDGE:
            return "B5P2"   # Both, medium, double-tap
        elif tier == ConfidenceTier.ESCALATE:
            return "B9P5"   # Both, max, SOS pattern
        return "B3P1"       # Fallback: gentle pulse

    # ── Milestone commands ────────────────────────────────────────────────────
    @staticmethod
    def encode_arrival() -> str:
        """Destination or waypoint reached: long hold on both motors."""
        return "B7P4"

    @staticmethod
    def encode_start() -> str:
        """Walk started confirmation: single gentle pulse on both."""
        return "B4P1"

    @staticmethod
    def encode_approaching_waypoint() -> str:
        """User is approaching the next waypoint: light double-tap."""
        return "B3P2"

    # ── Parse ─────────────────────────────────────────────────────────────────
    @staticmethod
    def parse(cmd: str) -> HapticCommand:
        """Parses a raw command string into a HapticCommand with description."""
        return HapticCommand(cmd)

    @staticmethod
    def is_valid(cmd: str) -> bool:
        """Returns True if the string is a valid haptic command."""
        try:
            HapticCommand(cmd)
            return True
        except ValueError:
            return False
