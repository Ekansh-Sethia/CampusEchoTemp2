# Indoor Landmark & Position Recovery — Implementation Guide

## 1. Objective

Build an indoor localization and navigation-recovery system for the wearable wristband.

The system should:

- Detect when GPS/visual localization becomes unreliable.
- Recover approximate indoor position using predefined BLE landmarks.
- Optionally use QR markers as an explicit fallback.
- Feed the recovered position into the existing destination-navigation system.
- Send high-level navigation commands to the ESP32 over Wi-Fi.
- Provide left/right/forward/unknown feedback through two vibration motors.
- Stop giving potentially misleading directions when localization confidence is too low.
- Allow testing at multiple predefined indoor locations.

## 2. Overall Architecture

```text
GPS / Visual Localization
          |
          v
  Localization Manager
          |
   +------+------+
   |             |
 Reliable       Low
   |             |
 Normal       BLE Recovery
 Navigation       |
                  v
          Indoor Position
                  |
                  v
          Confidence Check
             /        \
          HIGH        LOW
           |           |
        Navigate     QR / Safe
           |         Recovery
           +----+------+
                |
                v
        Indoor Navigation
                |
                v
              Wi-Fi
                |
                v
              ESP32
             /     \
        GPIO25     GPIO26
        LEFT       RIGHT
        MOTOR      MOTOR
```

## 3. Hardware

| Component | Quantity | Purpose |
|---|---:|---|
| ESP32-WROOM-32 DevKit | 1 | Wearable controller |
| 3V 10mm vibration motor | 2 | Left/right haptic feedback |
| 2N2222A NPN transistor | 2 | Motor switching |
| 1kΩ resistor | 2 | Transistor base resistor |
| 1N4148 diode | 2 | Flyback protection |
| 3.7V LiPo | 1 | Battery |
| TP4056 protection/charger | 1 | Battery charging |
| 3-pin slide switch | 1 | Power ON/OFF |
| LED | 1 | Power indicator |
| 330Ω resistor | 1 | LED current limiting |
| Perfboard | 1 | Final circuit |

## 4. ESP32 Pin Assignment

```text
GPIO25 → LEFT vibration motor
GPIO26 → RIGHT vibration motor
```

## 5. Motor Driver Wiring

Never drive the vibration motors directly from ESP32 GPIOs.

### Left motor

```text
GPIO25 ── 1kΩ ── Base
                 2N2222A
Motor - ─────── Collector
GND ─────────── Emitter

MAIN+ ───────── Motor +
```

### Right motor

```text
GPIO26 ── 1kΩ ── Base
                 2N2222A
Motor - ─────── Collector
GND ─────────── Emitter

MAIN+ ───────── Motor +
```

For the user's confirmed transistor:

```text
Flat/printed side facing you:

LEFT   = Collector
MIDDLE = Base
RIGHT  = Emitter
```

Verify the pinout if using a different transistor.

## 6. Flyback Diodes

Put one diode directly across each motor.

```text
Motor + ────────|<|──────── Motor -
                 diode
```

For the 1N4148:

```text
Stripe / cathode     → Motor +
Non-striped / anode  → Motor -
```

The diode must be physically close to the motor/transistor switching path.

## 7. Power Rails

`MAIN+` is the switched positive supply rail, not an ESP32 pin.

```text
TP4056 OUT+
     |
  Switch
     |
   MAIN+
```

All grounds must be common:

```text
TP4056 OUT-
     |
     +---- ESP32 GND
     +---- Left transistor emitter
     +---- Right transistor emitter
     +---- LED cathode
```

Do not intentionally short 3V3 to GND.

### ESP32 power warning

Do **not** connect a 3.7V LiPo directly to the ESP32 `3V3` pin. A LiPo can reach about 4.2V when fully charged.

Before battery-powered operation, verify the exact DevKit power-input specification or use an appropriate regulator/power-management stage. USB power is recommended while debugging.

## 8. Power LED

```text
MAIN+
  |
 330Ω
  |
LED long leg (+)
LED short leg (-)
  |
 GND
```

The LED is therefore ON whenever the switched MAIN+ rail is active.

# 9. ESP32 Motor Test

The project uses Arduino-ESP32 3.x LEDC:

