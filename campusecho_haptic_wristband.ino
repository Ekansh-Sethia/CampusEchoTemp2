/*
  CampusEcho — Haptic Wristband Firmware
  ---------------------------------------
  Board: ESP32-WROOM-32 DevKitC
  Motors: 2x coin ERM vibration motors, driven via NPN transistor low-side switches
  Comms: Classic Bluetooth SPP (paired as a serial device from the host app)

  Command protocol (sent from host over Bluetooth Serial), newline-terminated:
      <side>,<intensity 0-9>,<pattern 0-3>\n

      side:
        L = left motor only
        R = right motor only
        B = both motors (used for "stop" / critical escalation)
        O = off (both motors off, overrides intensity/pattern)

      intensity: 0 (off) to 9 (max) -> mapped internally to PWM duty cycle

      pattern:
        0 = continuous (steady vibration at the given intensity)
        1 = slow pulse   (500ms on / 500ms off)   -- informational
        2 = rapid pulse  (150ms on / 100ms off)   -- act now
        3 = double-pulse + pause                  -- critical / stop

  Safety fail-safe: if no command is received for FAILSAFE_TIMEOUT_MS,
  both motors are forced off. This prevents a stuck-on vibration if the
  Bluetooth link drops or the host app crashes mid-session.

  Example commands:
      L,7,2      -> left motor, strong, rapid pulse (obstacle left, close)
      R,3,1      -> right motor, mild, slow pulse (obstacle right, far)
      B,9,3      -> both motors, max, double-pulse (critical / escalate)
      O,0,0      -> all off
*/

#include "BluetoothSerial.h"

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Enable it in "Tools -> Board" menu / partition scheme.
#endif

BluetoothSerial SerialBT;

// ---------------- Pin configuration ----------------
const int LEFT_MOTOR_PIN  = 25;
const int RIGHT_MOTOR_PIN = 26;

// LEDC (PWM) configuration
// NOTE: ESP32 Arduino core 3.x replaced the old channel-based LEDC API
// (ledcSetup + ledcAttachPin + ledcWrite(channel, duty)) with a simpler
// pin-based API (ledcAttach(pin, freq, res) + ledcWrite(pin, duty)).
// This sketch targets core 3.x. If your board manager has an older core
// (2.x) installed, either upgrade it via Boards Manager, or see the
// commented legacy block near setup() below.
const int PWM_FREQ      = 5000;   // 5 kHz, well above motor mechanical response, avoids audible whine
const int PWM_RES_BITS  = 8;      // 0-255 duty range

// ---------------- State ----------------
struct MotorState {
  int   intensity   = 0;     // 0-9, as received
  int   pattern     = 0;     // 0-3
  bool  active      = false; // is this motor currently commanded on at all
  bool  pulseOn     = false; // for patterned pulsing, current on/off phase
  unsigned long lastToggle = 0;
  unsigned long lastDoublePulseStep = 0;
  int   doublePulsePhase = 0; // 0,1,2,3 cycle for double-pulse pattern
};

MotorState leftState;
MotorState rightState;

unsigned long lastCommandTime = 0;
const unsigned long FAILSAFE_TIMEOUT_MS = 3000; // auto-off if link goes quiet

String inputBuffer = "";

// ---------------- Helpers ----------------
int intensityToDuty(int intensity) {
  // Map 0-9 -> 0-255 PWM duty. Clamp defensively.
  intensity = constrain(intensity, 0, 9);
  return map(intensity, 0, 9, 0, 255);
}

void setMotorRaw(int pin, int duty) {
  ledcWrite(pin, duty);   // core 3.x: ledcWrite takes the GPIO pin, not a channel number
}

