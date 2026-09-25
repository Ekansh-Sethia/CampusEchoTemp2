"""
VoiceEngine: Priority queue for Text-to-Speech instructions.
Urgent messages (BLOCKED, ESCALATE) jump the queue and interrupt ongoing speech.
Duplicate consecutive identical instructions are de-duped automatically.
The engine itself does not call pyttsx3 or any system TTS — it emits
'voice_speak' WebSocket events that the browser handles via Web Speech API.
"""
import threading
import queue
from typing import Optional, Callable
from pydantic import BaseModel


class VoiceInstruction(BaseModel):
    """A single queued speech instruction."""
    text: str
    priority: str = "normal"        # "low", "normal", "urgent"
    interrupt_previous: bool = False  # If True, clears the queue before inserting


# Priority levels for the queue (lower number = higher priority)
_PRIORITY_MAP = {
    "urgent": 0,
    "normal": 1,
    "low": 2,
}


class VoiceQueue:
    """
    Thread-safe priority queue for voice instructions.
    Urgent items jump ahead of normal/low items.
    Consecutive duplicate texts are not re-enqueued.
    """

    def __init__(self):
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._lock = threading.Lock()
        self._last_enqueued: Optional[str] = None   # tracks last enqueued text for dedup
        self._counter = 0
        self._on_speak: Optional[Callable[[VoiceInstruction], None]] = None

    def set_speak_callback(self, callback: Callable[[VoiceInstruction], None]):
        """Register a callback that is called with each dequeued instruction."""
        self._on_speak = callback

    def enqueue(self, instruction: VoiceInstruction) -> bool:
        """
        Adds an instruction to the priority queue.
        Returns False (and skips) if the same text was the last instruction enqueued (dedup).
        If instruction.interrupt_previous is True, clears the queue first.
        """
        with self._lock:
            # De-duplicate consecutive identical instructions (non-urgent only)
            if instruction.text == self._last_enqueued and instruction.priority != "urgent":
                return False

            if instruction.interrupt_previous:
                while not self._queue.empty():
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        break

            priority_val = _PRIORITY_MAP.get(instruction.priority, 1)
            self._counter += 1
            self._queue.put((priority_val, self._counter, instruction))
            self._last_enqueued = instruction.text
            return True

    def dequeue(self) -> Optional[VoiceInstruction]:
        """
        Returns the highest-priority queued instruction, or None if empty.
        """
        try:
            _, _, instruction = self._queue.get_nowait()
            return instruction
        except queue.Empty:
            return None

    def flush(self) -> None:
        """Clear all pending instructions (e.g., on walk end)."""
        with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._last_enqueued = None

    def pending_count(self) -> int:
        return self._queue.qsize()

    def reset_dedup(self) -> None:
        """Reset the last-enqueued tracker (e.g., when context changes)."""
        with self._lock:
            self._last_enqueued = None


class VoiceEngine:
    """
    High-level voice notification engine.
    Wraps VoiceQueue with convenience methods for the notification layer.
    All actual speech synthesis is handled browser-side via Web Speech API.
    The engine emits instructions that the API server broadcasts as WebSocket events.
    """

    def __init__(self):
        self.queue = VoiceQueue()

    def speak(self, text: str, priority: str = "normal", interrupt: bool = False) -> bool:
        """Enqueue a spoken instruction."""
        instruction = VoiceInstruction(
            text=text,
            priority=priority,
            interrupt_previous=interrupt,
        )
        return self.queue.enqueue(instruction)

    def speak_urgent(self, text: str) -> bool:
        """Enqueue an urgent message that clears the queue and speaks immediately."""
        return self.speak(text, priority="urgent", interrupt=True)

    def speak_low(self, text: str) -> bool:
        """Enqueue a low-priority informational message."""
        return self.speak(text, priority="low")

    def next_instruction(self) -> Optional[VoiceInstruction]:
        """Pop and return the highest-priority pending instruction."""
        return self.queue.dequeue()

    def flush(self) -> None:
        self.queue.flush()

    def pending(self) -> int:
        return self.queue.pending_count()