```cpp
ledcAttach(pin, frequency, resolution);
ledcWrite(pin, duty);
```

Use:

```cpp
const int MOTOR_LEFT = 25;
const int MOTOR_RIGHT = 26;

const int PWM_FREQ = 5000;
const int PWM_RESOLUTION = 8;

const int VIB_OFF = 0;
const int VIB_LOW = 70;
const int VIB_MEDIUM = 150;
const int VIB_HIGH = 255;

void setMotors(int left, int right) {
  ledcWrite(MOTOR_LEFT, left);
  ledcWrite(MOTOR_RIGHT, right);
}

void stopMotors(int timeMs = 500) {
  setMotors(VIB_OFF, VIB_OFF);
  delay(timeMs);
}

void pulse(int left, int right, int onTime, int offTime, int repetitions) {
  for (int i = 0; i < repetitions; i++) {
    setMotors(left, right);
    delay(onTime);
    setMotors(VIB_OFF, VIB_OFF);
    delay(offTime);
  }
}

void setup() {
  Serial.begin(115200);

  ledcAttach(MOTOR_LEFT, PWM_FREQ, PWM_RESOLUTION);
  ledcAttach(MOTOR_RIGHT, PWM_FREQ, PWM_RESOLUTION);

  setMotors(VIB_OFF, VIB_OFF);

  Serial.println();
  Serial.println("ESP32 VIBRATION MOTOR TEST");
  delay(2000);
}

void loop() {
  pulse(VIB_LOW, VIB_OFF, 1000, 500, 3);
  stopMotors();

  pulse(VIB_MEDIUM, VIB_OFF, 1000, 500, 3);
  stopMotors();

  pulse(VIB_HIGH, VIB_OFF, 1000, 500, 3);
  stopMotors();

  pulse(VIB_OFF, VIB_LOW, 1000, 500, 3);
  stopMotors();

  pulse(VIB_OFF, VIB_MEDIUM, 1000, 500, 3);
  stopMotors();

  pulse(VIB_OFF, VIB_HIGH, 1000, 500, 3);
  stopMotors();

  pulse(VIB_LOW, VIB_LOW, 1000, 500, 3);
  stopMotors();

  pulse(VIB_MEDIUM, VIB_MEDIUM, 1000, 500, 3);
  stopMotors();

  pulse(VIB_HIGH, VIB_HIGH, 1000, 500, 3);
  stopMotors();

  for (int i = 0; i < 5; i++) {
    setMotors(VIB_HIGH, VIB_OFF);
    delay(400);
    setMotors(VIB_OFF, VIB_HIGH);
    delay(400);
  }

  stopMotors();

  pulse(VIB_HIGH, VIB_OFF, 150, 150, 10);
  stopMotors();

  pulse(VIB_OFF, VIB_HIGH, 150, 150, 10);
  stopMotors();

  for (int i = 0; i < 10; i++) {
    setMotors(VIB_HIGH, VIB_OFF);
    delay(200);
    setMotors(VIB_OFF, VIB_HIGH);
    delay(200);
  }

  stopMotors();

  for (int intensity = 40; intensity <= 255; intensity += 20) {
    setMotors(intensity, intensity);
    delay(300);
  }

  stopMotors();

  for (int intensity = 255; intensity >= 40; intensity -= 20) {
    setMotors(intensity, intensity);
    delay(300);
  }

  stopMotors();

  pulse(VIB_HIGH, VIB_HIGH, 150, 150, 15);
  stopMotors(1000);

  delay(3000);
}
```

# 10. BLE Landmark System

Use 3–5 predefined BLE landmarks.

Example:

| ID | Landmark | Floor | Zone | X | Y |
|---|---|---:|---|---:|---:|
| B1 | Main Entrance | 0 | Entrance | 0 | 0 |
| B2 | Central Corridor | 0 | Corridor | 5 | 0 |
| B3 | Computer Lab | 0 | Lab | 10 | 0 |
| B4 | Staircase | 0 | Staircase | 5 | 5 |
| B5 | Library | 0 | Library | 10 | 5 |

Coordinates can represent positions in the indoor map; they do not imply centimeter-level physical accuracy.

## BLE Strategy

For the hackathon MVP, use **strongest/stable landmark → zone** rather than claiming precise RSSI trilateration.

Example:

