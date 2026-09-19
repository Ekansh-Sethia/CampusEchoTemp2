# CampusEcho: Implementation Plan

**CampusEcho** is an explainable, memory-driven, dual-mode accessible campus navigation assistant designed for visually impaired students. It integrates real-time computer vision (YOLOv8n + EasyOCR), a 3-tier confidence decision policy, a decaying hazard memory model, a shared multi-user obstacle database, and dual-mode outputs (Voice TTS + Haptic feedback + Caregiver Mission Control Dashboard).

---

## 1. Project Goals & Scope

### 1.1 Goals
- Empower visually impaired students to navigate unfamiliar campus environments safely and independently.
- Bridge the sensory gap with a **"one brain, two mouths"** architecture: simultaneous or switchable voice guidance and ears-free directional haptic feedback.
- Eliminate static navigation failures through a **dynamic decaying obstacle memory** and a **real-time shared obstacle database** that learns building changes from multiple users.
- Provide institutional trust and explainability via a **3-tier confidence policy** (Act, Hedge, Escalate) and an auditable **post-walk decision replay report**.

### 1.2 Scope: Must-Have vs. Nice-to-Have (Hackathon Scope)

| Capability | Must-Have (Hackathon 24h Build) | Nice-to-Have (Post-Hackathon / Roadmap) |
|---|---|---|
| **Campus Graph & Routing** | 5–8 waypoint campus graph (JSON), Dijkstra shortest path with dynamic edge weight penalties for active obstacles. | Full-campus 100+ node graph with automatic floor transitions and elevator logic. |
| **Perception Loop** | 1.5s frame capture, YOLOv8n object detection on CPU, monocular bounding-box distance estimation, walking lane corridor check. | Stereoscopic depth camera (e.g., Intel RealSense / OAK-D) or LiDAR point cloud processing. |
| **Landmark Localization** | EasyOCR text recognition on keyframes matching signage text (e.g., "ATC BUILDING", "ROOM 101") with fuzzy matching. | Visual feature SLAM / point-cloud matching / BLE beacon fusion. |
| **Confidence Policy & Memory** | 3 tiers (>0.70 BLOCKED $\rightarrow$ Dijkstra reroute + log memory; 0.40–0.70 HEDGE $\rightarrow$ caution warning; <0.40 ESCALATE $\rightarrow$ human help trigger). Exponential time decay model. | Deep reinforcement learning for predictive obstacle trajectories. |
| **Shared Obstacle Database** | SQLite (WAL mode) + FastAPI WebSocket broadcast for multi-user obstacle sync, spatial deduplication, decay pruning, and dynamic edge penalties. | Distributed Cloud Postgres/PostGIS or Firebase with global geo-sharding. |
| **Dual-Mode Output** | Web Speech API TTS + Haptic byte protocol (`L7P2`) with interactive Web Haptic Simulator + optional ESP32 Bluetooth Classic SPP integration. | Custom molded binaural headband with DRV2605L haptic driver ICs. |
| **Caregiver / Operator UI** | Live Mission Control Dashboard: video feed with bounding boxes, real-time reasoning trail, decaying hazard map, escalation alert modal, and post-walk replay report. | Native iOS/Android mobile apps with cellular video streaming. |

---

## 2. Technology Stack & Trade-Off Decisions

