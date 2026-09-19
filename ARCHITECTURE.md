# CampusEcho System Architecture & Data Flow

This document details the complete end-to-end architecture of **CampusEcho**, integrating the 4-stage pipeline, the 3-tier confidence policy, the dynamic decaying memory model, and the real-time shared obstacle database.

---

## 1. End-to-End System Architecture Diagram

```mermaid
flowchart TD
    %% STAGE 1: PRE-FED DATA
    subgraph Stage1["Stage 1: Pre-Fed Campus Knowledge"]
        MapGraph["Campus Map Graph<br/>(Nodes, Edges, Distances)"]
        LandmarkPhotos["Landmark Signage Database<br/>(Photos, Room Labels, Regex)"]
    end

    %% STAGE 2: PERCEPTION LOOP
    subgraph Stage2["Stage 2: Real-Time Perception Loop (1.5s Interval)"]
        CamFrame["Video Camera Frame<br/>(Webcam or Simulated Video)"]
        YOLO["YOLOv8n Obstacle Detector<br/>(Bounding Box, Class, Conf)"]
        DistEst["Distance Estimator<br/>(Pinhole / Bounding-box Height)"]
        EasyOCR["EasyOCR Reader<br/>(Signage Text Extraction)"]
        LaneCheck{"Obstacle in<br/>Walking Lane?<br/>(Center-third corridor & dist < 3.5m)"}
        LandmarkMatch["Landmark Matcher<br/>(Fuzzy Match -> Node Update)"]
    end

    %% STAGE 3: DECISION & MEMORY LAYER
    subgraph Stage3["Stage 3: Decision Engine & Decaying Memory"]
        ConfidenceCheck{"Confidence<br/>Level?"}
        Tier1["Tier 1: BLOCKED (> 0.70)<br/>Dijkstra Reroute + Local Memory"]
        Tier2["Tier 2: HEDGE (0.40 - 0.70)<br/>Caution Warning Issued"]
        Tier3["Tier 3: ESCALATE (< 0.40)<br/>Human Assistance Requested"]
        DijkstraRouter["Dynamic Dijkstra Router<br/>(Graph + Active Edge Penalties)"]
        DecayMemory["Local Decaying Memory Store<br/>W(t) = C * exp(-dt / tau)"]
    end

    %% SHARED OBSTACLE DATABASE
    subgraph SharedDB["Shared Obstacle Database (Multi-User Sync)"]
        SQLiteDB[("SQLite WAL Database<br/>(Obstacles, Nodes, Penalties)")]
        DedupWorker["Deduplication & Merge Engine<br/>(Spatial radius <= 2.0m + same class)"]
        DecayWorker["Background Decay & TTL Worker<br/>(Active -> Stale -> Cleared)"]
        WSBroadcaster["FastAPI WebSocket Hub<br/>(Real-time State Broadcast)"]
    end

    %% STAGE 4: USER NOTIFICATION MATRIX & OUTPUTS
    subgraph Stage4["Stage 4: Dual-Mode User Notification Matrix"]
        ModeRouter{"Mode Router<br/>(Voice / Haptic / Both)"}
        VoiceModule["Voice Audio Guidance<br/>(Web Speech API TTS)"]
        HapticEncoder["Haptic Encoder<br/>(Protocol: L7P2, R5P1, B9P3)"]
        WebHapticSim["Web Haptic Visual/Audio Simulator<br/>(Stereo Panning + Pulse Rings)"]
        ESP32Hardware["ESP32 Behind-Ear / Wristband<br/>(Bluetooth Classic SPP / PWM)"]
        CaregiverDash["Caregiver Mission Control<br/>(Live Map, Video Overlay, Logs, Alerts)"]
    end

    %% DATA FLOW CONNECTIONS
    MapGraph --> DijkstraRouter
    LandmarkPhotos --> LandmarkMatch

    CamFrame --> YOLO
    CamFrame --> EasyOCR

    YOLO --> DistEst
    DistEst --> LaneCheck

    EasyOCR --> LandmarkMatch
    LandmarkMatch -->|"Current Node Confirmed"| DijkstraRouter

    LaneCheck -->|"No"| PathClear["Path Clear<br/>Continue Guidance"]
    PathClear --> ModeRouter

    LaneCheck -->|"Yes"| ConfidenceCheck

    ConfidenceCheck -->|"> 0.70"| Tier1
    ConfidenceCheck -->|"0.40 - 0.70"| Tier2
    ConfidenceCheck -->|"< 0.40"| Tier3

    Tier1 --> DecayMemory
    Tier1 -->|"Report Obstacle"| DedupWorker
    Tier1 --> DijkstraRouter

    Tier2 -->|"Log Event / Spoken Hedge"| ModeRouter
    Tier3 -->|"Push Escalation Event"| CaregiverDash

    DedupWorker --> SQLiteDB
    DecayWorker <--> SQLiteDB
    SQLiteDB --> WSBroadcaster

    WSBroadcaster -->|"Sync Edge Penalties"| DijkstraRouter
    WSBroadcaster -->|"Live Telemetry & Pins"| CaregiverDash

    DijkstraRouter -->|"Turn / Reroute Action"| ModeRouter

    ModeRouter -->|"Voice / Both"| VoiceModule
    ModeRouter -->|"Haptic / Both"| HapticEncoder

    HapticEncoder --> WebHapticSim
    HapticEncoder -.->|"Optional Bluetooth"| ESP32Hardware

    Tier3 -.->|"Alert Tone & Modal"| ModeRouter
```