```text
B1 strongest/stable → Entrance
B2 strongest/stable → Corridor
B3 strongest/stable → Computer Lab
B4 strongest/stable → Staircase
B5 strongest/stable → Library
```

A more advanced version can combine several RSSI values, but indoor RSSI is noisy and should be calibrated.

# 11. Landmark Configuration

`landmarks.json`

```json
[
  {
    "id": "B1",
    "name": "Main Entrance",
    "floor": 0,
    "zone": "Entrance",
    "x": 0,
    "y": 0
  },
  {
    "id": "B2",
    "name": "Central Corridor",
    "floor": 0,
    "zone": "Corridor",
    "x": 5,
    "y": 0
  },
  {
    "id": "B3",
    "name": "Computer Lab",
    "floor": 0,
    "zone": "Lab",
    "x": 10,
    "y": 0
  },
  {
    "id": "B4",
    "name": "Staircase",
    "floor": 0,
    "zone": "Staircase",
    "x": 5,
    "y": 5
  },
  {
    "id": "B5",
    "name": "Library",
    "floor": 0,
    "zone": "Library",
    "x": 10,
    "y": 5
  }
]
```

# 12. BLE Smoothing

Do not change location after one noisy scan.

Example:

```text
B2
B2
B2
B3
B2
```

A simple rule is:

```text
Accept a new landmark after several consecutive matching observations.
```

This prevents location jumping.

Useful BLE data:

```text
landmark_id
RSSI
timestamp
number_of_matching_scans
confidence
```

# 13. BLE Confidence

Represent confidence from `0.0` to `1.0`.

Possible starting thresholds:

```text
0.75–1.00 → HIGH
0.50–0.74 → MEDIUM
0.00–0.49 → LOW
```

These are starting values and must be calibrated in the actual building.

Confidence can consider:

- RSSI strength
- Number of detected landmarks
- Stability across scans
- Agreement between consecutive estimates

# 14. QR Fallback

QR markers provide explicit localization recovery.

```text
BLE confidence LOW
        |
        v
Ask user to scan landmark
        |
        v
QR = B3
        |
        v
Current position = Computer Lab
        |
        v
Resume navigation
```

A QR payload can simply be:

```text
B3
```

or:

```json
{
  "type": "indoor_landmark",
  "id": "B3"
}
```

# 15. Localization Manager

Use one component to choose the current localization source.

Conceptual logic:

```text
GPS/visual reliable?
    YES → use it
    NO
     |
     v
BLE reliable?
    YES → use BLE
    NO
     |
     v
QR available?
    YES → use QR
    NO
     |
     v
Fresh last-known position?
    YES → temporary low-confidence state
    NO
     |
     v
UNKNOWN
```

Suggested sources:

```text
GPS
VISUAL
BLE
QR
LAST_KNOWN
UNKNOWN
```

Example localization object:

```json
{
  "source": "BLE",
  "landmark_id": "B3",
  "zone": "Computer Lab",
  "floor": 0,
  "x": 10,
  "y": 0,
  "confidence": 0.82,
  "timestamp": 1720000000
}
```

# 16. Safe Low-Confidence Behavior

When localization confidence is too low:

Do not:

```text
Guess LEFT
Guess RIGHT
Continue an old route forever
Pretend the user is still at the last known location
```

Instead:

```text
navigation_state = UNKNOWN

Stop directional haptic commands.

Dashboard:
"Localization uncertain"

User instruction:
"Move toward a marked landmark"
or
"Scan QR landmark"
```

Last-known position should have a timeout and should not be treated as current indefinitely.

# 17. Indoor Map

Represent the building as a graph.

Example:

```text
B1 Entrance
 |
B2 Corridor
 |  |  B4 Staircase
 |
B3 Computer Lab
 |
B5 Library
```

`indoor_map.json`

```json
{
  "nodes": ["B1", "B2", "B3", "B4", "B5"],
  "edges": [
    ["B1", "B2"],
    ["B2", "B3"],
    ["B2", "B4"],
    ["B4", "B5"]
  ]
}
```

For a small hackathon map, BFS is sufficient when all connections have equal cost.

# 18. Navigation Integration

Example:

```text
Current = B3
Destination = B5

Route:
B3 → B2 → B4 → B5
```

The navigation layer converts the route into high-level instructions:

```text
LEFT
RIGHT
FORWARD
ARRIVED
STOP
UNKNOWN
```

The exact directional mapping depends on the physical layout and user orientation.

# 19. Haptic Command Mapping

Suggested starting language:

| Command | Left motor | Right motor |
|---|---|---|
| LEFT | Strong | Off |
| RIGHT | Off | Strong |
| FORWARD | Both | Both |
| ARRIVED | Both short pulse | Both short pulse |
| WARNING | Alternating | Alternating |
| UNKNOWN | Double short pulse | Double short pulse |
| STOP | Off | Off |

These patterns are design choices. Test that they are distinguishable and comfortable.

# 20. Wi-Fi Communication

Prefer high-level commands rather than sending raw PWM continuously.

```text
Laptop / Navigation
       |
       v
LEFT / RIGHT / FORWARD / STOP
       |
      Wi-Fi
       |
       v
ESP32
       |
       v
PWM motor pattern
```

Example Python:

```python
import requests

ESP32_IP = "192.168.1.100"

requests.get(f"http://{ESP32_IP}/left")
requests.get(f"http://{ESP32_IP}/right")
requests.get(f"http://{ESP32_IP}/forward")
requests.get(f"http://{ESP32_IP}/stop")
```

The actual ESP32 IP should come from the ESP32 Serial Monitor/network configuration. Do not assume `192.168.4.1` unless the ESP32 is configured as an access point.

# 21. ESP32 HTTP Server

Example structure:

```cpp
#include <WiFi.h>
#include <WebServer.h>

const char* ssid = "YOUR_WIFI";
const char* password = "YOUR_PASSWORD";

WebServer server(80);

const int MOTOR_LEFT = 25;
const int MOTOR_RIGHT = 26;

const int PWM_FREQ = 5000;
const int PWM_RESOLUTION = 8;

const int VIB_OFF = 0;
const int VIB_HIGH = 255;

void setMotors(int left, int right) {
  ledcWrite(MOTOR_LEFT, left);
  ledcWrite(MOTOR_RIGHT, right);
}

void stopMotors() {
  setMotors(VIB_OFF, VIB_OFF);
}

void leftCommand() {
  setMotors(VIB_HIGH, VIB_OFF);
  server.send(200, "text/plain", "LEFT");
}

void rightCommand() {
  setMotors(VIB_OFF, VIB_HIGH);
  server.send(200, "text/plain", "RIGHT");
}

void forwardCommand() {
  setMotors(VIB_HIGH, VIB_HIGH);
  server.send(200, "text/plain", "FORWARD");
}

void stopCommand() {
  stopMotors();
  server.send(200, "text/plain", "STOP");
}

void setup() {
  Serial.begin(115200);

  ledcAttach(MOTOR_LEFT, PWM_FREQ, PWM_RESOLUTION);
  ledcAttach(MOTOR_RIGHT, PWM_FREQ, PWM_RESOLUTION);

  stopMotors();

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println(WiFi.localIP());

  server.on("/left", leftCommand);
  server.on("/right", rightCommand);
  server.on("/forward", forwardCommand);
  server.on("/stop", stopCommand);

  server.begin();
}

void loop() {
  server.handleClient();
}
```

# 22. ESP32 Command Timeout

The wearable should not keep vibrating forever if communication stops.

Recommended logic:

```text
lastCommandTime = current time

if current time - lastCommandTime > 2000 ms:
    stopMotors()
```

This should be included in the final firmware.

# 23. Software Structure

Recommended project structure:

```text
project/
│
├── backend/
│   ├── app.py
│   ├── localization/
│   │   ├── gps.py
│   │   ├── visual.py
│   │   ├── ble.py
│   │   ├── qr.py
│   │   └── manager.py
│   │
│   ├── navigation/
│   │   ├── map.py
│   │   ├── router.py
│   │   └── instructions.py
│   │
│   └── communication/
│       └── esp32.py
│
├── esp32/
│   ├── esp32_navigation.ino
│   └── ble_scanner/
│       └── ble_scanner.ino
│
├── config/
│   ├── landmarks.json
│   └── indoor_map.json
│
└── dashboard/
```

# 24. Dashboard

Show:

```text
---------------------------------------
        INDOOR NAVIGATION
---------------------------------------

Current Location:
Computer Lab

Source:
BLE Landmark B3

Floor:
Ground Floor

Confidence:
82% HIGH

Destination:
Library

Next Action:
RIGHT

GPS:
Unavailable

BLE:
Connected

QR:
Standby

ESP32:
Connected
---------------------------------------
```

When confidence is low:

```text
---------------------------------------
      LOCALIZATION UNCERTAIN
---------------------------------------

Current Location:
Unknown

Confidence:
28% LOW

Action:
Scan nearby QR landmark

Navigation:
PAUSED

Haptic:
UNKNOWN pattern
---------------------------------------
```

# 25. Judge Test Setup

Prepare five visible test locations:

```text
B1 → Main Entrance
B2 → Central Corridor
B3 → Computer Lab
B4 → Staircase
B5 → Library
```

At each location:

1. Stand near the landmark.
2. Wait for BLE detection.
3. Verify the dashboard location.
4. Verify confidence.
5. Select a destination.
6. Verify the route.
7. Verify haptic feedback.

# 26. Required Demonstrations

## Test 1 — Normal localization

```text
B1 → B3
```

Expected:

```text
Current = B1
Route = B1 → B2 → B3
```

## Test 2 — GPS/visual loss

```text
GPS/visual confidence drops
        ↓
BLE activates
        ↓
B2 detected
        ↓
Indoor navigation resumes
```

## Test 3 — BLE recovery

At B3:

```text
Stable B3 detection
        ↓
Current = Computer Lab
        ↓
Route recalculated
```

## Test 4 — BLE confidence drop

```text
BLE confidence ↓
        ↓
Navigation pauses
        ↓
UNKNOWN haptic pattern
        ↓
Dashboard asks for recovery
```

## Test 5 — QR recovery

```text
Scan B4 QR
        ↓
Current = Staircase
        ↓
Confidence restored
        ↓
Navigation resumes
```

# 27. Failure Handling

### BLE unavailable

```text
BLE unavailable
    ↓
Try QR
    ↓
If unavailable
    ↓
UNKNOWN
```

### Wi-Fi unavailable

```text
Wi-Fi lost
    ↓
Stop new haptic commands
    ↓
Show communication error
```

### ESP32 disconnected

```text
ESP32 unreachable
    ↓
Dashboard:
"Haptic device disconnected"
```

Do not keep sending stale navigation commands indefinitely.

# 28. Development Order

## Phase 1 — Hardware

- [ ] ESP32 USB upload works
- [ ] External LED works
- [ ] Left motor driver works
- [ ] Right motor driver works
- [ ] Diodes installed
- [ ] Common GND verified
- [ ] PWM test completed

## Phase 2 — ESP32 Networking

- [ ] ESP32 connects to Wi-Fi
- [ ] ESP32 prints IP
- [ ] `/left` works
- [ ] `/right` works
- [ ] `/forward` works
- [ ] `/stop` works
- [ ] Timeout implemented

## Phase 3 — BLE

- [ ] B1 beacon
- [ ] B2 beacon
- [ ] B3 beacon
- [ ] B4 beacon
- [ ] B5 beacon
- [ ] Scanner detects IDs
- [ ] RSSI recorded
- [ ] Stability filter implemented

## Phase 4 — Localization

- [ ] Landmark database
- [ ] Confidence calculation
- [ ] Localization manager
- [ ] Source switching
- [ ] UNKNOWN state
- [ ] Last-known timeout

## Phase 5 — Navigation

- [ ] Indoor map
- [ ] Route calculation
- [ ] Destination selection
- [ ] Next-action calculation
- [ ] Haptic command generation

## Phase 6 — QR

- [ ] QR B1
- [ ] QR B2
- [ ] QR B3
- [ ] QR B4
- [ ] QR B5
- [ ] QR recovery flow

## Phase 7 — Dashboard

- [ ] Current position
- [ ] Localization source
- [ ] Confidence
- [ ] Destination
- [ ] Next instruction
- [ ] GPS status
- [ ] BLE status
- [ ] QR status
- [ ] ESP32 status

## Phase 8 — Final testing

- [ ] Test every landmark
- [ ] Test GPS/visual loss
- [ ] Test BLE loss
- [ ] Test QR recovery
- [ ] Test Wi-Fi loss
- [ ] Test ESP32 disconnect
- [ ] Test motor timeout
- [ ] Test multiple destinations