| Component | Selected Technology | Alternatives Considered | Why This One (Hackathon Trade-off) |
|---|---|---|---|
| **Backend Framework** | **FastAPI (Python 3.10+)** | Flask, Node.js / Express | Native async, high-throughput WebSockets for real-time telemetry, auto OpenAPI docs, direct interop with Python AI/CV libraries. |
| **Object Detection** | **YOLOv8n (Ultralytics)** | YOLOv11, MediaPipe, DETR | Smallest footprint (~3M parameters, ~6MB weights), runs fast on CPU (~15–30 FPS on laptops) with zero GPU requirement. |
| **Text Recognition (OCR)** | **EasyOCR (PyTorch)** | Tesseract OCR, Google Cloud Vision API | Better accuracy on natural campus signage under varied angles than Tesseract; 100% free and local-first (unlike Cloud Vision). |
| **Graph & Routing** | **NetworkX + Custom Dijkstra** | pgRouting, OSRM, GraphHopper | Zero external server dependencies; Python in-memory representation allows instant dynamic edge weight manipulation and penalty updates. |
| **Shared Obstacle DB** | **SQLite (WAL mode) + FastAPI WebSockets** | Firebase, PostgreSQL, Redis | Zero configuration, zero external service setup, file-based ACID compliance, sub-millisecond local queries, works 100% offline at the venue. |
| **Frontend / Dashboard** | **Vanilla HTML5 / CSS3 / ES Modules** | React / Next.js, Streamlit | Zero npm build step fragility on team machines, blazing fast loading, full control over Web Audio/Speech APIs and canvas map rendering. |
| **Voice Output (TTS)** | **Web Speech Synthesis API** | ElevenLabs, Google TTS, pyttsx3 | Free, zero latency, client-side, runs directly in modern browsers without API keys or bandwidth bottlenecks. |
| **Haptic Layer** | **Protocol `L{int}P{pat}` + Web Simulator + ESP32 SPP** | Native Bluetooth only | Guarantees 100% working demo even if hardware fails or Bluetooth drops; hardware connects seamlessly if present. |

---

## 3. Implementation Phases & Exit Criteria

### Phase 1: Project Setup, Campus Map Graph & Dijkstra Routing Engine
- **What to build:** Directory structure, virtual environment, dependencies (`requirements.txt`), sample campus graph (`campus_graph.json` with 6–8 nodes and edges), Dijkstra router with edge weights and penalty support.
- **Exit Criteria:** Unit tests prove finding shortest path between "Main Gate" and "Seminar Hall", and rerouting around a manually penalized edge.

### Phase 2: Real-Time Perception Loop (YOLOv8n + Distance + Walking Lane)
- **What to build:** Video capture worker (supporting webcam or recorded test MP4/images), YOLOv8n inference pipeline, bounding-box height-based distance estimator, and walking lane corridor filter (center-third of frame).
- **Exit Criteria:** Script processes a live or recorded video feed, detects obstacles (chairs, persons, trash cans), estimates distances within $\pm 0.5m$ accuracy, and flags whether the obstacle is in the walking lane.

### Phase 3: EasyOCR Sign Reading & Landmark Localization Engine
- **What to build:** OCR extraction pipeline targeting signage in keyframes (1.5s interval), text cleaning, fuzzy matcher against campus graph node labels (e.g., "ATC Building", "Room 101").
- **Exit Criteria:** System successfully recognizes a test image of campus signage and correctly updates the agent's current node in the navigation graph.

### Phase 4: 3-Tier Confidence Policy, Decaying Memory & Dynamic Rerouting
- **What to build:** Decision engine implementing the 3 tiers:
  - **Tier 1 (Confidence > 0.70):** BLOCKED $\rightarrow$ trigger Dijkstra replan, mark edge penalty, log hazard to local memory.
  - **Tier 2 (Confidence 0.40–0.70):** HEDGE $\rightarrow$ issue spoken caution warning, keep route, log for review.
  - **Tier 3 (Confidence < 0.40 in hazard zone):** ESCALATE $\rightarrow$ trigger bystander alert tone and push to human assistance queue.
  - Exponential decay formula: $W(t) = C \cdot e^{-\Delta t / \tau}$.
- **Exit Criteria:** Automated test simulating all 3 tiers verifies correct branch execution, route recalculation on Tier 1, and time-based decay of hazard weights.

### Phase 5: Shared Obstacle Database & Multi-User Synchronization
- **What to build:** SQLite database schema (`obstacles` table), spatial & type deduplication logic, background decay worker, FastAPI WebSocket broadcaster (`/ws/telemetry`). Edge penalty injection for Dijkstra when any user requests a route.
- **Exit Criteria:** Concurrent simulation: User 1 reports an obstacle; User 2 immediately receives updated route avoiding that edge; after simulated decay time without confirmation, obstacle status becomes stale and weight drops.

