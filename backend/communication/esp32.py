"""
ESP32 Wearable Communication Client.
Supports:
1. Primary: Wi-Fi HTTP client sending high-level commands (/left, /right, /forward, /stop, /arrived, /unknown)
2. Fail-safe: Detects network disconnection and notifies the system
3. Fallback: Serial / Bluetooth bridge compatibility if Wi-Fi is unconfigured or unreachable
"""
import time
from typing import Optional, Dict, Any
import httpx


class ESP32Client:
    """
    Communicates with the ESP32 wearable over Wi-Fi HTTP endpoints.
    Provides connection health tracking, retry logic, and safety timeout handling.
    """

    DEFAULT_TIMEOUT_S = 1.2
    MAX_CONSECUTIVE_FAILURES = 3

    # Command to endpoint path mapping
    COMMAND_ENDPOINTS = {
        "LEFT": "/left",
        "RIGHT": "/right",
        "FORWARD": "/forward",
        "STOP": "/stop",
        "ARRIVED": "/arrived",
        "UNKNOWN": "/unknown",
    }

    # Fallback serial command mapping (for USB / Bluetooth paired wristband)
    SERIAL_FALLBACK_MAPPINGS = {
        "LEFT": "L,8,0\n",
        "RIGHT": "R,8,0\n",
        "FORWARD": "B,8,0\n",
        "STOP": "O,0,0\n",
        "ARRIVED": "B,6,1\n",
        "UNKNOWN": "B,5,3\n",
    }

    def __init__(
        self,
        esp32_ip: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_S,
        serial_bridge: Optional[Any] = None,
    ):
        self.esp32_ip = esp32_ip
        self.timeout = timeout
        self.serial_bridge = serial_bridge

        self._is_connected: bool = False
        self._consecutive_failures: int = 0
        self._last_command_sent: Optional[str] = None
        self._last_command_time: float = 0.0
        self._last_error: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def status_summary(self) -> Dict[str, Any]:
        return {
            "connected": self._is_connected,
            "esp32_ip": self.esp32_ip,
            "last_command": self._last_command_sent,
            "last_command_time": self._last_command_time,
            "consecutive_failures": self._consecutive_failures,
            "last_error": self._last_error,
        }

    def set_ip(self, ip: str) -> None:
        """Updates the target ESP32 IP address."""
        self.esp32_ip = ip.strip() if ip else None
        self._consecutive_failures = 0

    def send_command(self, command: str) -> bool:
        """
        Sends high-level navigation command to ESP32.
        First tries Wi-Fi HTTP. If Wi-Fi is unconfigured or unreachable,
        tries local Serial/Bluetooth bridge.
        """
        command = command.upper()
        self._last_command_sent = command
        self._last_command_time = time.time()

        # 1. Try Wi-Fi HTTP if IP is configured
        if self.esp32_ip:
            success = self._send_http(command)
            if success:
                self._is_connected = True
                self._consecutive_failures = 0
                self._last_error = None
                return True
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    self._is_connected = False

        # 2. Try Serial / Bluetooth fallback if available
        if self.serial_bridge:
            success = self._send_serial(command)
            if success:
                self._is_connected = True
                return True

        if not self.esp32_ip and not self.serial_bridge:
            self._last_error = "No Wi-Fi IP or Serial Bridge configured"

        return False

    def _send_http(self, command: str) -> bool:
        endpoint = self.COMMAND_ENDPOINTS.get(command, "/stop")
        url = f"http://{self.esp32_ip}{endpoint}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    return True
                self._last_error = f"HTTP {resp.status_code}: {resp.text}"
                return False
        except Exception as e:
            self._last_error = f"Wi-Fi connection error: {str(e)}"
            return False

    def _send_serial(self, command: str) -> bool:
        try:
            line = self.SERIAL_FALLBACK_MAPPINGS.get(command, "O,0,0\n")
            if hasattr(self.serial_bridge, "send_raw"):
                return bool(self.serial_bridge.send_raw(line))
            elif hasattr(self.serial_bridge, "write"):
                self.serial_bridge.write(line.encode("ascii"))
                return True
        except Exception as e:
            self._last_error = f"Serial error: {str(e)}"
        return False

    def check_connection(self) -> bool:
        """Pings ESP32 /status endpoint or sends test stop."""
        if not self.esp32_ip:
            return bool(self.serial_bridge and getattr(self.serial_bridge, "is_connected", False))

        try:
            with httpx.Client(timeout=1.0) as client:
                r = client.get(f"http://{self.esp32_ip}/status")
                self._is_connected = (r.status_code == 200)
                return self._is_connected
        except Exception:
            self._is_connected = False
            return False
