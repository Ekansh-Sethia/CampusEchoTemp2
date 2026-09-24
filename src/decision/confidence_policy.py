"""
3-Tier Confidence Policy Decision Engine for CampusEcho.
Maps (confidence, in_walking_lane, shadow_likelihood) to safety action tiers.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

from src.perception.models import DetectedObstacle


class ConfidenceTier(str, Enum):
    BLOCKED = "BLOCKED"       # Confidence >= 0.70: hard obstacle, reroute + memory
    HEDGE = "HEDGE"           # Confidence 0.40–0.70: caution warning, hold route
    ESCALATE = "ESCALATE"     # Confidence < 0.40 inside walking lane: request human help


# Decay time constants (seconds) per obstacle class
DECAY_TAU_BY_CLASS: dict = {
    "pothole": 120.0,
    "stair": 180.0,
    "stairs": 180.0,
    "stone": 90.0,
    "tree": 300.0,
    "pillar": 600.0,
    "car": 45.0,
    "motorcycle": 45.0,
    "bicycle": 45.0,
    "person": 30.0,
    "bus": 60.0,
    "truck": 60.0,
    "two_wheeler": 45.0,
    "four_wheeler": 60.0,
    "default": 90.0,
}


class PolicyDecision(BaseModel):
    """Result of the 3-tier confidence policy evaluation for a single detection."""
    tier: ConfidenceTier
    obstacle_label: str
    effective_confidence: float = Field(ge=0.0, le=1.0)
    raw_confidence: float = Field(ge=0.0, le=1.0)
    shadow_likelihood: float = Field(ge=0.0, le=1.0)
    in_walking_lane: bool
    distance_m: float
    spoken_instruction: str
    reroute_triggered: bool = False
    escalation_triggered: bool = False
    decay_tau_s: float = 90.0


class ConfidencePolicy:
    """
    Evaluates detected obstacles against the 3-tier confidence decision policy.

    Shadow-penalized detections require higher raw confidence to reach Tier 1,
    because ShadowLightAnalyzer has already downscaled confidence proportionally.
    The shadow_likelihood field on the obstacle determines an additional safety margin.
    """

    TIER1_THRESHOLD = 0.70   # BLOCKED
    TIER2_THRESHOLD = 0.40   # HEDGE

    def evaluate(self, obstacle: DetectedObstacle) -> PolicyDecision:
        """
        Evaluates a single DetectedObstacle and returns a PolicyDecision.
        Only obstacles in the walking lane can trigger ESCALATE or BLOCKED.
        Off-lane obstacles are downgraded to HEDGE or ignored.
        """
        raw_conf = obstacle.raw_confidence if obstacle.raw_confidence > 0.0 else obstacle.confidence
        effective_conf = obstacle.confidence  # Already shadow-recalibrated by detector
        shadow = obstacle.shadow_likelihood
        in_lane = obstacle.in_walking_lane
        dist = obstacle.distance_m

        # Determine decay tau for this class
        tau = DECAY_TAU_BY_CLASS.get(obstacle.label.lower(), DECAY_TAU_BY_CLASS["default"])

        # Off-lane: cap tier at HEDGE regardless of confidence
        if not in_lane:
            if effective_conf >= self.TIER1_THRESHOLD:
                tier = ConfidenceTier.HEDGE
                instruction = (
                    f"Caution: {obstacle.label} detected {dist:.1f}m "
                    f"to your {obstacle.horizontal_position}. Proceed carefully."
                )
            else:
                # Below hedge threshold off-lane: low-priority note
                tier = ConfidenceTier.HEDGE
                instruction = (
                    f"Note: Possible {obstacle.label} {dist:.1f}m "
                    f"to your {obstacle.horizontal_position}."
                )
            return PolicyDecision(
                tier=tier,
                obstacle_label=obstacle.label,
                effective_confidence=round(effective_conf, 3),
                raw_confidence=round(raw_conf, 3),
                shadow_likelihood=round(shadow, 3),
                in_walking_lane=in_lane,
                distance_m=dist,
                spoken_instruction=instruction,
                reroute_triggered=False,
                escalation_triggered=False,
                decay_tau_s=tau,
            )

        # In-lane evaluation
        if effective_conf >= self.TIER1_THRESHOLD:
            tier = ConfidenceTier.BLOCKED
            instruction = (
                f"Warning! {obstacle.label} blocking path {dist:.1f} meters ahead. "
                f"Rerouting now."
            )
            return PolicyDecision(
                tier=tier,
                obstacle_label=obstacle.label,
                effective_confidence=round(effective_conf, 3),
                raw_confidence=round(raw_conf, 3),
                shadow_likelihood=round(shadow, 3),
                in_walking_lane=in_lane,
                distance_m=dist,
                spoken_instruction=instruction,
                reroute_triggered=True,
                escalation_triggered=False,
                decay_tau_s=tau,
            )

        elif effective_conf >= self.TIER2_THRESHOLD:
            tier = ConfidenceTier.HEDGE
            instruction = (
                f"Caution: possible {obstacle.label} {dist:.1f} meters ahead. "
                f"Slow down and proceed carefully."
            )
            return PolicyDecision(
                tier=tier,
                obstacle_label=obstacle.label,
                effective_confidence=round(effective_conf, 3),
                raw_confidence=round(raw_conf, 3),
                shadow_likelihood=round(shadow, 3),
                in_walking_lane=in_lane,
                distance_m=dist,
                spoken_instruction=instruction,
                reroute_triggered=False,
                escalation_triggered=False,
                decay_tau_s=tau,
            )

        else:
            # Tier 3: Low confidence in lane — uncertain, request human assistance
            tier = ConfidenceTier.ESCALATE
            instruction = (
                f"Uncertain obstacle detected {dist:.1f} meters ahead. "
                f"Requesting assistance — please stop and wait."
            )
            return PolicyDecision(
                tier=tier,
                obstacle_label=obstacle.label,
                effective_confidence=round(effective_conf, 3),
                raw_confidence=round(raw_conf, 3),
                shadow_likelihood=round(shadow, 3),
                in_walking_lane=in_lane,
                distance_m=dist,
                spoken_instruction=instruction,
                reroute_triggered=False,
                escalation_triggered=True,
                decay_tau_s=tau,
            )