# 29. Recommended MVP

If implementation time is limited, build:

```text
4 BLE landmarks
      ↓
Strongest/stable landmark
      ↓
Indoor zone
      ↓
Indoor graph
      ↓
Destination
      ↓
LEFT / RIGHT / FORWARD
      ↓
Wi-Fi
      ↓
ESP32
      ↓
Two vibration motors
```

Then add:

```text
BLE confidence LOW
      ↓
QR recovery
```

This demonstrates the core challenge without requiring centimeter-level indoor positioning.

# 30. Final Demo Script

1. Start outside the building.
2. Use normal GPS/visual localization.
3. Enter the indoor area.
4. Show GPS/visual confidence dropping.
5. Localization Manager switches to BLE.
6. A predefined landmark is detected.
7. Indoor position is recovered.
8. Destination route is recalculated.
9. Navigation commands are sent to ESP32.
10. ESP32 produces haptic feedback.
11. Move away from landmarks.
12. BLE confidence drops.
13. System stops giving potentially misleading directions.
14. Dashboard shows LOW/UNKNOWN.
15. Scan a QR landmark.
16. Position is recovered.
17. Navigation resumes.

# 31. Challenge Requirement Mapping

| Requirement | Implementation |
|---|---|
| Reasonable indoor position | BLE landmark-based zone recovery |
| Predefined landmarks | B1–B5 |
| Identify landmarks | BLE IDs |
| Indoor navigation | Graph-based routing |
| GPS/visual failure | Localization confidence manager |
| Fallback | BLE → QR → safe UNKNOWN |
| Low-confidence communication | Dashboard + haptic warning |
| Multiple test points | B1–B5 |
| Destination integration | Indoor route feeds navigation |
| Wearable feedback | ESP32 + GPIO25/GPIO26 motors |

# 32. Engineering Rules

1. Never drive vibration motors directly from ESP32 GPIOs.
2. Use transistor drivers.
3. Keep the flyback diode across each motor.
4. Keep all grounds common.
5. Do not connect a LiPo directly to ESP32 3V3.
6. Do not intentionally short 3V3 and GND.
7. Use the Arduino-ESP32 3.x LEDC API used by the installed core.
8. Do not trust one noisy BLE reading.
9. Do not claim precise positioning from uncalibrated RSSI.
10. Do not issue directional navigation when localization confidence is too low.
11. Do not let stale commands keep motors running.
12. Insulate solder joints.
13. Protect the LiPo from puncture, crushing, overheating, and short circuits.
14. Do not wear the device while charging.
15. Verify the exact ESP32 board power-input arrangement before battery operation.

# 33. Final Architecture

```text
                 +----------------------+
                 | GPS / Visual System  |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Localization Manager |
                 +----------+-----------+
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
          GPS/Visual       BLE             QR
             |              |              |
             +--------------+--------------+
                            |
                            v
                 +----------------------+
                 | Indoor Position      |
                 | + Confidence         |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Indoor Map / Router  |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Navigation Command   |
                 | LEFT/RIGHT/FORWARD   |
                 | STOP/UNKNOWN         |
                 +----------+-----------+
                            |
                          Wi-Fi
                            |
                            v
                 +----------------------+
                 | ESP32 Wearable       |
                 +---------+------------+
                           | 
                     +-----+-----+
                     |           |
                  GPIO25      GPIO26
                     |           |
                     v           v
                   LEFT        RIGHT
                   MOTOR       MOTOR
```

# 34. Completion Criteria

The system is ready for the demo when:

- [ ] ESP32 reliably receives commands.
- [ ] Both motors work independently.
- [ ] LEFT and RIGHT are distinguishable.
- [ ] BLE landmarks are detected.
- [ ] Indoor zones are correctly recovered at predefined points.
- [ ] Confidence changes with localization quality.
- [ ] Navigation switches to indoor localization.
- [ ] Indoor routes are calculated.
- [ ] Haptic commands follow the route.
- [ ] Low confidence prevents misleading navigation.
- [ ] QR recovery works if included.
- [ ] Dashboard shows source and confidence.
- [ ] Temporary GPS/BLE/communication failures do not crash the system.
