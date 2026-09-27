/*
  Indoor Landmark & Position Recovery — ESP32 Wi-Fi Navigation Firmware
  ---------------------------------------------------------------------
  Hardware Configuration:
    Board: ESP32-WROOM-32 DevKitC
    GPIO25: LEFT vibration motor (via 2N2222A NPN low-side switch)
    GPIO26: RIGHT vibration motor (via 2N2222A NPN low-side switch)
    PWM: 5000 Hz, 8-bit resolution (Arduino-ESP32 3.x ledcAttach / ledcWrite)
    Diodes: 1N4148 flyback diodes across motor terminals

  Communication:
    Wi-Fi WebServer on Port 80
    Endpoints:
      GET /left     -> Left motor strong, Right off
      GET /right    -> Left off, Right motor strong
      GET /forward  -> Both motors strong
      GET /arrived  -> Short arrival pulses
      GET /unknown  -> Double pulse warning (low-confidence safe state)
      GET /stop     -> Both motors off
      GET /status   -> JSON status with uptime & last command

  Fail-Safe:
    2000ms safety watchdog (FAILSAFE_TIMEOUT_MS).
    If no command is received within 2 seconds, both motors are automatically stopped.

  Fallback Mode:
    If STA Wi-Fi cannot connect within 10 seconds, ESP32 launches Access Point:
    SSID: "CampusEcho-Wristband" (IP: 192.168.4.1) for offline hackathon testing.
*/

#include <WiFi.h>
#include <WebServer.h>

// ---------------- Wi-Fi Credentials ----------------
// Replace with your local Wi-Fi credentials or phone hotspot
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Fallback SoftAP credentials
const char* AP_SSID       = "CampusEcho-Wristband";
const char* AP_PASSWORD   = "12345678";

// ---------------- Pin Assignment ----------------
const int MOTOR_LEFT_PIN  = 25;
const int MOTOR_RIGHT_PIN = 26;

// ---------------- PWM Configuration (ESP32 Core 3.x) ----------------
const int PWM_FREQ        = 5000;  // 5 kHz avoids audible noise
const int PWM_RESOLUTION  = 8;     // 8-bit (0-255 duty cycle)

const int VIB_OFF         = 0;
const int VIB_LOW         = 70;
const int VIB_MEDIUM      = 150;
const int VIB_HIGH        = 255;

// ---------------- Safety Watchdog ----------------
const unsigned long FAILSAFE_TIMEOUT_MS = 2000;
unsigned long lastCommandTime = 0;
bool motorsActive = false;

// ---------------- Pattern State ----------------
enum PatternType {
  PATTERN_NONE,
  PATTERN_ARRIVED,
  PATTERN_UNKNOWN
};

PatternType activePattern = PATTERN_NONE;
unsigned long patternStartTime = 0;

WebServer server(80);
String lastCommand = "INIT";

// ---------------- Motor Control Helpers ----------------
void setMotors(int leftDuty, int rightDuty) {
  leftDuty  = constrain(leftDuty, 0, 255);
  rightDuty = constrain(rightDuty, 0, 255);
  ledcWrite(MOTOR_LEFT_PIN, leftDuty);
  ledcWrite(MOTOR_RIGHT_PIN, rightDuty);
  motorsActive = (leftDuty > 0 || rightDuty > 0);
}

void stopMotors() {
  setMotors(VIB_OFF, VIB_OFF);
  activePattern = PATTERN_NONE;
  motorsActive = false;
}

// ---------------- HTTP Endpoints ----------------
void handleLeft() {
  lastCommandTime = millis();
  activePattern = PATTERN_NONE;
  lastCommand = "LEFT";
  setMotors(VIB_HIGH, VIB_OFF);
  server.send(200, "text/plain", "OK: LEFT");
  Serial.println("[CMD] LEFT -> GPIO25: HIGH, GPIO26: OFF");
}

void handleRight() {
  lastCommandTime = millis();
  activePattern = PATTERN_NONE;
  lastCommand = "RIGHT";
  setMotors(VIB_OFF, VIB_HIGH);
  server.send(200, "text/plain", "OK: RIGHT");
  Serial.println("[CMD] RIGHT -> GPIO25: OFF, GPIO26: HIGH");
}

void handleForward() {
  lastCommandTime = millis();
  activePattern = PATTERN_NONE;
  lastCommand = "FORWARD";
  setMotors(VIB_HIGH, VIB_HIGH);
  server.send(200, "text/plain", "OK: FORWARD");
  Serial.println("[CMD] FORWARD -> Both Motors HIGH");
}