---

## 2. Event-Driven Reaction Flow (Sequence Diagram)

```mermaid
sequenceDiagram
    autonumber
    actor User as Visually Impaired Student
    participant Cam as Video Capture (1.5s)
    participant Perc as Perception Engine (YOLO + EasyOCR)
    participant Dec as Decision Engine (3-Tier Policy)
    participant SDB as Shared Obstacle DB (SQLite + WS)
    participant Route as Dijkstra Router
    participant Mode as Mode Router
    participant Voice as Voice TTS (Web Speech)
    participant Haptic as Haptic Actuators (ESP32 / Sim)
    participant Dash as Caregiver Dashboard

    Note over User,Dash: Navigation Active (Walking from Main Gate to Seminar Hall)
    Cam->>Perc: Frame captured (t = 1.5s)
    Perc->>Perc: YOLOv8n detects Chair (Conf: 0.88, Box: [210, 180, 420, 510])
    Perc->>Perc: Distance = 2.1m (in walking corridor)
    Perc->>Dec: ObstacleEvent(type="chair", conf=0.88, dist=2.1m, lane=True)

    rect rgb(255, 230, 230)
        Note over Dec,SDB: Tier 1 Triggered (Confidence 0.88 > 0.70 BLOCKED)
        Dec->>SDB: upsert_obstacle(type="chair", edge="corridor_a->seminar_hall", conf=0.88)
        SDB->>SDB: Merge nearby reports, set penalty_weight = 100.0, status="active"
        SDB-->>Route: Edge penalized ("corridor_a->seminar_hall")
        SDB-->>Dash: WS broadcast: NEW_OBSTACLE (Pin on map, Reasoning log)
        Dec->>Route: recalculate_route(current="corridor_a", dest="seminar_hall")
        Route-->>Dec: New Route: ["corridor_a", "courtyard_path", "seminar_hall"]
    end

    Dec->>Mode: RouteAction(status="REROUTED", hazard="chair", side="both", urgency="HIGH")

    alt Mode is Voice Only or Both
        Mode->>Voice: speak("Obstacle ahead. Rerouting via Courtyard Path.")
        Voice-->>User: Spoken guidance
    end

    alt Mode is Haptic Only or Both
        Mode->>Haptic: emit_command("B9P3") [Both motors, 9/9 duty, emergency pulse]
        Haptic-->>User: Physical vibration alert
    end

    Mode->>Dash: Telemetry update (Breadcrumb, Mode, Active Route)
```

---

## 3. Shared Obstacle Database Specifications

### 3.1 SQLite Schema (`obstacles`)
```sql
CREATE TABLE IF NOT EXISTS obstacles (
    id TEXT PRIMARY KEY,               -- e.g. "obs_corr_a_chair_001"
    obstacle_type TEXT NOT NULL,       -- "chair", "trash_can", "person", "wet_floor", "closed_door"
    edge_id TEXT NOT NULL,             -- e.g. "corridor_a_to_seminar_hall"
    offset_m REAL NOT NULL,            -- distance along edge in meters (e.g. 12.5)
    confidence REAL NOT NULL,          -- current decayed confidence [0.0 - 1.0]
    initial_confidence REAL NOT NULL,  -- original detection confidence
    distance_m REAL NOT NULL,          -- estimated distance when reported
    first_seen TIMESTAMP NOT NULL,     -- first detected timestamp
    last_seen TIMESTAMP NOT NULL,      -- most recent confirmation timestamp
    times_confirmed INTEGER DEFAULT 1, -- confirmation count across sessions
    reporter_id TEXT NOT NULL,         -- session/user ID
    status TEXT NOT NULL,              -- "active", "stale", "cleared"
    ttl_seconds INTEGER DEFAULT 300    -- time-to-live before expiration
);
```