### Phase 6: Dual-Mode Notification Layer & Caregiver Mission Control
- **What to build:**
  - Mode Router (Voice Only / Haptic Only / Both Together).
  - Web Speech TTS client-side integration with concise phrasing.
  - Haptic command encoder (`L7P2`, `R5P1`, `B9P3`) + Web Haptic Visual/Audio Simulator + ESP32 serial/SPP bridge.
  - Caregiver Mission Control Dashboard: live camera stream, campus map with active hazard pins, live scrolling reasoning trail, human escalation modal, and post-walk replay report.
- **Exit Criteria:** Dashboard connects via WebSocket, renders live detections, visualizes haptic pulses, speaks turn-by-turn prompts, and generates the post-walk summary.

### Phase 7: End-to-End Integration, Staged Demo Scenarios & Polish
- **What to build:** Unified startup script, recorded fallback video dataset (clear path, chair obstacle, low-confidence case), demo runner script, slide-deck alignment.
- **Exit Criteria:** Rehearsal of the complete 90-second demo script end-to-end without errors or crashes.

---

## 4. Risk Analysis & Mitigation

| Risk | Impact | Mitigation Strategy |
|---|---|---|
| **Webcam / Lighting failure during live judging** | High | Pre-record a 1080p walking video through the test route; provide a one-click "Simulated Mode" in the dashboard. |
| **EasyOCR slow inference on CPU (>1.5s)** | Medium | Run OCR only every 1.5s or on keyframes when approaching expected landmark nodes; resize ROI to upper half of frame. |
| **Bluetooth / ESP32 disconnection on stage** | Medium | The Web Dashboard features a prominent **Web Haptic Simulator** (visual vibration rings + stereo spatial audio) so the haptic feedback is visible and audible to judges even with zero physical hardware. |
| **YOLOv8 false positives / flickering detections** | Medium | Implement temporal hysteresis/debouncing (require obstacle detection across 2 consecutive frames before triggering reroute). |
| **Judges asking: "Why not just use GPS or Google Maps?"** | High | Highlight in pitch: GPS fails completely indoors; commercial maps lack room-level indoor graphs, real-time crowd-sourced obstacle decay, and multi-tier uncertainty escalation. |

---

## 5. Live 90-Second Demo Plan

1. **0:00 – 0:20 (Setup & Voice Mode):**
   - User inputs destination: *"Take me to Seminar Hall."*
   - CampusEcho plans shortest path, speaks confirmation: *"Heading to Seminar Hall via Corridor A — 45 meters away."*
2. **0:20 – 0:45 (Obstacle Detection & Dynamic Rerouting):**
   - Camera encounters a staged obstacle (e.g., chair in walking corridor, confidence 0.88).
   - System triggers **Tier 1 (BLOCKED)**: Both motors buzz emergency pattern (`B9P3`), voice speaks: *"Obstacle detected 2 meters ahead in walking lane. Rerouting via Corridor B."*
   - Shared DB updates: User 2's map immediately shows the red hazard pin and recalculates their route with an edge penalty.
3. **0:45 – 1:05 (Mode Switching & Haptic Ears-Free Experience):**
   - Toggle to **Haptic Only Mode** via dashboard or toggle button.
   - User walks toward turn: Left motor buzzes (`L7P2`). No voice chatter. Ambient hearing remains completely open.
4. **1:05 – 1:20 (Low-Confidence Human Escalation):**
   - Camera encounters an ambiguous scenario (confidence 0.35 near steps).
   - System triggers **Tier 3 (ESCALATE)**: Spoken tone + Caregiver Mission Control dashboard pops up an immediate Escalation Alert with live frame snapshot and location.
5. **1:20 – 1:30 (Decaying Memory & Post-Walk Replay Report):**
   - Point out the hazard marker on the dashboard transitioning from red to yellow to expired.
   - Click **"End Walk"** $\rightarrow$ show the **Post-Walk Decision Replay Report** (total distance, obstacles encountered, confidence log, and replanning audit trail).
