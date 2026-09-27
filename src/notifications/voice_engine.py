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


class NativeVoiceSpeaker:
    """
    Native desktop Text-to-Speech audio synthesizer for Windows.
    Uses System.Speech.Synthesis.SpeechSynthesizer via a persistent background process.
    Supports asynchronous non-blocking speech, rate/volume control, and immediate cancellation
    for urgent navigation alerts (BLOCKED / ESCALATE).
    """

    def __init__(self, rate: int = 2):
        self._ps = None
        self._lock = threading.Lock()
        self._rate = max(-10, min(10, rate))
        self._active = False
        self._init_process()

    def _init_process(self):
        try:
            import platform
            if platform.system() != "Windows":
                return

            ps_cmd = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Rate = {self._rate}; "
                f"while ($line = [Console]::In.ReadLine()) {{ "
                f"  if ($line -eq '__CANCEL__') {{ $s.SpeakAsyncCancelAll() | Out-Null }} "
                f"  else {{ $s.SpeakAsync($line) | Out-Null }} "
                f"}}"
            )
            import subprocess
            self._ps = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1
            )
            self._active = True
        except Exception:
            self._ps = None
            self._active = False

    def speak(self, text: str, interrupt: bool = False) -> None:
        """Speak a phrase asynchronously without blocking the perception/video loop."""
        if not self._ps or self._ps.poll() is not None:
            return
        with self._lock:
            try:
                if interrupt:
                    self._ps.stdin.write("__CANCEL__\n")
                clean = text.replace("\n", " ").replace("\r", " ").replace('"', "'").strip()
                if clean:
                    self._ps.stdin.write(f"{clean}\n")
                    self._ps.stdin.flush()
            except Exception:
                pass

    def cancel(self) -> None:
        """Immediately cancel any speech currently playing."""
        if not self._ps or self._ps.poll() is not None:
            return
        with self._lock:
            try:
                self._ps.stdin.write("__CANCEL__\n")
                self._ps.stdin.flush()
            except Exception:
                pass

    def close(self) -> None:
        """Cleanly terminate the background synthesizer."""
        with self._lock:
            if self._ps and self._ps.poll() is None:
                try:
                    self._ps.stdin.write("__CANCEL__\n")
                    self._ps.stdin.close()
                    self._ps.terminate()
                except Exception:
                    pass
                self._ps = None
            self._active = False


class VoiceEngine:
    """
    High-level voice notification engine.
    Wraps VoiceQueue with priority gating, deduplication, and multi-channel dispatch.
    Emits instructions that the API server broadcasts as WebSocket events for Web Speech API,
    and optionally synthesizes spoken audio directly via NativeVoiceSpeaker during video/CLI testing.
    """

    def __init__(self, enable_local_audio: bool = False, speech_rate: int = 2):
        self.queue = VoiceQueue()
        self.enable_local_audio = enable_local_audio
        self._speech_rate = speech_rate
        self._speaker: Optional[NativeVoiceSpeaker] = (
            NativeVoiceSpeaker(rate=speech_rate) if enable_local_audio else None
        )

    def enable_audio(self, enabled: bool = True, speech_rate: Optional[int] = None) -> None:
        """Enable or disable local desktop audio output at runtime."""
        self.enable_local_audio = enabled
        if speech_rate is not None:
            self._speech_rate = speech_rate

        if enabled:
            if self._speaker is None:
                self._speaker = NativeVoiceSpeaker(rate=self._speech_rate)
        else:
            if self._speaker is not None:
                self._speaker.close()
                self._speaker = None

    def speak(self, text: str, priority: str = "normal", interrupt: bool = False) -> bool:
        """Enqueue a spoken instruction and optionally synthesize audio locally."""
        instruction = VoiceInstruction(
            text=text,
            priority=priority,
            interrupt_previous=interrupt,
        )
        enqueued = self.queue.enqueue(instruction)
        if enqueued and self.enable_local_audio and self._speaker:
            self._speaker.speak(text, interrupt=interrupt)
        return enqueued

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
        if self._speaker:
            self._speaker.cancel()

    def close(self) -> None:
        """Clean up local audio resources on shutdown."""
        if self._speaker:
            self._speaker.close()
            self._speaker = None

    def pending(self) -> int:
        return self.queue.pending_count()

