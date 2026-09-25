"""
ModeRouter: Central output dispatcher for CampusEcho notifications.
Routes PolicyDecision and NavigationEvent objects to the correct output
channels (VoiceEngine and/or HapticEncoder) depending on the active OutputMode.
Mode can be toggled at runtime — changes take effect immediately.
"""
from enum import Enum
from typing import Optional, List, Callable
from dataclasses import dataclass, field

from src.decision.confidence_policy import PolicyDecision, ConfidenceTier
from src.routing.navigator import NavigationEvent
from .voice_engine import VoiceEngine
from .haptic_encoder import HapticEncoder


class OutputMode(str, Enum):
    VOICE_ONLY  = "VOICE_ONLY"
    HAPTIC_ONLY = "HAPTIC_ONLY"
    DUAL        = "DUAL"


@dataclass
class DispatchResult:
    """Records what outputs were emitted for a single event."""
    voice_text: Optional[str] = None
    haptic_cmd: Optional[str] = None
    mode: OutputMode = OutputMode.DUAL
    escalation_triggered: bool = False
    event_type: str = ""


class ModeRouter:
    """
    Centralises all user-facing output routing for CampusEcho.

    On each perception frame cycle:
      - Call handle_decision(decision, edge_id) for obstacle policy results.
      - Call handle_nav_event(event) for navigation waypoint events.

    Registered callbacks are invoked with each DispatchResult so the
    API server can forward voice_speak and haptic_cmd WebSocket events
    to the dashboard and any connected ESP32 bridge.
    """

    def __init__(self, mode: OutputMode = OutputMode.DUAL):
        self.mode = mode
        self.voice = VoiceEngine()
        self.haptic = HapticEncoder()
        self._callbacks: List[Callable[[DispatchResult], None]] = []

        # Walk-session log for post-walk report
        self.session_log: List[DispatchResult] = []

    def set_mode(self, mode: OutputMode) -> None:
        """Switch output mode at runtime (thread-safe — single assignment)."""
        self.mode = mode

    def register_callback(self, callback: Callable[[DispatchResult], None]) -> None:
        """Register a callback that fires on every dispatched output event."""
        self._callbacks.append(callback)

    def handle_decision(self, decision: PolicyDecision) -> DispatchResult:
        """
        Dispatches voice and/or haptic outputs for a PolicyDecision.
        BLOCKED and ESCALATE always go through regardless of dedup — they are urgent.
        HEDGE uses normal priority and is de-duped if repeated consecutively.
        """
        voice_text: Optional[str] = None
        haptic_cmd: Optional[str] = None

        if decision.tier == ConfidenceTier.BLOCKED:
            haptic_cmd = self.haptic.encode_alert(ConfidenceTier.BLOCKED)
            if self.mode in (OutputMode.VOICE_ONLY, OutputMode.DUAL):
                self.voice.speak_urgent(decision.spoken_instruction)
                voice_text = decision.spoken_instruction
            if self.mode in (OutputMode.HAPTIC_ONLY, OutputMode.DUAL):
                haptic_cmd = haptic_cmd  # already set

        elif decision.tier == ConfidenceTier.HEDGE:
            haptic_cmd = self.haptic.encode_alert(ConfidenceTier.HEDGE)
            if self.mode in (OutputMode.VOICE_ONLY, OutputMode.DUAL):
                queued = self.voice.speak(decision.spoken_instruction, priority="normal")
                voice_text = decision.spoken_instruction if queued else None
            if self.mode == OutputMode.VOICE_ONLY:
                haptic_cmd = None  # suppress haptic

        elif decision.tier == ConfidenceTier.ESCALATE:
            haptic_cmd = self.haptic.encode_alert(ConfidenceTier.ESCALATE)
            if self.mode in (OutputMode.VOICE_ONLY, OutputMode.DUAL):
                self.voice.speak_urgent(decision.spoken_instruction)
                voice_text = decision.spoken_instruction
            if self.mode == OutputMode.VOICE_ONLY:
                haptic_cmd = None

        result = DispatchResult(
            voice_text=voice_text,
            haptic_cmd=haptic_cmd if self.mode != OutputMode.VOICE_ONLY else None,
            mode=self.mode,
            escalation_triggered=decision.escalation_triggered,
            event_type=f"decision_{decision.tier.value.lower()}",
        )
        self._fire(result)
        return result

    def handle_nav_event(self, event: NavigationEvent) -> DispatchResult:
        """
        Dispatches voice and/or haptic outputs for a NavigationEvent.
        Generates a turn-direction haptic command from the current_step's direction.
        """
        voice_text: Optional[str] = None
        haptic_cmd: Optional[str] = None

        # Determine haptic turn direction
        step_dir = "straight"
        if event.current_step:
            step_dir = event.current_step.direction  # "straight" | "left" | "right"
        haptic_cmd = self.haptic.encode_turn(step_dir)

        # Arrival gets a special haptic
        if event.event_type == "DESTINATION_REACHED":
            haptic_cmd = self.haptic.encode_arrival()

        # Route output based on mode
        if self.mode in (OutputMode.VOICE_ONLY, OutputMode.DUAL):
            self.voice.speak(event.voice_instruction, priority="normal")
            voice_text = event.voice_instruction

        if self.mode == OutputMode.VOICE_ONLY:
            haptic_cmd = None

        result = DispatchResult(
            voice_text=voice_text,
            haptic_cmd=haptic_cmd,
            mode=self.mode,
            escalation_triggered=False,
            event_type=f"nav_{event.event_type.lower()}",
        )
        self._fire(result)
        return result

    def handle_walk_start(self, route_summary: str) -> DispatchResult:
        """Emit walk-start confirmation."""
        haptic_cmd = self.haptic.encode_start()
        voice_text = None
        if self.mode in (OutputMode.VOICE_ONLY, OutputMode.DUAL):
            self.voice.speak(route_summary, priority="normal")
            voice_text = route_summary
        if self.mode == OutputMode.VOICE_ONLY:
            haptic_cmd = None

        result = DispatchResult(
            voice_text=voice_text,
            haptic_cmd=haptic_cmd,
            mode=self.mode,
            event_type="walk_start",
        )
        self._fire(result)
        return result

    def flush_voice(self) -> None:
        """Clear all pending voice instructions (e.g., on walk end)."""
        self.voice.flush()

    def clear_session_log(self) -> None:
        """Reset session log for a new walk."""
        self.session_log.clear()

    def _fire(self, result: DispatchResult) -> None:
        """Persist to session log and invoke all registered callbacks."""
        self.session_log.append(result)
        for cb in self._callbacks:
            cb(result)