void applyMotorPattern(MotorState &state, int pin) {
  if (!state.active || state.intensity == 0) {
    setMotorRaw(pin, 0);
    return;
  }

  int duty = intensityToDuty(state.intensity);
  unsigned long now = millis();

  switch (state.pattern) {
    case 0: // continuous
      setMotorRaw(pin, duty);
      break;

    case 1: { // slow pulse: 500ms on / 500ms off
      const unsigned long ON_MS = 500, OFF_MS = 500;
      unsigned long interval = state.pulseOn ? ON_MS : OFF_MS;
      if (now - state.lastToggle >= interval) {
        state.pulseOn = !state.pulseOn;
        state.lastToggle = now;
      }
      setMotorRaw(pin, state.pulseOn ? duty : 0);
      break;
    }

    case 2: { // rapid pulse: 150ms on / 100ms off
      const unsigned long ON_MS = 150, OFF_MS = 100;
      unsigned long interval = state.pulseOn ? ON_MS : OFF_MS;
      if (now - state.lastToggle >= interval) {
        state.pulseOn = !state.pulseOn;
        state.lastToggle = now;
      }
      setMotorRaw(pin, state.pulseOn ? duty : 0);
      break;
    }

    case 3: { // double-pulse + pause: buzz-buzz-....-buzz-buzz-....
      // phase 0: on (120ms), phase 1: off (100ms), phase 2: on (120ms), phase 3: off (600ms pause)
      const unsigned long PHASE_MS[4] = {120, 100, 120, 600};
      bool phaseOn[4] = {true, false, true, false};

      if (now - state.lastDoublePulseStep >= PHASE_MS[state.doublePulsePhase]) {
        state.doublePulsePhase = (state.doublePulsePhase + 1) % 4;
        state.lastDoublePulseStep = now;
      }
      setMotorRaw(pin, phaseOn[state.doublePulsePhase] ? duty : 0);
      break;
    }

    default:
      setMotorRaw(pin, 0);
      break;
  }
}

void resetMotorTiming(MotorState &state) {
  state.pulseOn = false;
  state.lastToggle = millis();
  state.doublePulsePhase = 0;
  state.lastDoublePulseStep = millis();
}

void allMotorsOff() {
  leftState.active = false;
  rightState.active = false;
  ledcWrite(LEFT_MOTOR_PIN, 0);
  ledcWrite(RIGHT_MOTOR_PIN, 0);
}

// ---------------- Command parsing ----------------
void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  // Expected format: side,intensity,pattern
  int firstComma  = cmd.indexOf(',');
  int secondComma = cmd.indexOf(',', firstComma + 1);
  if (firstComma == -1 || secondComma == -1) {
    Serial.println("Malformed command, ignoring: " + cmd);
    return;
  }

  String sideStr      = cmd.substring(0, firstComma);
  String intensityStr = cmd.substring(firstComma + 1, secondComma);
  String patternStr   = cmd.substring(secondComma + 1);

  sideStr.trim();
  char side = sideStr.length() > 0 ? sideStr.charAt(0) : 'O';
  int intensity = intensityStr.toInt();
  int pattern   = patternStr.toInt();

  lastCommandTime = millis();

  if (side == 'O' || side == 'o') {
    allMotorsOff();
    return;
  }

  if (side == 'L' || side == 'l' || side == 'B' || side == 'b') {
    leftState.intensity = intensity;
    leftState.pattern   = pattern;
    leftState.active    = true;
    resetMotorTiming(leftState);
  } else {
    leftState.active = false;
  }

  if (side == 'R' || side == 'r' || side == 'B' || side == 'b') {
    rightState.intensity = intensity;
    rightState.pattern   = pattern;
    rightState.active    = true;
    resetMotorTiming(rightState);
  } else {
    rightState.active = false;
  }
}

// ---------------- Setup / Loop ----------------
void setup() {
  Serial.begin(115200);
  SerialBT.begin("CampusEcho-Wristband"); // Bluetooth device name shown when pairing
  Serial.println("CampusEcho haptic wristband ready. Pair via Bluetooth as 'CampusEcho-Wristband'.");

  // core 3.x pin-based LEDC setup: attaches PWM directly to a GPIO pin,
  // no separate channel number needed.
  ledcAttach(LEFT_MOTOR_PIN, PWM_FREQ, PWM_RES_BITS);
  ledcAttach(RIGHT_MOTOR_PIN, PWM_FREQ, PWM_RES_BITS);

  allMotorsOff();
  lastCommandTime = millis();
}

void loop() {
  // --- Read incoming Bluetooth data, line by line ---
  while (SerialBT.available()) {
    char c = SerialBT.read();
    if (c == '\n') {
      handleCommand(inputBuffer);
      inputBuffer = "";
    } else if (c != '\r') {
      inputBuffer += c;
    }
  }

  // --- Fail-safe: if the host goes quiet, turn everything off ---
  if (millis() - lastCommandTime > FAILSAFE_TIMEOUT_MS) {
    if (leftState.active || rightState.active) {
      allMotorsOff();
      Serial.println("Fail-safe: no command received, motors off.");
    }
  }

  // --- Continuously apply the current pattern (non-blocking) ---
  applyMotorPattern(leftState, LEFT_MOTOR_PIN);
  applyMotorPattern(rightState, RIGHT_MOTOR_PIN);
}
