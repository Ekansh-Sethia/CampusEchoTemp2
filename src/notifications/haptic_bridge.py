"""
HapticBridge: Hardware serial communication bridge for the CampusEcho ESP32
Haptic Wristband (campusecho_haptic_wristband.ino).

Bridges internal CampusEcho haptic protocol (e.g. 'L7P2', 'B9P3') to the ESP32
firmware's Bluetooth Classic SPP newline-terminated CSV format:
    <side>,<intensity 0-9>,<pattern 0-3>\\n

Protocol Translation:
  - side: 'L', 'R', 'B', 'O'
  - intensity: 0..9 mapped directly
  - pattern:
      P1 (single pulse)   -> 1 (slow pulse: 500ms on / 500ms off)
      P2 (double-tap)     -> 3 (double-pulse + pause: 120ms on/100ms off/120ms on/600ms off)
      P3 (rapid burst)    -> 2 (rapid pulse: 150ms on / 100ms off)
      P4 (long hold)      -> 0 (continuous steady vibration)
      P5 (SOS / critical) -> 3 (double-pulse critical)

Features:
  - Non-blocking: background worker thread with command queue.
  - Thread-safe: safe to call from any thread or async event loop.
  - Graceful fallback: drops commands safely if hardware is disconnected without crashing.
  - Auto-discovery: scans Windows COM ports for Bluetooth SPP devices.
  - ModeRouter integration: hooks directly into DispatchResult callbacks.
"""
import logging
import queue
import re
import threading
import time
from typing import Dict, List, Optional

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    serial = None

from src.notifications.mode_router import DispatchResult, OutputMode

logger = logging.getLogger("CampusEcho.HapticBridge")


# Translation table from Python HapticEncoder pattern ('1'..'5') to ESP32 firmware pattern (0..3)
PATTERN_TRANSLATION_MAP: Dict[str, int] = {
    "1": 1,  # P1: slow pulse (informational / straight confirmation)
    "2": 3,  # P2: double-pulse (turn instruction / caution)
    "3": 2,  # P3: rapid pulse (hazard BLOCKED alert)
    "4": 0,  # P4: continuous (destination arrived)
    "5": 3,  # P5: double-pulse critical (ESCALATE)
}