void handleArrived() {
  lastCommandTime = millis();
  activePattern = PATTERN_ARRIVED;
  patternStartTime = millis();
  lastCommand = "ARRIVED";
  server.send(200, "text/plain", "OK: ARRIVED");
  Serial.println("[CMD] ARRIVED -> Pulsing Pattern");
}

void handleUnknown() {
  lastCommandTime = millis();
  activePattern = PATTERN_UNKNOWN;
  patternStartTime = millis();
  lastCommand = "UNKNOWN";
  server.send(200, "text/plain", "OK: UNKNOWN (Safe Mode)");
  Serial.println("[CMD] UNKNOWN -> Double Pulse Safe Warning");
}

void handleStop() {
  lastCommandTime = millis();
  lastCommand = "STOP";
  stopMotors();
  server.send(200, "text/plain", "OK: STOP");
  Serial.println("[CMD] STOP -> Motors OFF");
}

void handleStatus() {
  String json = "{";
  json += "\"status\":\"ONLINE\",";
  json += "\"uptime_ms\":" + String(millis()) + ",";
  json += "\"last_command\":\"" + lastCommand + "\",";
  json += "\"motors_active\":" + String(motorsActive ? "true" : "false") + ",";
  json += "\"ip\":\"" + (WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString() : WiFi.softAPIP().toString()) + "\"";
  json += "}";
  server.send(200, "application/json", json);
}

void handleNotFound() {
  server.send(404, "text/plain", "Not Found");
}

// ---------------- Setup ----------------
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("==================================================");
  Serial.println(" CampusEcho — Indoor Position Recovery Firmware");
  Serial.println("==================================================");

  // Configure PWM using Arduino-ESP32 3.x pin-based API
  ledcAttach(MOTOR_LEFT_PIN, PWM_FREQ, PWM_RESOLUTION);
  ledcAttach(MOTOR_RIGHT_PIN, PWM_FREQ, PWM_RESOLUTION);
  stopMotors();

  // Connect to Wi-Fi
  Serial.print("Connecting to Wi-Fi SSID: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startAttempt = millis();
  bool connected = false;

  while (millis() - startAttempt < 8000) {
    if (WiFi.status() == WL_CONNECTED) {
      connected = true;
      break;
    }
    delay(400);
    Serial.print(".");
  }

  Serial.println();
  if (connected) {
    Serial.println("[WiFi] Connected successfully!");
    Serial.print("[WiFi] IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[WiFi] STA connection timed out. Starting Fallback SoftAP...");
    WiFi.mode(WIFI_AP);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    Serial.print("[WiFi] Access Point started: ");
    Serial.println(AP_SSID);
    Serial.print("[WiFi] AP IP Address: ");
    Serial.println(WiFi.softAPIP());
  }

  // Register WebServer routes
  server.on("/left", handleLeft);
  server.on("/right", handleRight);
  server.on("/forward", handleForward);
  server.on("/arrived", handleArrived);
  server.on("/unknown", handleUnknown);
  server.on("/stop", handleStop);
  server.on("/status", handleStatus);
  server.onNotFound(handleNotFound);

  // Enable CORS
  server.enableCORS(true);
  server.begin();
  Serial.println("[HTTP] WebServer listening on port 80.");
  Serial.println("[System] Ready for navigation commands.");
}

// ---------------- Main Loop ----------------
void loop() {
  server.handleClient();

  unsigned long now = millis();

  // Pattern Handler
  if (activePattern == PATTERN_ARRIVED) {
    // 3 short celebratory pulses
    unsigned long elapsed = now - patternStartTime;
    if (elapsed < 1200) {
      int phase = (elapsed / 200) % 2;
      setMotors(phase ? VIB_MEDIUM : VIB_OFF, phase ? VIB_MEDIUM : VIB_OFF);
    } else {
      stopMotors();
    }
  } else if (activePattern == PATTERN_UNKNOWN) {
    // Double pulse safe alert (2 short pulses then stop)
    unsigned long elapsed = now - patternStartTime;
    if (elapsed < 150) {
      setMotors(VIB_LOW, VIB_LOW);
    } else if (elapsed < 250) {
      setMotors(VIB_OFF, VIB_OFF);
    } else if (elapsed < 400) {
      setMotors(VIB_LOW, VIB_LOW);
    } else {
      stopMotors();
    }
  }

  // Safety Watchdog: Auto-stop if no command received for FAILSAFE_TIMEOUT_MS
  if (motorsActive && activePattern == PATTERN_NONE) {
    if (now - lastCommandTime > FAILSAFE_TIMEOUT_MS) {
      Serial.println("[SAFETY] Watchdog timeout: no command for 2000ms. Stopping motors.");
      stopMotors();
    }
  }
}
