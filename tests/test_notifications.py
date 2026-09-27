"""
Unit tests for Phase 6:
- HapticEncoder protocol (turn, alert, milestone commands)
- VoiceEngine priority queue and de-duplication
- ModeRouter output dispatch (VOICE_ONLY / HAPTIC_ONLY / DUAL)
"""
import pytest

from src.notifications.haptic_encoder import HapticEncoder, HapticCommand
from src.notifications.voice_engine import VoiceEngine, VoiceInstruction
from src.notifications.mode_router import ModeRouter, OutputMode
from src.decision.confidence_policy import ConfidenceTier, PolicyDecision
from src.routing.navigator import NavigationEvent, NavigationStep


# ─── HapticEncoder Tests ──────────────────────────────────────────────

class TestHapticEncoder:
    def test_encode_left_turn(self):
        assert HapticEncoder.encode_turn("left") == "L7P2"

    def test_encode_right_turn(self):
        assert HapticEncoder.encode_turn("right") == "R7P2"

    def test_encode_straight(self):
        assert HapticEncoder.encode_turn("straight") == "B3P1"

    def test_encode_straight_unknown_direction(self):
        # Unrecognised direction defaults to straight
        assert HapticEncoder.encode_turn("forward") == "B3P1"

    def test_encode_blocked_alert(self):
        assert HapticEncoder.encode_alert(ConfidenceTier.BLOCKED) == "B9P3"

    def test_encode_hedge_alert(self):
        assert HapticEncoder.encode_alert(ConfidenceTier.HEDGE) == "B5P2"

    def test_encode_escalate_alert(self):
        assert HapticEncoder.encode_alert(ConfidenceTier.ESCALATE) == "B9P5"

    def test_encode_arrival(self):
        assert HapticEncoder.encode_arrival() == "B7P4"

    def test_encode_start(self):
        assert HapticEncoder.encode_start() == "B4P1"

    def test_parse_valid_command(self):
        cmd = HapticCommand("L7P2")
        assert cmd.side == "L"
        assert cmd.intensity == 7
        assert cmd.pattern == "2"
        assert "left" in cmd.description
        assert "double-tap" in cmd.description

    def test_parse_invalid_command_raises(self):
        with pytest.raises(ValueError):
            HapticCommand("INVALID")

    def test_is_valid_true(self):
        assert HapticEncoder.is_valid("B9P5") is True

    def test_is_valid_false(self):
        assert HapticEncoder.is_valid("XYZ") is False


# ─── VoiceEngine Tests ────────────────────────────────────────────────

class TestVoiceEngine:
    def setup_method(self):
        self.engine = VoiceEngine()

    def test_enqueue_and_dequeue(self):
        self.engine.speak("Hello", priority="normal")
        instr = self.engine.next_instruction()
        assert instr is not None
        assert instr.text == "Hello"

    def test_urgent_jumps_queue(self):
        self.engine.speak("First normal message", priority="normal")
        self.engine.speak("Second normal message", priority="normal")
        self.engine.speak("URGENT — stop now!", priority="urgent")
        # Urgent should come out first
        first = self.engine.next_instruction()
        assert first.text == "URGENT — stop now!"

    def test_dedup_normal_consecutive(self):
        self.engine.speak("Caution ahead")
        result = self.engine.speak("Caution ahead")  # same text
        assert result is False  # de-duped, not enqueued
        assert self.engine.pending() == 1  # only one in queue

    def test_urgent_bypasses_dedup(self):
        self.engine.speak("Rerouting")
        result = self.engine.speak_urgent("Rerouting")
        assert result is True  # urgent always enqueued

    def test_flush_clears_queue(self):
        self.engine.speak("Message 1")
        self.engine.speak_low("Message 2")
        self.engine.flush()
        assert self.engine.pending() == 0

    def test_low_priority_after_normal(self):
        self.engine.speak("Normal message", priority="normal")
        self.engine.speak_low("Low priority note")
        first = self.engine.next_instruction()
        assert first.priority == "normal"


# ─── ModeRouter Tests ─────────────────────────────────────────────────

def make_decision(tier: ConfidenceTier, spoken: str = "Test instruction") -> PolicyDecision:
    return PolicyDecision(
        tier=tier,
        obstacle_label="pothole",
        effective_confidence=0.80,
        raw_confidence=0.80,
        shadow_likelihood=0.0,
        in_walking_lane=True,
        distance_m=2.0,
        spoken_instruction=spoken,
        reroute_triggered=(tier == ConfidenceTier.BLOCKED),
        escalation_triggered=(tier == ConfidenceTier.ESCALATE),
        decay_tau_s=120.0,
    )


class TestModeRouter:
    def setup_method(self):
        self.dispatched = []

    def router_with_callback(self, mode: OutputMode) -> ModeRouter:
        router = ModeRouter(mode=mode)
        router.register_callback(lambda r: self.dispatched.append(r))
        return router

    def test_dual_blocked_emits_both(self):
        router = self.router_with_callback(OutputMode.DUAL)
        result = router.handle_decision(make_decision(ConfidenceTier.BLOCKED))
        assert result.voice_text is not None
        assert result.haptic_cmd == "B9P3"

    def test_voice_only_blocked_emits_voice_no_haptic(self):
        router = self.router_with_callback(OutputMode.VOICE_ONLY)
        result = router.handle_decision(make_decision(ConfidenceTier.BLOCKED))
        assert result.voice_text is not None
        assert result.haptic_cmd is None

    def test_haptic_only_blocked_emits_haptic_no_voice(self):
        router = self.router_with_callback(OutputMode.HAPTIC_ONLY)
        result = router.handle_decision(make_decision(ConfidenceTier.BLOCKED))
        assert result.voice_text is None
        assert result.haptic_cmd == "B9P3"

    def test_escalation_flag_propagated(self):
        router = self.router_with_callback(OutputMode.DUAL)
        result = router.handle_decision(make_decision(ConfidenceTier.ESCALATE))
        assert result.escalation_triggered is True
        assert result.haptic_cmd == "B9P5"

    def test_mode_switch_takes_effect_immediately(self):
        router = self.router_with_callback(OutputMode.DUAL)
        router.set_mode(OutputMode.HAPTIC_ONLY)
        result = router.handle_decision(make_decision(ConfidenceTier.HEDGE))
        assert result.voice_text is None
        assert result.haptic_cmd == "B5P2"

    def test_session_log_records_events(self):
        router = self.router_with_callback(OutputMode.DUAL)
        router.handle_decision(make_decision(ConfidenceTier.BLOCKED))
        router.handle_decision(make_decision(ConfidenceTier.HEDGE))
        assert len(router.session_log) == 2

    def test_callback_fired_on_each_event(self):
        router = self.router_with_callback(OutputMode.DUAL)
        router.handle_decision(make_decision(ConfidenceTier.BLOCKED))
        router.handle_decision(make_decision(ConfidenceTier.HEDGE))
        assert len(self.dispatched) == 2

    def test_local_audio_toggle(self):
        router = ModeRouter(mode=OutputMode.DUAL)
        assert router.voice.enable_local_audio is False
        router.enable_local_audio(True, speech_rate=3)
        assert router.voice.enable_local_audio is True
        assert router.voice._speaker is not None
        router.enable_local_audio(False)
        assert router.voice.enable_local_audio is False
        assert router.voice._speaker is None
        router.close()

