# CampusEcho — ESP32 Haptic Wristband Hardware Setup Guide

This guide describes how to assemble, flash, pair, and operate the **ESP32 Haptic Wristband** with the CampusEcho navigation software.

---

## 1. Hardware Bill of Materials (BOM)

| Component | Quantity | Specification / Notes |
|---|---|---|
| **Microcontroller** | 1 | ESP32-WROOM-32 DevKitC (or compatible ESP32 board) |
| **Vibration Motors** | 2 | 3V Coin ERM (Eccentric Rotating Mass) vibration motors |
| **Transistors** | 2 | 2N2222 or BC547 NPN BJT (low-side PWM switches) |
| **Base Resistors** | 2 | 1 kΩ (limits base current from ESP32 GPIO) |
| **Flyback Diodes** | 2 | 1N4148 or 1N4001 (clamps motor inductive voltage spikes) |
| **Power Source** | 1 | 3.7V LiPo battery with 5V boost, or USB power bank |
| **Wristband Strap** | 1 | Velcro / silicone wearable wrist strap |

---

## 2. Circuit Schematic & Pinout

```text
               +3.3V or +5V Motor Rail
                      │
           ┌──────────┴──────────┐
           │                     │
        [Motor L]             [Motor R]
       (Left Wrist)         (Right Wrist)
           │                     │
           ├───[|>| Diode]───────┤   (Cathodes to +V, Anodes to Collector)
           │                     │
       Collector             Collector
      ┌────┴────┐           ┌────┴────┐
GPIO25┤ 2N2222  │    GPIO26┤ 2N2222  │
 ──[1k]──┤  NPN    │    ──[1k]──┤  NPN    │
      └────┬────┘           └────┬────┘
        Emitter               Emitter
           │                     │
           └──────────┬──────────┘
                      │
                     GND (ESP32 Common Ground)
```

- **Left Motor Control**: `GPIO 25` $\rightarrow$ `1 kΩ` $\rightarrow$ Base of Left Transistor
- **Right Motor Control**: `GPIO 26` $\rightarrow$ `1 kΩ` $\rightarrow$ Base of Right Transistor
- **Ground**: All grounds must be tied together.
- **PWM Frequency**: Configured in firmware at `5 kHz` (avoids audible motor coil whine and provides smooth duty cycle mapping).

---

## 3. Firmware Flashing (`campusecho_haptic_wristband.ino`)

The firmware sketch is located at:
[`campusecho_haptic_wristband.ino`](file:///d:/CampusEchoTemp2/campusecho_haptic_wristband.ino)

### Step-by-Step Upload in Arduino IDE:
1. **Install ESP32 Board Package**:
   - Go to `File` $\rightarrow$ `Preferences`.
   - Add to *Additional Board Manager URLs*:
     `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
   - Open `Tools` $\rightarrow$ `Board` $\rightarrow$ `Boards Manager...`, search for `esp32` by Espressif Systems, and install version **3.x** (or latest).
2. **Select Board & Port**:
   - `Tools` $\rightarrow$ `Board` $\rightarrow$ `esp32` $\rightarrow$ `ESP32 Dev Module` (or your specific ESP32 board).
   - `Tools` $\rightarrow$ `Partition Scheme` $\rightarrow$ `Default 4MB with spiffs (1.2MB APP / 1.5MB SPIFFS)` or `Huge APP (3MB No OTA / 1MB SPIFFS)`.
   - Ensure Bluetooth is enabled.
   - Connect ESP32 via USB and select the COM port in `Tools` $\rightarrow$ `Port`.
3. **Upload**:
   - Click **Upload** (or press `Ctrl+U`).
   - Once uploaded, open `Tools` $\rightarrow$ `Serial Monitor` at `115200 baud`.
   - You should see:
     ```text
     CampusEcho haptic wristband ready. Pair via Bluetooth as 'CampusEcho-Wristband'.
     ```

---

## 4. Windows Bluetooth Classic Pairing

1. On your Windows PC, open **Settings** $\rightarrow$ **Bluetooth & devices**.
2. Turn **Bluetooth** ON and click **Add device**.
3. Choose **Bluetooth** (mice, keyboards, audio, etc.).
4. Select **`CampusEcho-Wristband`**.
5. Once paired, Windows will automatically configure a **Standard Serial over Bluetooth link (SPP)**.
6. Open **Device Manager** $\rightarrow$ expand **Ports (COM & LPT)**.
7. Note the assigned COM port (e.g. `COM4` or `COM5`). This is the virtual serial port used by CampusEcho.

---

## 5. Connecting with CampusEcho Software

### Option A: Mission Control Dashboard (Interactive Web UI)
1. Start the system:
   ```powershell
   .\.venv\Scripts\python.exe start.py
   ```
2. Open the dashboard at `http://127.0.0.1:8000/dashboard`.
3. Look at the **Hardware Wristband** panel beneath the Haptic Simulator:
   - Click **↻ Scan** to populate the COM port list.
   - Select your port (e.g. `COM5`).
   - Click **Connect**.
   - The badge will switch from **ESP32 Offline** to 🟢 **ESP32 (COM5)**.
4. Click **Test Left**, **Test Right**, or **Test Hazard** to verify physical motor vibration instantly!

### Option B: Automatic Startup via CLI
```powershell
# Specify the COM port directly:
.\.venv\Scripts\python.exe start.py --haptic-port COM5

# Or auto-detect:
.\.venv\Scripts\python.exe start.py --haptic-port auto
```

---

## 6. Command Protocol & Safety Watchdog

The firmware uses newline-terminated CSV format:
```text
<side>,<intensity 0-9>,<pattern 0-3>\n
```

- **Side**: `L` (Left), `R` (Right), `B` (Both), `O` (Off)
- **Intensity**: `0` (off) to `9` (maximum PWM duty)
- **Pattern**:
  - `0`: Continuous vibration
  - `1`: Slow pulse (500ms on / 500ms off) — informational / straight path
  - `2`: Rapid pulse (150ms on / 100ms off) — urgent action / hazard alert
  - `3`: Double-pulse + pause (120ms on, 100ms off, 120ms on, 600ms off) — turns & critical stop

### Safety Failsafe Watchdog:
The ESP32 firmware enforces `FAILSAFE_TIMEOUT_MS = 3000` (3.0 seconds). If Bluetooth disconnects or the host application terminates unexpectedly, both vibration motors automatically shut off after 3 seconds, preventing battery drain or unwanted sustained vibrations.