### 3.2 Decay & Penalty Mathematical Model
1. **Confidence Decay Formula:**
   $$\text{confidence}(t) = \text{initial\_confidence} \times e^{-\frac{t - t_{\text{last\_seen}}}{\tau}}$$
   *Where $\tau = \frac{\text{half\_life}}{\ln(2)}$ (half-life configured to 180 seconds for demo).*
2. **Dijkstra Dynamic Edge Weight:**
   $$\text{EffectiveWeight}(e) = \text{BaseDistance}(e) + \sum_{o \in \text{obstacles}(e)} \left( \text{PenaltyMultiplier} \times \text{confidence}_o(t) \right)$$
   *If $\text{status} = \text{"active"}$, $\text{PenaltyMultiplier} = 150.0$ (effectively blocks the path unless no alternative exists).*
   *If $\text{status} = \text{"stale"}$ ($0.30 \le \text{confidence} < 0.60$), $\text{PenaltyMultiplier} = 30.0$ (path allowed if necessary, triggering a HEDGE warning).*
   *If $\text{confidence} < 0.30$, status is marked `"cleared"` and penalty drops to 0.*

### 3.3 Spatial Deduplication & Confirmation Rule
- When a new detection is reported on edge $e$ with obstacle type $T$ at offset $x$:
  - Query existing active/stale obstacles on edge $e$ matching type $T$.
  - If $|x_{\text{existing}} - x_{\text{new}}| \le 2.0\text{ meters}$:
    - **Merge & Refresh:** Update $t_{\text{last\_seen}} = \text{now}$, increment $\text{times\_confirmed} += 1$, set $\text{confidence} = \min(1.0, \text{confidence} + 0.15)$, set $\text{status} = \text{"active"}$.
  - If no match within 2.0m:
    - **Insert** new obstacle record.

---

## 4. Component Event-Response Matrix

| Triggering Event | Processing Component | Action Taken | Output Generated |
|---|---|---|---|
| **Webcam frame received (every 1.5s)** | YOLOv8n + Distance Estimator | Detects objects, computes bounding-box center and relative distance. | Array of `DetectedObstacle` objects. |
| **Obstacle detected in walking corridor with Conf > 0.70** | Decision Engine (Tier 1) | Upserts hazard into Shared DB, marks edge penalty, triggers Dijkstra replan. | Voice: *"Obstacle ahead. Rerouting."*<br/>Haptic: `B9P3`<br/>Dashboard: Red hazard pin + route update. |
| **Obstacle detected with Conf 0.40 – 0.70** | Decision Engine (Tier 2) | Logs hazard as unconfirmed, does NOT reroute. | Voice: *"Caution, possible obstacle ahead."*<br/>Haptic: Single warning pulse (`B5P1`). |
| **Ambiguous feature detected with Conf < 0.40 in hazard zone** | Decision Engine (Tier 3) | Freezes guidance, alerts bystanders, pushes escalation ticket to dashboard. | Voice: *"Uncertain path ahead. Requesting assistance."*<br/>Dashboard: Escalation Modal with camera frame snapshot. |
| **Signage text detected by EasyOCR** | Landmark Matcher | Fuzzy matches recognized text against known campus graph labels. | Position update: *"Arrived at Corridor A."*<br/>Recalibrates current graph node. |
| **User passes location without re-detecting obstacle** | Perception + Decision Engine | Emits `CLEAR_CONFIRMATION` event to Shared DB. | DB reduces confidence by 0.25; if $< 0.30$, marks `cleared`. |
| **Mode Toggle changed (Voice $\rightarrow$ Haptic $\rightarrow$ Both)** | Mode Router | Adjusts active channel routing without restarting navigation. | Confirmation tone/pulse; routes guidance to selected outputs. |