class HapticBridge:
    """
    Manages connection and non-blocking command transmission to the ESP32
    Haptic Wristband over a Bluetooth Classic SPP virtual COM port.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        auto_connect: bool = False,
    ):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn: Optional[serial.Serial] = None
        self._connected = False
        self._lock = threading.Lock()

        # Telemetry & metrics
        self.tx_count = 0
        self.error_count = 0
        self.last_cmd: Optional[str] = None
        self.last_sent_at: Optional[float] = None

        # Non-blocking worker queue
        self._queue: queue.Queue = queue.Queue(maxsize=100)
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="HapticBridgeWorker")
        self._worker_thread.start()

        if auto_connect:
            target_port = self.port or self.find_wristband_port()
            if target_port:
                self.connect(target_port, baudrate)

    @property
    def is_connected(self) -> bool:
        """Returns True if the serial connection is open and active."""
        with self._lock:
            return bool(self._connected and self.serial_conn and self.serial_conn.is_open)

    # ── Protocol Translation ──────────────────────────────────────────────────
    @staticmethod
    def translate_to_firmware(cmd: str) -> str:
        """
        Translates a CampusEcho haptic command string to the ESP32 firmware CSV string.

        Supports:
          - Internal format: 'L7P2' -> 'L,7,3\\n'
          - Raw CSV passthrough: 'L,7,2' -> 'L,7,2\\n'
          - Off commands: 'O0P0' or 'O,0,0' or 'OFF' -> 'O,0,0\\n'
        """
        raw = cmd.strip()
        if not raw:
            return "O,0,0\n"

        # Check for direct CSV format: side,intensity,pattern
        csv_match = re.fullmatch(r"([LRBOlrbo]),(\d+),(\d+)", raw)
        if csv_match:
            side = csv_match.group(1).upper()
            intensity = min(9, max(0, int(csv_match.group(2))))
            pattern = min(3, max(0, int(csv_match.group(3))))
            return f"{side},{intensity},{pattern}\n"

        # Check for all-off aliases
        if raw.upper() in ("O", "OFF", "O0P0", "STOP"):
            return "O,0,0\n"

        # Check for standard CampusEcho format: {side}{intensity}P{pattern}
        match = re.fullmatch(r"([LRBOlrbo])(\d)P(\d)", raw)
        if match:
            side = match.group(1).upper()
            intensity = min(9, max(0, int(match.group(2))))
            pattern_key = match.group(3)
            fw_pattern = PATTERN_TRANSLATION_MAP.get(pattern_key, 1)

            if side == "O":
                return "O,0,0\n"
            return f"{side},{intensity},{fw_pattern}\n"

        # If unrecognised, fallback to gentle straight confirmation or off
        logger.warning(f"[HapticBridge] Unrecognised command format '{raw}', defaulting to O,0,0\\n")
        return "O,0,0\n"

    # ── Connection Management ─────────────────────────────────────────────────
    def connect(self, port: str, baudrate: int = 115200) -> bool:
        """
        Connects to the specified COM port.
        Returns True if successful, False otherwise.
        """
        if not SERIAL_AVAILABLE:
            logger.error("[HapticBridge] pyserial is not installed. Cannot open serial port.")
            return False

        with self._lock:
            # Close existing connection if any
            self._close_internal()
            self.port = port
            self.baudrate = baudrate

            try:
                self.serial_conn = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    timeout=1.0,
                    write_timeout=1.0,
                )
                self._connected = True
                logger.info(f"[HapticBridge] Connected to ESP32 on {port} @ {baudrate} baud.")
                return True
            except Exception as e:
                self._connected = False
                self.serial_conn = None
                self.error_count += 1
                logger.warning(f"[HapticBridge] Failed to connect to {port}: {e}")
                return False

    def disconnect(self) -> None:
        """Sends all-off and safely closes the serial port."""
        # Send off command immediately
        self.silence()
        # Brief pause to let worker flush before closing
        time.sleep(0.05)
        with self._lock:
            self._close_internal()
            logger.info("[HapticBridge] Disconnected from ESP32.")

    def silence(self) -> None:
        """Forces both motors off immediately."""
        self.send_raw("O,0,0\n")

    def _close_internal(self) -> None:
        """Internal close helper (must hold self._lock)."""
        self._connected = False
        if self.serial_conn:
            try:
                if self.serial_conn.is_open:
                    self.serial_conn.close()
            except Exception as e:
                logger.debug(f"[HapticBridge] Error closing serial connection: {e}")
            finally:
                self.serial_conn = None

    # ── Command Transmission ──────────────────────────────────────────────────
    def send_haptic(self, cmd: str) -> bool:
        """
        Translates a CampusEcho haptic command (e.g. 'L7P2') and enqueues it
        for non-blocking transmission to the wristband.
        """
        if not cmd:
            return False
        fw_cmd = self.translate_to_firmware(cmd)
        return self.send_raw(fw_cmd)

    def send_raw(self, csv_cmd: str) -> bool:
        """
        Enqueues a raw CSV command string (e.g. 'L,7,2\\n') for transmission.
        Non-blocking: drops message if queue is completely saturated.
        """
        if not csv_cmd.endswith("\n"):
            csv_cmd += "\n"

        try:
            self._queue.put_nowait(csv_cmd)
            return True
        except queue.Full:
            logger.warning("[HapticBridge] Command queue full — dropping haptic command.")
            return False

    # ── Worker Thread Loop ────────────────────────────────────────────────────
    def _worker_loop(self) -> None:
        """Background thread worker that processes queued serial writes."""
        while not self._stop_event.is_set():
            try:
                cmd = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if self._stop_event.is_set():
                break

            with self._lock:
                if not self._connected or not self.serial_conn or not self.serial_conn.is_open:
                    # Not connected — discard command cleanly
                    self._queue.task_done()
                    continue

                try:
                    payload = cmd.encode("ascii", errors="ignore")
                    self.serial_conn.write(payload)
                    self.serial_conn.flush()
                    self.tx_count += 1
                    self.last_cmd = cmd.strip()
                    self.last_sent_at = time.time()
                except Exception as e:
                    self.error_count += 1
                    logger.warning(f"[HapticBridge] Serial write failed on {self.port}: {e}")
                    self._close_internal()
                finally:
                    self._queue.task_done()

    # ── Port Discovery & Utilities ────────────────────────────────────────────
    @staticmethod
    def list_ports() -> List[Dict[str, str]]:
        """
        Lists all available serial / COM ports on the system.
        Returns a list of dicts: [{'port': 'COM4', 'description': '...', 'hwid': '...'}]
        """
        if not SERIAL_AVAILABLE:
            return []
        ports = []
        try:
            for p in serial.tools.list_ports.comports():
                ports.append({
                    "port": p.device,
                    "description": p.description or p.device,
                    "hwid": p.hwid or "",
                })
        except Exception as e:
            logger.warning(f"[HapticBridge] Error enumerating COM ports: {e}")
        return ports

    @classmethod
    def find_wristband_port(cls) -> Optional[str]:
        """
        Heuristically searches available COM ports for the CampusEcho wristband
        or a standard Bluetooth Serial Port Profile device.
        """
        ports = cls.list_ports()
        # Look for explicit name first
        for p in ports:
            desc = p["description"].lower()
            hwid = p["hwid"].lower()
            if "campusecho" in desc or "campusecho" in hwid:
                return p["port"]

        # Look for Bluetooth SPP port signatures
        for p in ports:
            desc = p["description"].lower()
            if "bluetooth" in desc or "standard serial over bluetooth" in desc:
                return p["port"]

        return None

    # ── ModeRouter Callback ───────────────────────────────────────────────────
    def on_dispatch(self, result: DispatchResult) -> None:
        """
        Callback handler to be registered with ModeRouter.
        Automatically transmits haptic commands when output mode permits.
        """
        if result.mode == OutputMode.VOICE_ONLY:
            # In VOICE_ONLY mode, ensure physical motors are silent
            self.silence()
            return

        if result.haptic_cmd:
            self.send_haptic(result.haptic_cmd)

    # ── Status Dictionary ─────────────────────────────────────────────────────
    def get_status(self) -> Dict:
        """Returns diagnostic status dict for API and Dashboard."""
        return {
            "connected": self.is_connected,
            "port": self.port,
            "baudrate": self.baudrate,
            "tx_count": self.tx_count,
            "error_count": self.error_count,
            "last_cmd": self.last_cmd,
            "last_sent_at": self.last_sent_at,
        }

    def close(self) -> None:
        """Clean shutdown of worker and serial connection."""
        self._stop_event.set()
        self.disconnect()
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=0.5)
