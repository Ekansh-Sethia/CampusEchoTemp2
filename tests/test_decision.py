"""
Unit tests for Phase 4:
- 3-Tier Confidence Policy (BLOCKED / HEDGE / ESCALATE)
- Hazard Memory decay model
"""
import time
import math
import pytest

from src.perception.models import DetectedObstacle
from src.decision.confidence_policy import ConfidencePolicy, ConfidenceTier
from src.decision.hazard_memory import HazardMemory


def make_obstacle(
    label="pothole",
    confidence=0.80,
    raw_confidence=0.80,
    shadow_likelihood=0.0,
    in_lane=True,
    distance_m=2.5,
    position="center",
) -> DetectedObstacle:
    return DetectedObstacle(
        label=label,
        confidence=confidence,
        raw_confidence=raw_confidence,
        shadow_likelihood=shadow_likelihood,
        bbox=(200, 300, 440, 400),
        bbox_normalized=(0.3, 0.6, 0.7, 0.8),
        distance_m=distance_m,
        in_walking_lane=in_lane,
        horizontal_position=position,
        urgency="high",
        is_environmental_hazard=True,
    )


# ─── Policy Tests ─────────────────────────────────────────────────────────────

class TestConfidencePolicy:
    def setup_method(self):
        self.policy = ConfidencePolicy()

    def test_tier1_blocked_high_confidence_in_lane(self):
        obs = make_obstacle(confidence=0.85, in_lane=True)
        decision = self.policy.evaluate(obs)
        assert decision.tier == ConfidenceTier.BLOCKED
        assert decision.reroute_triggered is True
        assert decision.escalation_triggered is False
        assert "Rerouting" in decision.spoken_instruction

    def test_tier2_hedge_mid_confidence_in_lane(self):
        obs = make_obstacle(confidence=0.55, in_lane=True)
        decision = self.policy.evaluate(obs)
        assert decision.tier == ConfidenceTier.HEDGE
        assert decision.reroute_triggered is False
        assert decision.escalation_triggered is False
        assert "Caution" in decision.spoken_instruction

    def test_tier3_escalate_low_confidence_in_lane(self):
        obs = make_obstacle(confidence=0.25, in_lane=True)
        decision = self.policy.evaluate(obs)
        assert decision.tier == ConfidenceTier.ESCALATE
        assert decision.escalation_triggered is True
        assert decision.reroute_triggered is False
        assert "assistance" in decision.spoken_instruction.lower()

    def test_off_lane_high_confidence_capped_at_hedge(self):
        # Even a high-confidence detection off-lane should NOT trigger BLOCKED
        obs = make_obstacle(confidence=0.90, in_lane=False, position="right")
        decision = self.policy.evaluate(obs)
        assert decision.tier == ConfidenceTier.HEDGE
        assert decision.reroute_triggered is False

    def test_shadow_penalized_detection_stays_hedge(self):
        # Shadow-recalibrated confidence (already lowered by detector)
        # raw was 0.80 but shadow_likelihood=0.65 → effective ~0.52
        obs = make_obstacle(
            confidence=0.52,   # already recalibrated by ShadowLightAnalyzer
            raw_confidence=0.80,
            shadow_likelihood=0.65,
            in_lane=True,
        )
        decision = self.policy.evaluate(obs)
        assert decision.tier == ConfidenceTier.HEDGE  # Not BLOCKED — shadow kept it below 0.70
        assert decision.reroute_triggered is False

    def test_boundary_exactly_at_tier1_threshold(self):
        obs = make_obstacle(confidence=0.70, in_lane=True)
        decision = self.policy.evaluate(obs)
        assert decision.tier == ConfidenceTier.BLOCKED

    def test_boundary_exactly_at_tier2_threshold(self):
        obs = make_obstacle(confidence=0.40, in_lane=True)
        decision = self.policy.evaluate(obs)
        assert decision.tier == ConfidenceTier.HEDGE

    def test_decay_tau_assigned_correctly(self):
        obs_pothole = make_obstacle(label="pothole", confidence=0.80, in_lane=True)
        obs_tree = make_obstacle(label="tree", confidence=0.80, in_lane=True)
        d_pothole = self.policy.evaluate(obs_pothole)
        d_tree = self.policy.evaluate(obs_tree)
        assert d_pothole.decay_tau_s == 120.0
        assert d_tree.decay_tau_s == 300.0


# ─── Hazard Memory Tests ───────────────────────────────────────────────────────

class TestHazardMemory:
    def setup_method(self):
        self.memory = HazardMemory()

    def test_add_record_and_retrieve(self):
        rec = self.memory.add_or_refresh(
            edge_id="edge_turn_to_atc",
            label="pothole",
            confidence=0.85,
            decay_tau_s=120.0,
            penalty_weight=300.0,
        )
        assert len(self.memory) == 1
        active = self.memory.get_active_hazards()
        assert len(active) == 1
        assert active[0].label == "pothole"
        assert active[0].active_weight == 300.0

    def test_refresh_resets_decay_timer(self):
        rec = self.memory.add_or_refresh(
            edge_id="edge_turn_to_atc", label="pothole",
            confidence=0.85, decay_tau_s=120.0, penalty_weight=300.0,
        )
        # Manually simulate partial decay
        rec.active_weight = 150.0

        # Refresh restores weight
        rec2 = self.memory.add_or_refresh(
            edge_id="edge_turn_to_atc", label="pothole",
            confidence=0.90, decay_tau_s=120.0, penalty_weight=300.0,
        )
        assert rec2.active_weight == 300.0  # Restored to initial
        assert len(self.memory) == 1  # Same record, not a new one

    def test_decay_reduces_active_weight(self):
        rec = self.memory.add_or_refresh(
            edge_id="edge_1", label="car",
            confidence=0.80, decay_tau_s=45.0, penalty_weight=300.0,
        )
        # Simulate 45 seconds passing (one τ → weight should be ~37% = ~110)
        future_time = rec.last_confirmed + 45.0
        self.memory.decay_all(now=future_time)
        updated = self.memory.get_active_hazards()
        assert len(updated) == 1
        expected = round(300.0 * math.exp(-1.0), 3)  # e^-1 ≈ 0.368
        assert abs(updated[0].active_weight - expected) < 1.0

    def test_decay_removes_stale_obstacle(self):
        rec = self.memory.add_or_refresh(
            edge_id="edge_2", label="stone",
            confidence=0.80, decay_tau_s=90.0, penalty_weight=300.0,
        )
        # Jump far into the future (10× tau → weight ≈ 0.000045% → stale)
        far_future = rec.last_confirmed + 90.0 * 10
        pruned = self.memory.decay_all(now=far_future)
        assert len(self.memory) == 0
        assert rec.obstacle_id in pruned

    def test_manual_remove(self):
        rec = self.memory.add_or_refresh(
            edge_id="edge_3", label="tree",
            confidence=0.75, decay_tau_s=300.0, penalty_weight=300.0,
        )
        removed = self.memory.remove(rec.obstacle_id)
        assert removed is True
        assert len(self.memory) == 0

    def test_multiple_hazards_different_edges(self):
        self.memory.add_or_refresh("edge_a", "pothole", 0.85, decay_tau_s=120.0, penalty_weight=300.0)
        self.memory.add_or_refresh("edge_b", "car", 0.90, decay_tau_s=45.0, penalty_weight=300.0)
        self.memory.add_or_refresh("edge_c", "tree", 0.70, decay_tau_s=300.0, penalty_weight=200.0)
        assert len(self.memory) == 3
