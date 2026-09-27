# CampusEcho: Living Design Decisions Log

This document records the architectural and engineering decisions made during the development of CampusEcho. It is maintained and updated after each development phase.

---

## Template for Phase Sections

Each phase section documents:
1. **What Was Built**: Summary of components and functionality implemented.
2. **Technology & Libraries Used**: Specific packages and modules selected.
3. **Decision & Trade-offs**: Why this approach was chosen and which alternatives were rejected.
4. **Functionality & Data Flow**: What it does in plain language.
5. **Inputs & Outputs**: Exact interfaces, data formats, and schemas.
6. **Known Limitations & Future Work**: Known constraints and post-hackathon roadmap.

---

## Phase 1: Project Setup, Campus Map Graph & Dijkstra Routing Engine

- **What Was Built**:
  - Modular project architecture (`src/routing`, `src/perception`, `src/memory`, `src/notifications`, `tests`).
  - `data/campus_graph.json` configured with the user's exact college campus measurements (Golden Gate $\rightarrow$ ATC Building $\rightarrow$ Silveria Hall / Administrative Building / Plus Point).
  - `CampusGraph` class supporting node metadata, expected landmark signage, bidirectional edge traversal, and dynamic edge penalty manipulation.
  - `DijkstraRouter` engine computing optimal paths, generating turn-by-turn navigation instructions with directional prompts (straight, left, right), and dynamic obstacle rerouting.
  - Comprehensive unit test suite (`tests/test_routing.py`) verifying all routes, turn instructions, landmark queries, and dynamic obstacle rerouting.
- **Technology & Libraries Used**:
  - `networkx>=3.0` (Graph data structures and Dijkstra shortest path algorithm).
  - `pydantic>=2.0` (`BaseModel`, `Field`, `ConfigDict` for data validation).
  - `pytest>=7.0` (Automated unit testing).
- **Decision / Alternatives Considered / Why This One**:
  - *Decision:* Python NetworkX + JSON graph representation.
  - *Alternatives Considered:* External routing engines (OSRM, GraphHopper, pgRouting).
  - *Why This One:* Running Dijkstra directly in-memory via NetworkX has zero external setup or background service dependencies, executes in under 1 millisecond on a laptop, and allows instant runtime modification of edge weights when obstacles are detected or decayed.
- **Functionality & Data Flow**:
  - Reads `campus_graph.json` at startup.
  - Generates shortest path paths and converts each segment into natural spoken guidance (e.g. *"Walk straight for 58 meters."*, *"Turn left and walk 50 meters to ATC Building."*).
  - When an obstacle is reported on an edge, `add_edge_penalty` increases the edge's virtual cost, causing `recalculate_route` to find the next best path (e.g. diverting via the Plus Point courtyard connector to Silveria Hall).
- **Inputs & Outputs**:
  - *Input:* Source node ID (`str`), Destination node ID (`str`), optional blocked edge tuple `(u, v)` with penalty weight (`float`).
  - *Output:* `RouteResult` object containing `path` (`List[str]`), `total_distance_m` (`float`), `effective_weight` (`float`), `steps` (`List[NavigationStep]`), and `voice_summary` (`str`).
- **Known Limitations**:
  - Assumes a single campus plane (no multi-floor stair/elevator vertical graph transitions yet; planned for future roadmap).
  - Turn directions are currently discrete ("straight", "left", "right") rather than continuous heading angles (sufficient for corridor navigation).

---

## Phase 2: Real-Time Perception Loop (YOLOv8n + Distance Estimation + Walking Lane Check)

- **What Was Built**:
  - `src/perception/models.py`: Data structures for `DetectedObstacle` and `FramePerceptionResult`.
  - `src/perception/distance.py`: Monocular distance estimator using pinhole camera geometry and ground-plane perspective projection, plus a central walking corridor analyzer ($0.25 W \le x_c \le 0.75 W$).
  - `src/perception/hazard_heuristics.py`: Specialized computer vision detectors for environmental campus hazards:
    - `stair`: Real staircase detection based on perspective spacing compression ($dy$ decreases as steps recede), significant vertical riser face height ($\ge 14\text{px}$), sawtooth photometric normal shading between tread and riser ($|I_{\text{tread}} - I_{\text{riser}}| \ge 14$), and flanking diagonal handrail/wall stringers. **Rejects flat paver blocks and tile seams** whose spacing is constant and surface is coplanar.
    - `pothole`: Surface depression detection prioritizing **internal structural distortion / roughness entropy** ($\ge 2.0\times$ floor roughness) and jagged fractured rims. **Rejects smooth floor shadows** which have identical texture roughness to the surrounding pavement.
    - `wall`: Imminent dead-end/flat planar obstacle detection within $<1.5\text{m}$.
    - `exclusion_mask`: Masks out any detected people, chairs, or furniture so floor hazards are never placed on human bodies or clothing.
  - `src/perception/video_source.py`: Dual-mode video ingestion supporting live webcams, pre-recorded MP4 video files, and looping image sequence directories.
  - `src/perception/detector.py`: `ObstacleDetector` integrating YOLOv8n, hazard heuristics, non-blocking thread safety, 2-frame temporal debouncing (hysteresis) to eliminate flickering, and OpenCV visual HUD annotation.
  - `demo_phase2.py`: Interactive CLI and visual GUI runner for testing perception on test frames, video files, or live webcams.
  - `tests/test_perception.py`: 8 unit tests validating distance scaling, corridor containment, stairs/potholes/wall heuristics, video looping, and debouncing.
- **Technology & Libraries Used**:
  - `ultralytics>=8.4.0` (YOLOv8n nano object detector).
  - `opencv-python>=5.0.0` (Image processing, Canny edge detection, Hough lines, and HUD annotation).
  - `numpy>=2.4.0` (Vectorized geometric and statistical image operations).
  - `pydantic>=2.0` (Data validation for perception models).
- **Decision / Alternatives Considered / Why This One**:
  - *Decision:* Hybrid YOLOv8n (for objects: chairs, people, bags, tables) + OpenCV heuristic detectors (for stairs, potholes, walls) + Monocular pinhole geometry.
  - *Alternatives Considered:*
    - Training custom YOLO models on stairs/potholes (requires hours of data collection and GPU training, impossible within hackathon timeframe).
    - Monocular Deep Depth models like MiDaS/DPT (too heavy on CPU, $>350\text{ms}$ per frame).
    - Hardware LiDAR / Stereo camera (adds hardware costs and complexity).
  - *Why This One:* YOLOv8n runs at $\sim 50\text{ms}$ ($\sim 20\text{ FPS}$) on standard laptop CPUs, requires zero GPU, and the CV heuristics detect stairs and potholes instantly without extra model training.
- **Functionality & Data Flow**:
  - Camera/Video feeds frames to `ObstacleDetector.process_frame()`.
  - YOLOv8n identifies objects; `hazard_detector` identifies stairs, potholes, and walls.
  - `DistanceEstimator` calculates physical distance in meters and checks if the hazard falls in the central walking lane ($0.25 W \le x_c \le 0.75 W$ and $d \le 3.5\text{m}$).
  - A 2-frame temporal hysteresis filter ensures an obstacle persists across frames before setting it as the `primary_obstacle`, preventing noisy flickering.
- **Inputs & Outputs**:
  - *Input:* BGR video frame (`np.ndarray`).
  - *Output:* `FramePerceptionResult` containing `obstacles` (`List[DetectedObstacle]`), `primary_obstacle` (`Optional[DetectedObstacle]`), `path_clear` (`bool`), `processing_time_ms` (`float`), and `fps` (`float`).
- **Known Limitations**:
  - Monocular distance estimation relies on assumed standard object dimensions and may vary if an obstacle is unusually sized.
  - Extreme low-light or unlit environments may degrade camera visibility (handled by Tier 3 human escalation in Phase 4).

### Phase 2 Addendum: Shadow/Light False Positive Filtering Layer (Bug Fix & Architecture Enhancement)

- **The Bug & Root Cause**:
  - *Symptom 1:* Hard contrast transitions between direct sunlight and shadow on walking surfaces were being misclassified as stairs or potholes.
  - *Symptom 2:* Mottled/dappled sunlight shining through tree leaves onto shaded paths was being misclassified as stones / rubble.
  - *Root Cause:* Monocular 2D edge detectors key off sharp luminance contrast gradients. A cast shadow or sun patch produces a sharp light-to-dark transition in 2D that mimics a step riser, pothole rim, or stone outline, but completely lacks 3D physical elevation, depth disparity, and material change.
- **What Was Built (`src/perception/shadow_filter.py`)**:
  - **A. Temporal / Motion Cross-Check (`TemporalStabilityTracker`)**: Tracks candidate regions across consecutive frames ($N=8$). Fluttering/flickering light patterns caused by wind moving canopy leaves produce high intensity standard deviation ($\sigma(I) \ge 10$), boosting the shadow likelihood score. Conversely, rock-solid stability over $\ge 5$ frames confirms static physical geometry.
  - **B. Shadow-Specific Color & Texture Checks (`ShadowLightAnalyzer`)**:
    - *HSV Chromaticity Invariance:* Evaluates candidate interior vs. surrounding ground. Shadows preserve underlying surface Hue and Saturation ($|\Delta H| \le 14^\circ$, $|\Delta S| \le 26$), differing only in brightness ($V$). Real potholes/stones have different material colors or moisture.
    - *Laplacian Texture Disparity:* Shadows have identical texture roughness to the surrounding pavement ($R_{\text{tex}} \approx 1.0$). Real potholes or rubble have broken gravel, cavities, or fractured surfaces ($R_{\text{tex}} \ge 1.9\times$), guaranteeing potholes in shadow are not over-suppressed.
  - **C. Dappled Canopy Shape Signature**:
    - *Multi-Blob Clustering:* Dappled sunlight occurs in clusters ($\ge 3$ nearby bright patches within $150\text{px}$ radius).
    - *Contour Solidity Check:* Dappled light patches have low solidity ($\text{Area} / \text{ConvexHullArea} < 0.72$) due to leaf mottling; stones are compact with solidity $\ge 0.85$.
    - *Penumbra Edge Softness:* Diffused atmospheric/diffraction penumbra borders ($>4\text{px}$) vs. steep contact edges on 3D stones.
  - **D. Geometric Plausibility**: Ground plane distance calibration prevents non-ground artifacts from triggering floor hazard checks.
  - **E. Sun-Angle / Ambient Lighting Parameter**: Exposes `ambient_sun_factor` (default 1.0; 1.25 for harsh midday direct sunlight, 0.70 for overcast conditions).
  - **F. Proportional Confidence Recalibration**: Rather than a brittle binary filter, calculates continuous `shadow_likelihood` $\in [0.0, 1.0]$ and applies calibrated confidence penalties:
    $$\text{calibrated\_conf} = \text{raw\_conf} \times (1.0 - \text{penalty})$$
    Downweights questionable detections into Tier 2 (HEDGE) rather than triggering false Tier 1 BLOCKED reroutes.
- **Verification & Hard Test Cases**:
  - `frame_13_dappled_tree_shadow.jpg` (dappled sunlight) $\rightarrow$ `shadow_likelihood >= 0.70`, stone suppressed, path reported safe.
  - `frame_14_pothole_in_shadow.jpg` (pothole inside shade) $\rightarrow$ `shadow_likelihood <= 0.05`, correctly detected as pothole.
  - `frame_15_stone_in_full_sun.jpg` (stone in bright sun) $\rightarrow$ `shadow_likelihood <= 0.14`, correctly detected as stone.
- **Known Remaining Limitations**:
  - Intense specular glare on wet pavements or polished marble may require polarimetric or multi-spectral sensing in extreme conditions.

---

## Phase 3: EasyOCR Sign Reading & Landmark Localization Engine

- **What Was Built**:
  - `src/perception/text_reader.py`: `SignpostReader` wrapping EasyOCR for real-time text extraction from campus signage images. Applies Gaussian blur pre-processing, CLAHE histogram equalization for contrast enhancement in harsh outdoor lighting, and a lightweight confidence threshold gate ($\ge 0.40$) to suppress noisy low-confidence reads.
  - `src/routing/landmark_matcher.py`: `LandmarkMatcher` performing fuzzy multi-strategy matching between raw OCR text output and known campus node names / expected signpost tokens. Uses Levenshtein edit-distance similarity (threshold $\ge 0.60$) via `rapidfuzz`, plus exact substring containment matching, to tolerate OCR typos, partial reads, and rotated/partial signs.
  - `src/routing/navigator.py`: `CampusNavigator` — the stateful real-time navigation tracker. Stores `current_node_id`, `destination_node_id`, `active_route`, and `current_step_index`. Processes landmark detection events via `process_landmark_event()` to advance waypoints, detect off-route position corrections, and emit `NavigationEvent` objects with contextual voice instructions.
  - `tests/test_ocr_localization.py`: 8 unit tests covering text normalisation, exact match, fuzzy typo tolerance, substring match, route initialisation, step advancement, destination arrival, and a full EasyOCR end-to-end synthetic landmark test.
- **Technology & Libraries Used**:
  - `easyocr==1.7.2` (Multi-language scene text recognition, installed `--no-deps` to prevent `opencv-headless` from overwriting the project's `opencv-python` GUI build).
  - `rapidfuzz` (Levenshtein / Jaro-Winkler fuzzy string similarity for OCR typo tolerance).
  - `pydantic>=2.0` (`LandmarkMatchResult`, `NavigationEvent` data models).
- **Decision / Alternatives Considered / Why This One**:
  - *Decision:* EasyOCR + RapidFuzz fuzzy matching.
  - *Alternatives Considered:*
    - Tesseract OCR: Lower out-of-box accuracy on real-world outdoor signs with perspective distortion.
    - Google Cloud Vision API: Requires internet connectivity — unacceptable for a device that must function in campus dead zones.
    - QR-code landmark markers: Requires physical infrastructure installation across campus.
  - *Why This One:* EasyOCR runs fully offline, achieves $>90\%$ accuracy on sign fonts in well-lit conditions, and handles non-English text if campus signs include regional language characters. Fuzzy matching provides graceful degradation when partial reads or weathered signs are encountered.
  - *EasyOCR Install Constraint:* Standard `pip install easyocr` installs `opencv-headless` as a dependency, which overwrites `opencv-python` and destroys `cv2.imshow()` used by Phase 2's visual HUD. Resolved by installing with `--no-deps` and manually pinning only pure-Python EasyOCR dependencies in `requirements.txt`.
- **Functionality & Data Flow**:
  - Camera frame → `SignpostReader.read_frame()` → list of `(text, confidence)` tuples.
  - Each text string → `LandmarkMatcher.match()` → `LandmarkMatchResult` with `matched_node_id`, `similarity_score`, and `match_strategy` ("exact", "fuzzy", "substring", "sign_field").
  - Match result → `CampusNavigator.process_landmark_event()` → `NavigationEvent` with `event_type` ("WAYPOINT_REACHED", "DESTINATION_REACHED", "OFF_ROUTE_LANDMARK"), `voice_instruction`, and `remaining_distance_m`.
- **Inputs & Outputs**:
  - *Input:* BGR image frame (`np.ndarray`), optionally `node_hint` (current expected node ID) for targeted matching.
  - *Output:* `NavigationEvent` (or `None` if no landmark matched above confidence floor).
- **Known Limitations**:
  - OCR accuracy degrades significantly in direct glare on retroreflective sign materials (common on Indian campus signboards).
  - Very small signs ($<60\text{px}$ text height) may not be reliably read without optical zoom.

---

## Phase 4: 3-Tier Confidence Policy, Decaying Hazard Memory & Dynamic Rerouting

- **What Was Built**:
  - `src/decision/confidence_policy.py`: `ConfidencePolicy` engine mapping a `DetectedObstacle`'s `(confidence, in_walking_lane, shadow_likelihood)` triple to one of three formal action tiers:
    - **Tier 1 — BLOCKED** ($\text{conf} \ge 0.70$, in-lane): Obstacle confirmed real. Triggers Dijkstra reroute, graph edge penalty, hazard memory write, shared DB POST, and WebSocket broadcast.
    - **Tier 2 — HEDGE** ($0.40 \le \text{conf} < 0.70$, or off-lane): Uncertain or lateral detection. Issues spoken caution, holds current route, logs for review.
    - **Tier 3 — ESCALATE** ($\text{conf} < 0.40$, in-lane): Ambiguous in-path hazard. Sets escalation flag for Phase 6 caregiver notification; user is instructed to stop and wait.
  - `src/decision/hazard_memory.py`: `HazardMemory` — in-memory store of `HazardRecord` objects with exponential time decay:
    $$W(t) = W_0 \times e^{-\Delta t / \tau}$$
    where $\tau$ is configurable per obstacle class (pothole: $120\text{s}$, vehicle: $45\text{s}$, tree: $300\text{s}$, pillar: $600\text{s}$). Records whose weight falls below $5\%$ of $W_0$ are automatically pruned and their graph edge penalties are removed. Re-detecting the same obstacle on the same edge refreshes `last_confirmed` and restores weight to $W_0$.
  - `tests/test_decision.py`: 14 unit tests covering all tier boundaries, off-lane capping, shadow-penalized detection, decay mathematics, stale pruning, and manual removal.
- **Technology & Libraries Used**:
  - `pydantic>=2.0` (`PolicyDecision`, `HazardRecord` data models).
  - Python `math.exp` (exponential decay — no external dep needed).
  - Python `time` (monotonic real-world timestamps for decay $\Delta t$).
- **Decision / Alternatives Considered / Why This One**:
  - *Decision:* Continuous exponential decay with per-class $\tau$, rather than fixed TTL expiry.
  - *Alternatives Considered:*
    - Fixed time-to-live (TTL) per obstacle: Binary — obstacle is either fully active or fully gone, which causes abrupt graph weight jumps and potential oscillating reroutes near expiry.
    - Bayesian occupancy grid: More principled probabilistically, but requires known map geometry and is too heavy for CPU-only real-time use.
  - *Why This One:* Exponential decay provides a smooth, physically intuitive model — a freshly reported pothole carries full penalty, while an old report from 5 minutes ago (not re-confirmed) carries very little. This prevents phantom reroutes from long-expired reports while maintaining caution for freshly confirmed hazards.
  - *Shadow integration:* Because `ShadowLightAnalyzer` already downscales `confidence` before `ConfidencePolicy` sees it, shadow-affected detections naturally land in Tier 2 (HEDGE) without any shadow-specific logic inside the policy itself. This preserves separation of concerns.
- **Functionality & Data Flow**:
  - `ObstacleDetector.process_frame()` → `DetectedObstacle` → `ConfidencePolicy.evaluate()` → `PolicyDecision`.
  - `BLOCKED` path: → `HazardMemory.add_or_refresh()` → `CampusGraph.add_edge_penalty()` → `DijkstraRouter.find_route()` (reroute).
  - `HEDGE` path: → spoken caution → no graph modification.
  - `ESCALATE` path: → `escalation_triggered = True` flag → Phase 6 notification layer.
  - Background decay worker calls `HazardMemory.decay_all()` and removes stale penalties from the graph on each tick.
- **Inputs & Outputs**:
  - *Input:* `DetectedObstacle` (from Phase 2 perception pipeline).
  - *Output:* `PolicyDecision` with fields: `tier` (`ConfidenceTier`), `spoken_instruction` (`str`), `reroute_triggered` (`bool`), `escalation_triggered` (`bool`), `decay_tau_s` (`float`).
- **Known Limitations**:
  - In-memory `HazardMemory` is cleared on process restart. Persistence across restarts is handled by Phase 5's SQLite `ObstacleStore`.
  - Decay $\tau$ values are currently hard-coded constants; a future version could learn adaptive $\tau$ per location from historical re-detection frequency.

---

## Phase 5: Shared Obstacle Database & Multi-User Synchronization

- **What Was Built**:
  - `src/db/schema.py`: SQLite schema initialisation with WAL (Write-Ahead Logging) journal mode. WAL mode enables safe concurrent reads from multiple users while one user writes — no table locks, no blocking.
  - `src/db/obstacle_store.py`: `ObstacleStore` — synchronous, thread-safe SQLite persistence layer. Methods: `upsert(record)` (INSERT OR UPDATE with `MAX(confidence)` on conflict), `get_active(threshold)` (retrieves all non-stale records), `decay_tick(now)` (applies exponential decay to all rows, deletes stale entries, returns list of pruned IDs), `clear_edge(edge_id)`, and `remove(obstacle_id)`.
  - `src/api/server.py`: FastAPI HTTP + WebSocket server exposing:
    - `GET /status` — returns JSON of all active obstacles and count.
    - `POST /obstacles` — accepts `HazardRecord`-shaped JSON, upserts to DB, broadcasts `obstacle_reported` event to all connected WebSocket clients.
    - `POST /obstacles/{id}/clear` — manually removes an obstacle (user confirms path is clear), broadcasts `obstacle_cleared`.
    - `GET /health` — liveness probe.
    - `WebSocket /ws/telemetry` — on connect: sends full current hazard snapshot. On obstacle POST or decay tick: pushes `obstacle_reported` / `decay_tick` JSON to all connected clients. Supports `ping`/`status` commands from clients.
  - `src/api/decay_worker.py` (inline in `server.py`): Background `asyncio.Task` launched via FastAPI `lifespan` context. Runs `ObstacleStore.decay_tick()` every 10 seconds, broadcasts updated hazard map to all WebSocket clients, and logs pruned obstacle IDs.
  - `tests/test_db_and_sync.py`: 16 integration tests covering upsert, confidence MAX merge on conflict, decay mathematics, stale pruning, manual removal, `clear_edge`, multi-user upsert, REST endpoints, WebSocket snapshot-on-connect, obstacle broadcast, and ping/pong.
- **Technology & Libraries Used**:
  - `fastapi==0.141.1` + `uvicorn==0.53.0` (ASGI HTTP + WebSocket server).
  - `sqlite3` (stdlib, WAL mode, `row_factory=sqlite3.Row` for named column access).
  - `aiosqlite==0.22.1` (installed for future async upgrade path; current implementation uses sync `sqlite3` with short-lived connections which is sufficient for this load profile).
  - `aiofiles==25.1.0`, `websockets==17.1` (async file I/O and WebSocket client support for demo and testing).
  - `httpx==0.28.1` (HTTPX async/sync test client for FastAPI `TestClient`).
- **Decision / Alternatives Considered / Why This One**:
  - *Decision:* SQLite (WAL mode) + FastAPI WebSocket broadcast, rather than a heavier message broker.
  - *Alternatives Considered:*
    - Redis Pub/Sub: Would work well for real-time broadcast but adds a running Redis server as an infrastructure dependency. Unacceptable for a campus device that runs entirely offline.
    - PostgreSQL with NOTIFY: Requires a Postgres server process — too heavy for a Raspberry Pi / laptop edge device.
    - In-memory dict with no persistence: Means all obstacle history is lost on app restart or crash — unsafe for a safety-critical navigation tool.
  - *Why This One:* SQLite with WAL requires zero infrastructure. It runs in-process, supports multiple readers concurrently, and persists hazard history across restarts. FastAPI's built-in WebSocket support provides the real-time broadcast layer with no additional broker. This architecture runs entirely offline on a laptop or edge device with no external dependencies.
  - *Single-file DB path:* `data/obstacles.db` is `.gitignore`d (like all run-time data). On a co-developer's machine, the DB is created fresh on first run by `db_init()`.
- **Functionality & Data Flow**:
  - User 1 (`ObstacleDetector`) detects `BLOCKED` obstacle → `ConfidencePolicy` emits `PolicyDecision` → `POST /obstacles` → `ObstacleStore.upsert()` → `_broadcast()` to all WebSocket clients.
  - User 2 (any connected WebSocket client) immediately receives `{event: "obstacle_reported", obstacle: {...}}` and updates their local Dijkstra graph edge weights.
  - `DecayWorker` (10s tick) → `ObstacleStore.decay_tick()` → broadcast `{event: "decay_tick", pruned_ids: [...], active_hazards: [...]}` → all clients remove stale penalties from their local graphs.
- **Inputs & Outputs**:
  - *Input (REST):* `ObstacleReportRequest` JSON body with `edge_id`, `label`, `confidence`, `decay_tau_s`, `penalty_weight`, `reported_by`.
  - *Output (REST):* `HazardRecord` JSON with all fields including `obstacle_id`, `active_weight`, `first_seen`, `last_confirmed`.
  - *Output (WebSocket):* JSON events: `snapshot`, `obstacle_reported`, `obstacle_cleared`, `decay_tick`, `pong`, `status_response`.
- **Known Limitations**:
  - Currently single-server: All users must connect to the same `uvicorn` instance. A multi-server deployment would require a shared Redis or Postgres NOTIFY for cross-process broadcast (future roadmap).
  - Decay ticks are server-driven at 10s intervals; a client that goes offline mid-session will have stale weights until it reconnects and receives the next broadcast snapshot.

---

## Phase 6: Dual-Mode Notification Layer (Voice TTS + Haptic Encoder + Caregiver Dashboard)

- **What Was Built**:
  - `src/notifications/voice_engine.py`: `VoiceQueue` — thread-safe `PriorityQueue` for spoken instructions. Supports three priority levels: `urgent` (priority 0), `normal` (1), `low` (2). Duplicate consecutive texts are de-duped at enqueue time (not dequeue) so the same caution message is not repeated on every frame. Urgent instructions (`BLOCKED`, `ESCALATE`) call `interrupt_previous=True`, which drains the queue before insertion. `VoiceEngine` wraps the queue with `speak()`, `speak_urgent()`, and `speak_low()` convenience methods.
  - `src/notifications/haptic_encoder.py`: `HapticEncoder` — encodes turns, alerts, and milestones into the CampusEcho haptic protocol string `{side}{intensity}P{pattern}`:
    - `side`: `L` (left motor), `R` (right motor), `B` (both)
    - `intensity`: 1–9 (vibration strength)
    - `pattern`: 1=single, 2=double-tap, 3=rapid burst, 4=long hold, 5=SOS
    - `HapticCommand.parse()` validates and describes any command string for the simulator UI.
  - `src/notifications/mode_router.py`: `ModeRouter` — central output dispatcher. Accepts `PolicyDecision` and `NavigationEvent` objects, routes to `VoiceEngine` and/or `HapticEncoder` based on the active `OutputMode` (`VOICE_ONLY`, `HAPTIC_ONLY`, `DUAL`). Mode is togglable at runtime. Registers callbacks so the API server can forward `voice_speak` and `haptic_cmd` WebSocket events to the dashboard. Maintains `session_log: List[DispatchResult]` for post-walk report generation.
  - `src/api/telemetry.py`: Defines all WebSocket event type constants (`voice_speak`, `haptic_cmd`, `nav_event`, `frame_result`, `escalation`, `mode_change`, `walk_start`, `walk_end`, …) and factory functions so server code stays free of raw string literals.
  - `src/api/server.py` (additions): `POST /mode` endpoint accepts `{"mode": "DUAL"|"VOICE_ONLY"|"HAPTIC_ONLY"}`, updates `ModeRouter`, and broadcasts `mode_change` to all WebSocket clients. `GET /dashboard` serves `static/dashboard.html`. `StaticFiles` mount at `/static` serves all assets.
  - `static/dashboard.html`: Single-file Caregiver Mission Control Dashboard (vanilla HTML5/CSS3/ES Modules, no build step):
    - **Left panel**: Live annotated camera feed via MJPEG `<img src="/video_feed">`.
    - **Centre panel**: SVG campus map with 8 nodes and 8 edges matching `campus_graph.json`. Hazard pins render on edge midpoints, colour-coded red → amber → grey as `active_weight` decays. Active route highlighted in indigo. Animated user-position dot.
    - **Haptic Simulator**: Visual motor-ring pulse animations (left/right/both) + stereo spatial audio tones via Web Audio API (`StereoPannerNode`). Fully functional with zero hardware — judges can see and hear every haptic event.
    - **Right panel**: Live scrolling Decision Reasoning Trail with colour-coded border per tier (red=BLOCKED, amber=HEDGE, purple=ESCALATE, green=nav).
    - **Escalation Modal**: Full-screen glassmorphism overlay triggered by `escalation` WebSocket event. Shows spoken instruction, obstacle label, confidence, distance, and a "Dispatch Help" action.
    - **Post-Walk Report**: Clicking "End Walk" generates a summary (duration, obstacles, escalations, nav events) and a full chronological decision audit table. Exportable as JSON via `Blob` download.
    - **Mode toggle**: Three-button pill (Dual / Voice / Haptic) calls `POST /mode` and receives `mode_change` broadcast.
  - `tests/test_notifications.py`: 20 unit tests covering haptic protocol encoding, VoiceQueue priority ordering, dedup, urgent bypass, flush, mode dispatch for all three modes, and session log recording.
- **Technology & Libraries Used**:
  - **Web Speech Synthesis API** (browser built-in): Zero-latency TTS with no API key, no network round-trip, no external dependency. Priority controlled by the `VoiceQueue` in Python; actual speech is synthesised client-side.
  - **Web Audio API** (`AudioContext`, `OscillatorNode`, `StereoPannerNode`): Spatial audio haptic tones (left-panned for L motor, right-panned for R motor) providing an audible haptic simulation for judges without hardware.
  - **Vanilla HTML5/CSS3**: No React, no npm, no build step. Loads in <200ms on any modern browser on the demo laptop.
  - `python-multipart==0.0.32` (added to `requirements.txt`): Required by FastAPI's `StaticFiles` mount and `FileResponse` for the dashboard endpoint.
- **Decision / Alternatives Considered / Why This One**:
  - *Decision (TTS):* Web Speech Synthesis API, not `pyttsx3` or ElevenLabs.
    - *Why:* `pyttsx3` requires a native TTS engine install per OS (SAPI5/espeak), adds process-level latency, and cannot be interrupted mid-utterance. ElevenLabs requires an API key and internet. Web Speech runs in the browser with sub-50ms latency and supports `speechSynthesis.cancel()` for urgent interrupts.
  - *Decision (Haptic Protocol):* Custom `L{n}P{p}` string protocol with Web Audio simulator fallback, not native Bluetooth-only.
    - *Why:* The demo is hardware-optional. If the ESP32 or Bluetooth drops during judging, the Web Haptic Simulator is a guaranteed visual + audible fallback that makes haptic feedback fully legible to the audience. Hardware connects transparently if present via the same command string over Bluetooth SPP serial.
  - *Decision (Dashboard):* Single-file vanilla HTML, not React/Next.js or Streamlit.
    - *Why:* Zero npm dependency fragility on a hackathon team machine. No build pipeline to break. The dashboard loads by double-clicking the file or visiting `/dashboard`, requires no `npm install`, and works on any teammate's machine in seconds.
- **Functionality & Data Flow**:
  - `ObstacleDetector` frame → `ConfidencePolicy.evaluate()` → `PolicyDecision` → `ModeRouter.handle_decision()` → `DispatchResult` → callback → `_broadcast()`.
  - `DispatchResult.voice_text` → WS `voice_speak` event → browser `speechSynthesis.speak()`.
  - `DispatchResult.haptic_cmd` → WS `haptic_cmd` event → browser `fireHaptic(cmd)` → ring pulse animation + spatial audio + (optional) ESP32 serial.
  - `NavigationEvent` → `ModeRouter.handle_nav_event()` → turn haptic + voice instruction.
  - `ESCALATE` tier → `ModeRouter` fires `speak_urgent()` + `B9P5` haptic → `_broadcast(escalation event)` → dashboard Escalation Modal opens.
- **Inputs & Outputs**:
  - *Input:* `PolicyDecision` (from Phase 4), `NavigationEvent` (from Phase 3), mode toggle command via `POST /mode`.
  - *Output (WS):* `voice_speak`, `haptic_cmd`, `nav_event`, `frame_result`, `escalation`, `mode_change`, `walk_start`, `walk_end`.
  - *Output (REST):* `GET /dashboard` → HTML, `POST /mode` → `{status, mode}`.
- **Known Limitations**:
  - Web Speech voice selection is browser/OS-dependent; quality varies between Chrome and Firefox.
  - The MJPEG `/video_feed` endpoint is not yet wired to `ObstacleDetector` in Phase 6 — it will be connected in Phase 7's `start.py` integration. The dashboard `<img>` shows a placeholder if the endpoint is unreachable.

---

## Phase 7: End-to-End Integration, Staged Demo Scenarios & Polish

- **What Was Built**:
  - `start.py`: Master single-command launcher. Sequence: (1) calls `db_init()`, (2) starts `uvicorn` FastAPI server in a background daemon thread, (3) polls `GET /health` until server is ready (max 8s), (4) `POST /mode` to set initial output mode, (5) calls `webbrowser.open()` to open the dashboard, (6) keeps main thread alive with `Ctrl+C` handler. Accepts `--mode`, `--video`, `--host`, `--port`, `--start`, `--destination`, `--no-browser` flags.
  - `scripts/run_demo_scenarios.py`: Automated 3-scenario demo runner that exercises the full pipeline against a running server without requiring a live camera:
    - **Scenario 1** (Clear Path): Narrates a clear walking corridor with expected TTS and haptic outputs.
    - **Scenario 2** (BLOCKED — Chair): POSTs a real obstacle to `POST /obstacles`, shows DB write confirmation, narrates Tier 1 reroute + `B9P3` haptic + WS broadcast.
    - **Scenario 3** (ESCALATE — Shadowed Step): Narrates the shadow-calibrated confidence path leading to Tier 3 `B9P5` SOS haptic + escalation modal.
    - Ends with a live DB status query showing active hazard count and weights.
  - `tests/test_integration.py`: 5 end-to-end integration tests covering: (1) clear frame → HEDGE policy, (2) high-confidence in-lane → BLOCKED reroute flag, (3) low-confidence in-lane → ESCALATE flag, (4) DUAL mode dispatch emits voice + haptic, (5) FastAPI endpoints: `/health`, `/dashboard`, `POST /mode` (valid and invalid), and WebSocket `mode_change` broadcast.
  - **100 tests passing** across all 7 phases (Phases 1–7, 11.49s full run).
- **Technology & Libraries Used**:
  - `uvicorn` (already in `requirements.txt`): Used as both the production server and the background thread server inside `start.py`. `log_level="warning"` suppresses per-request noise in the terminal.
  - `httpx` (already in `requirements.txt`): Used in `start.py` for health-check polling and mode-set POST, and in `run_demo_scenarios.py` for REST API calls.
  - `webbrowser` (Python stdlib): Opens the dashboard URL in the system default browser on startup.
  - `threading.Thread(daemon=True)`: The server thread is daemonised so it automatically terminates when the main thread exits on `Ctrl+C`.
- **Decision / Alternatives Considered / Why This One**:
  - *Decision:* `threading.Thread` for the server, not `subprocess.Popen`.
    - *Why:* Running uvicorn in a thread shares the same Python process, which means `store`, `mode_router`, and `_ws_clients` global objects are shared directly — no IPC, no serialisation, no port conflicts. `subprocess.Popen` would require the full server to be an external process and `httpx` calls for every interaction.
  - *Decision:* Demo runner posts real REST calls to the live server rather than mocking.
    - *Why:* This validates the actual end-to-end WebSocket broadcast path — a judge can watch the dashboard update in real time as the demo script runs, making the multi-user sync capability visually demonstrable without needing a second physical device.
  - *Decision:* `--no-browser` flag in `start.py`.
    - *Why:* Allows the server to run headlessly in a terminal (e.g., if a co-developer is running a separate frontend or wants to open the dashboard manually). Keeps the launcher useful in non-GUI environments.
- **Functionality & Data Flow** (Full System — All 7 Phases):
  - `start.py` → `db_init()` → `uvicorn` server → `POST /mode` → `webbrowser.open(/dashboard)`.
  - Camera / `--video` file → `ObstacleDetector.process_frame()` → `ShadowFilter` → `ConfidencePolicy` → `ModeRouter` → `_broadcast()` → dashboard `voice_speak` + `haptic_cmd`.
  - `BLOCKED` → `HazardMemory.add_or_refresh()` → `CampusGraph.add_edge_penalty()` → `DijkstraRouter.find_route()` → new route → `ModeRouter.handle_nav_event()` → turn voice + haptic.
  - `POST /obstacles` → `ObstacleStore.upsert()` → `_broadcast(obstacle_reported)` → all WS clients update edge weights.
  - 10s `DecayWorker` tick → `ObstacleStore.decay_tick()` → hazard pin colour fades on dashboard map → stale edges re-open.
  - "End Walk" → `ModeRouter.session_log` → post-walk report table rendered in dashboard.
- **Inputs & Outputs**:
  - *Input:* `python start.py [--mode] [--video] [--destination]`
  - *Output:* Full running system at `http://localhost:8000/dashboard` with live video, campus map, reasoning trail, haptic simulator, voice TTS, escalation modal, and post-walk report.
- **Known Limitations**:
  - `start.py` does not yet launch the `ObstacleDetector` perception loop automatically — it launches the API server and opens the dashboard, but the perception thread must be started separately (e.g., `python demo_phase2.py`). Full auto-launch will be the final pre-demo integration step.
  - Windows Bluetooth pairing is configured once manually in OS Bluetooth settings (`CampusEcho-Wristband`); thereafter the assigned virtual COM port remains stable across restarts.

---

## Hardware Integration: ESP32 Haptic Wristband (`campusecho_haptic_wristband.ino`)

- **What Was Built**:
  - `src/notifications/haptic_bridge.py`:
    - `HapticBridge`: Hardware serial communication driver connecting CampusEcho to the ESP32 wristband over Bluetooth Classic SPP virtual COM ports.
    - **Protocol Translation Layer**: Bridges CampusEcho's internal token format (`{side}{intensity}P{pattern}`) to firmware newline-terminated CSV format (`<side>,<intensity>,<pattern>\n`).
    - **Pattern Remapping**:
      - `P1` (Single / slow pulse) $\rightarrow$ Firmware `1` (Slow pulse: 500ms on / 500ms off — walk straight confirmation, start confirmation)
      - `P2` (Double-tap) $\rightarrow$ Firmware `3` (Double-pulse: 120ms on/100ms off/120ms on/600ms off — left/right turn instructions, caution)
      - `P3` (Rapid burst) $\rightarrow$ Firmware `2` (Rapid pulse: 150ms on / 100ms off — BLOCKED obstacle hazard alert)
      - `P4` (Long hold) $\rightarrow$ Firmware `0` (Continuous vibration — destination reached)
      - `P5` (SOS pattern) $\rightarrow$ Firmware `3` (Critical double-pulse at max intensity — ESCALATE emergency)
      - Direct CSV passthrough supported (`L,7,2`, `O,0,0`).
    - **Non-blocking Worker Queue**: Commands are enqueued into a thread-safe `queue.Queue(maxsize=100)` and processed by a dedicated daemon worker thread (`HapticBridgeWorker`). Serial transmission never stalls the vision perception loop or FastAPI async handlers.
    - **Port Discovery & Auto-Detect**: Enumerate system COM ports with `serial.tools.list_ports.comports()`, heuristically searching for `CampusEcho-Wristband` or standard Bluetooth SPP signatures.
    - **Graceful Hardware Degradation**: If hardware is absent or disconnected, packets drop cleanly without throwing exceptions, allowing the Web Haptic Simulator to operate uninterrupted.
  - `campusecho_haptic_wristband.ino`:
    - ESP32-WROOM-32 DevKitC firmware driving two coin ERM vibration motors via low-side NPN transistors (GPIO 25 = Left, GPIO 26 = Right).
    - Uses ESP32 Arduino Core 3.x pin-based LEDC PWM at 5 kHz (eliminating motor whine).
    - Enforces a 3000ms safety failsafe (`FAILSAFE_TIMEOUT_MS = 3000`) that automatically kills both motors if no commands are received from the host.
  - `src/notifications/mode_router.py` (additions):
    - `set_mode(OutputMode.VOICE_ONLY)` dispatches an immediate silence event (`O,0,0\n`) to shut off physical motors instantly when switching away from haptic modes.
    - `handle_nav_event()` robustly extracts direction from either `turn_direction` or `direction` attributes.
  - `src/api/server.py` (additions):
    - Instantiates global `haptic_bridge` and registers `haptic_bridge.on_dispatch` with `mode_router`.
    - `GET /haptic/ports` — lists available COM ports and detected wristband port.
    - `GET /haptic/status` — returns connection state, port, baud, TX count, error count, and last command sent.
    - `POST /haptic/connect` — connects to requested COM port (`{"port": "COM5", "baud": 115200}`).
    - `POST /haptic/disconnect` — disconnects and silences motors.
    - `POST /haptic/test` — dispatches immediate test pulse to both physical wristband and Web Haptic Simulator.
    - WebSocket `/ws/telemetry` snapshot includes `haptic_bridge` status on client connection.
    - Server lifespan cleanup disconnects serial bridge on shutdown.
  - `static/dashboard.html` (additions):
    - Added **Hardware Wristband (ESP32)** sub-panel below the Haptic Simulator:
      - Live status badge: 🟢 `ESP32 (COM5)` or ⚪ `ESP32 Offline`.
      - COM Port selector with `↻` Scan button.
      - Connect / Disconnect toggle button.
      - Quick-test vibration buttons: "Test Left", "Test Right", "Test Hazard", "Stop All".
      - Real-time `TX` activity flash LED.
  - `start.py` (additions):
    - Added `--haptic-port` (e.g. `COM5` or `auto`) and `--haptic-baud` CLI arguments with graceful fallback to the Web Simulator if the port is unreachable.
  - `docs/HARDWARE_SETUP.md`:
    - Full hardware documentation: Bill of Materials, transistor circuit schematic, ESP32 Arduino IDE flashing steps, Windows Bluetooth pairing instructions, and verification steps.
  - `tests/test_haptic_bridge.py`:
    - 32 unit and integration tests covering protocol translation, clamping, mock serial connect/disconnect/write, port discovery, ModeRouter integration across all modes, and FastAPI REST endpoints.
  - **132 tests passing** across entire repository.
- **Technology & Libraries Used**:
  - `pyserial>=3.5`: Python serial communications library for COM port access.
  - `BluetoothSerial.h`: ESP32 Classic Bluetooth Serial Port Profile (SPP).
  - ESP32 Core 3.x LEDC PWM API (`ledcAttach` + `ledcWrite`).
- **Decision / Alternatives Considered / Why This One**:
  - *Decision:* Bluetooth Classic SPP rather than Bluetooth Low Energy (BLE) GATT.
    - *Why:* Windows natively pairs Bluetooth Classic SPP devices directly as virtual serial COM ports (`COMx`). This allows standard `pyserial` communication with zero third-party drivers, no native C++ WinRT bindings, and no complex BLE MTU fragmentation logic. BLE on Windows frequently suffers from permission headaches and dropped GATT characteristics during high-frequency telemetry.
  - *Decision:* Decoupled asynchronous worker queue.
    - *Why:* Serial port I/O and Bluetooth RF latency can incur 10–50ms delays per write. Placing serial transmission in a background daemon thread completely shields the 30 FPS vision perception loop and web server from serial jitter.
  - *Decision:* Dual-mode co-existence (Hardware Bridge + Web Simulator).
    - *Why:* The physical wristband and the Web Haptic Simulator listen to the same `haptic_cmd` stream. During a live demo or presentation, judges and caregivers see visual pulsing rings and hear spatial audio while the user simultaneously feels tactile vibration on their wrists. If the hardware battery dies, the presentation continues without a hitch.
- **Data Flow**:
  - `NavigationEvent` / `PolicyDecision` $\rightarrow$ `ModeRouter` $\rightarrow$ `DispatchResult(haptic_cmd="L7P2")`.
  - $\rightarrow$ WebSocket Broadcast $\rightarrow$ Dashboard Web Audio & Ring Pulse Simulator.
  - $\rightarrow$ `HapticBridge.on_dispatch()` $\rightarrow$ `translate_to_firmware("L7P2")` $\rightarrow$ `"L,7,3\n"`.
  - $\rightarrow$ `HapticBridgeWorker` $\rightarrow$ `serial.Serial.write(b"L,7,3\n")` $\rightarrow$ Bluetooth SPP $\rightarrow$ ESP32 DevKitC.
  - $\rightarrow$ ESP32 `handleCommand()` $\rightarrow$ PWM on `GPIO 25` $\rightarrow$ Left ERM coin motor double-pulses.

---

## Phase 8: Perception Hardening, YOLOv8l Large Backbone Upgrade & False Positive Suppression

- **What Was Built**:
  - `src/perception/detector.py` & `demo_phase2.py`:
    - **YOLOv8l Backbone Upgrade**: Transitioned object detection backbone from the lightweight nano model (`yolov8n.pt`, $3.2\text{M}$ parameters, $6.3\text{ MB}$) to the high-capacity Large architecture (`yolov8l.pt`, $43.7\text{M}$ parameters, $83.7\text{ MB}$) featuring a deep CSPDarknet53 feature pyramid.
    - **High-Confidence Threshold Calibration**: Raised default detection confidence threshold from $0.45 \rightarrow 0.65$ and alert gating threshold from $0.55 \rightarrow 0.65$. This explicitly eliminates continuous phantom vibrations and nervous buzzing on benign floor textures, carpet seams, minor ground-plane irregularities, and background clutter.
    - **Multi-Rate Inference Cadence (10–12 FPS Optimization)**: Solved CPU latency constraints ($500\text{ms}$ per full YOLOv8l forward pass) by implementing multi-rate perception with configurable inference cadence (default: 5). High-accuracy deep inference and environmental hazard heuristics execute on keyframes, while intermediate frames utilize cached detections with updated walking lane geometry and centroid kinematic tracking ($< 1\text{ms}$). This delivers smooth **10–12 FPS** video throughput with zero lag.
    - **PyTorch CPU Thread Optimization**: Configured `torch.set_num_threads(12)` and wrapped prediction in `torch.inference_mode()`, reducing raw YOLOv8l forward pass latency on Intel 16-core hosts from $560\text{ms} \rightarrow 417\text{ms}$ (a 25% speedup).
    - **Throughput Pacing in `VideoSource`**: Implemented real-time clock drift compensation in `VideoSource.stream()`, preventing accumulated processing lags from degrading playback and guaranteeing stable 12.0 target FPS.
    - **Rolling Window Throughput FPS**: Implemented a 15-frame rolling timestamp window in `ObstacleDetector.process_frame()` to accurately report continuous pipeline throughput rather than oscillating between keyframe and tracking numbers.
    - **Desktop Spoken Audio Narrator (`NativeVoiceSpeaker`)**: Connected Phase 6's voice layer into video and CLI testing via Windows native `System.Speech.Synthesis.SpeechSynthesizer`. Operates in a non-blocking asynchronous background worker thread ($< 1\text{ms}$ dispatch time), with immediate cancellation (`SpeakAsyncCancelAll`) for urgent BLOCKED/ESCALATE warnings.
    - **Integrated Decision Policy & HUD**: Connected `ConfidencePolicy` and `ModeRouter` to `demo_phase2.py`, annotating live video with a color-coded bottom subtitle banner (`VOICE: "Warning! chair blocking path 1.8 meters ahead"`) synchronized with ESP32 haptic vibration commands.
    - **Kinematic Moving-Away Suppression**: Implemented obstacle range-rate tracking ($\Delta d / \Delta t$). When a detected pedestrian or cyclist is moving away from the user ($d_t > d_{t-1}$), alerts and motor vibrations are suppressed, focusing haptic cues solely on approaching or stationary obstacles.
    - **Temporal Stability Gating (`stability_required_sec = 2.0`)**: Stationary in-lane obstacles must persist consistently across the temporal buffer for $\ge 2.0$ seconds before continuous alert vibrations fire, preventing single-frame transient detections from triggering haptic fatigue.
    - **Integrated Chromatic Shadow Filtering**: Preserved `ShadowLightAnalyzer` chromatic invariance and Laplacian texture roughness checks, ensuring cast shadows and dappled canopy sun spots continue to receive proportional confidence penalties prior to policy evaluation.
  - `tests/test_perception.py` & `tests/test_notifications.py`:
    - Verified all 16 perception unit tests and 27 notification unit tests passing, validating corridor containment, distance scaling, stair/pothole/wall heuristics, multi-frame debouncing, and local audio speaker toggling.
- **Technology & Libraries Used**:
  - `ultralytics>=8.4.0` (YOLOv8l Large PyTorch weights).
  - `torch`, `torchvision` (Deep learning inference engine with multi-threading and inference mode).
  - `System.Speech.Synthesis.SpeechSynthesizer` (Native Windows desktop TTS via asynchronous persistent worker).
  - `opencv-python>=5.0.0` (HUD visualizer, frame processing, translucent banner overlays, Canny edge detection).
  - `numpy>=2.4.0` (Vectorized geometric calculations and range-rate tracking).
- **Decision / Alternatives Considered / Why This One**:
  - *Decision:* Upgrade to YOLOv8l with multi-rate cadence (5) + NativeVoiceSpeaker for video testing.
  - *Alternatives Considered:*
    - *Single-frame synchronous YOLOv8l without cadence:* Resulted in 1–2 FPS slideshow playback on CPU, causing severe visual stutter and delayed user reactions.
    - *Downscaling model to YOLOv8n or MobileNet:* Nano models frequently missed low-profile obstacles, thin chair legs, construction barriers, and slender signs.
    - *Third-party pip TTS (pyttsx3 / gTTS / ElevenLabs):* `pyttsx3` has driver incompatibilities across Windows Python 3.11 distributions; `gTTS`/`ElevenLabs` require external internet connectivity. Native `System.Speech` runs 100% offline with zero dependencies and sub-millisecond async dispatch.
  - *Why This One:* YOLOv8l delivers state-of-the-art obstacle detection fidelity. Multi-rate inference cadence bridges the gap between deep neural network computational intensity and real-time interactive video frame rates (achieving 10–12 FPS). Native voice synthesis provides immediate spoken audio feedback without blocking video rendering.
- **Functionality & Data Flow**:
  - Camera/Video stream $\rightarrow$ `VideoSource` throughput pacing ($12\text{ FPS}$).
  - Frame $\rightarrow$ `ObstacleDetector.process_frame()` (Cadence: full YOLO on keyframes, tracked lane check on tracking frames).
  - Primary obstacle $\rightarrow$ `ConfidencePolicy.evaluate()` $\rightarrow$ `PolicyDecision`.
  - $\rightarrow$ `ModeRouter.handle_decision()`:
    - Spoken text $\rightarrow$ `NativeVoiceSpeaker` speaks aloud through PC speakers + renders in bottom HUD banner.
    - Haptic command $\rightarrow$ dispatched to ESP32 wristband via Bluetooth SPP / serial.
  - Displays annotated video at smooth 10–12 FPS with rolling throughput telemetry.
- **Inputs & Outputs**:
  - *Input:* 3-channel BGR video frame (`np.ndarray`), optional ESP32 COM port.
  - *Output:* Annotated video preview at 10–12 FPS, real-time spoken audio narrations, ESP32 vibration pulses, terminal telemetry.
- **Known Limitations**:
  - Initial YOLOv8l model weight loading takes $\sim 2.5\text{s}$ on cold start; once warmed up, the pipeline operates smoothly at target throughput.

---

## Phase 9: Full SGSITS Campus Navigation Graph & Multi-Angle Landmark Catalog

- **What Was Built**:
  - `data/sgsits_campus_graph_full.json`:
    - Comprehensive 33-node, 39-edge topological campus navigation graph covering Shri Govindram Seksaria Institute of Technology and Science (SGSITS, Indore).
    - Ingested real-world geospatial GIS coordinates from Google Maps satellite imagery and OpenStreetMap (SGSITS bounds: $22.725^\circ\text{N}–22.727^\circ\text{N}$, $75.872^\circ\text{E}–75.875^\circ\text{E}$).
    - Every edge records ground-truth metric segment length ($m$), compass heading ($^\circ$), and turn angles.
    - Ground-truth campus walkability verification:
      - **Rule 1 (Plus Point to Canteen Walkway):** Confirmed open for pedestrian traffic. The pathway connecting the student plaza (Plus Point) to the central canteen is fully walkable.
      - **Rule 2 (Main Gate / Green Gate Dual Walkways):** Confirmed both pedestrian side walkways flanking the main driveway on Park Road are open.
      - **Rule 3 (Gate 2 / Silveria Back Path):** Confirmed permanently locked/impassable. Pruned from the pedestrian routing graph to prevent guiding visually impaired users to dead-ends.
      - **Rule 4 (Hostel Pedestrian Routing):** Pathways between academic blocks and student hostels are strictly routed via the illuminated Canteen and ATC walkway rather than unlit service alleys.
  - Multi-Angle Visual Landmark Image Catalog:
    - Ingested 28 real-world photos located in `GS Photos/` named in `<LocationName>_<AngleNumber>.jpg` format (e.g. `goldenGate_ag1.jpg`, `directorOffice_ag1.jpg`, `silveria_ag1.jpg`, `library_ag1.jpg`, `canteen_ag1.jpg`, `plusPoint_ag1.jpg`).
    - Mapped each location and angle to the corresponding graph node with directional approach metadata (`landmark_images`), enabling OCR and visual landmark matching from varying approach angles.
- **Technology & Libraries Used**:
  - `networkx>=3.0` (Campus topological graph and edge weight computation).
  - `pydantic>=2.0` (Graph and node schema validation).
  - GIS coordinate projections and Haversine distance calculations.
- **Decision / Alternatives Considered / Why This One**:
  - *Decision:* Full customized topological graph with verified campus walkability rules and multi-angle ground-truth photo landmarks over generic Google Maps Directions API.
  - *Alternatives Considered:*
    - *Generic Google Maps Walking Directions API:* Does not resolve internal campus pedestrian pathways, courtyard corridors, internal building gateways, or locked campus gates. Blind reliance on commercial maps directs users through locked security gates or across vehicular parking lots.
    - *Pure GPS coordinate tracing:* Degrades under dense tree canopies, near tall concrete buildings (ATC, Silveria), and is unavailable indoors.
  - *Why This One:* SGSITS-specific topological mapping provides centimeter-accurate pedestrian corridor guidance, guarantees routing only through open gates, and enables landmark-assisted localization even when GPS drifts.
- **Functionality & Data Flow**:
  - Campus graph loaded at system startup.
  - Origin and destination specified via UI or voice.
  - Dijkstra calculates the shortest accessible route through open, verified pedestrian paths.
  - As the user walks, camera frames are matched against expected landmark signboards and reference visual photos (`landmark_images`) to confirm waypoint arrival and advance navigation steps.
- **Inputs & Outputs**:
  - *Input:* Start node ID, destination node ID, dynamic edge penalties.
  - *Output:* Turn-by-turn navigation route, landmark reference photos, and voice prompts.
- **Known Limitations**:
  - Covers outdoor campus ground level; vertical multi-floor transitions (elevators, stairs) within buildings are handled by the Phase 10 Indoor Recovery system.

---

## Phase 10: Indoor Landmark Position Recovery System & Multi-Floor Blueprint

- **What Was Built**:
  - `backend/localization/`:
    - `GPSSystem`: Monitors GNSS signal status and accuracy; detects signal loss ($>10\text{m}$ error or signal drop) upon entering campus buildings, automatically triggering indoor recovery mode.
    - `BLELandmarkManager`: Tracks Bluetooth Low Energy beacon RSSI signals across predefined indoor zones. Features moving-average signal smoothing and 3-scan temporal hysteresis to eliminate location flip-flopping across door thresholds.
    - `QRValidator`: High-contrast visual QR and ArUco code marker detector serving as an absolute, deterministic ground-truth position reset ($100\%$ confidence).
    - `LocalizationManager`: Central failover arbiter selecting the highest-fidelity available positioning source: $\text{GPS} \rightarrow \text{Visual} \rightarrow \text{BLE} \rightarrow \text{QR} \rightarrow \text{Last Known} \rightarrow \text{UNKNOWN}$.
  - **Safe Low-Confidence Suppression**: When localization confidence drops below $50\%$ ($<0.50$), the system immediately enters `SAFE_UNKNOWN` state: halts all turn instructions and motor vibrations, warns the user via voice ("Localization uncertain. Please move toward a marked landmark or scan a QR code"), and prevents misleading guidance.
  - `backend/navigation/`:
    - `IndoorMap`: In-memory topological graph representing indoor corridors, rooms, and stairwells across multiple floors.
    - `IndoorRouter`: Breadth-First Search (BFS) and Dijkstra router computing shortest indoor paths across rooms and floors.
    - `InstructionGenerator`: Converts graph steps into discrete haptic commands (`FORWARD`, `TURN_LEFT`, `TURN_RIGHT`, `STAIRS_UP`, `STAIRS_DOWN`, `ARRIVED`, `STOP`).
  - `backend/communication/esp32.py`: Dual-mode hardware communication bridge supporting HTTP JSON commands over Wi-Fi (`POST /command`) and Bluetooth Classic SPP serial fallback.
  - `static/indoor_dashboard.html`: Caregiver Indoor Mission Control dashboard:
    - 2D multi-floor architectural blueprint with live user position indicator.
    - Visual confidence meter (green $\ge 75\%$, amber $50–74\%$, red $<50\%$).
    - BLE beacon RSSI signal strength bars and active landmark indicator.
    - Manual QR scan and preset location testing tools.
  - `src/api/server.py` Integration:
    - Integrated indoor router via `app.include_router(indoor_app.router)` and dedicated WebSocket `/ws/indoor`.
    - Exposes `/indoor` dashboard at root URL.
  - Unit & Integration Test Suite (`tests/test_indoor_recovery.py`):
    - 19 automated tests verifying BLE hysteresis, low-confidence suppression, QR recovery, multi-floor routing, ESP32 command encoding, and REST endpoints.
    - **151 total passing tests** across the entire repository.
- **Technology & Libraries Used**:
  - `FastAPI`, `Starlette`, `uvicorn` (ASGI HTTP + WebSocket framework).
  - `pyzbar` / `opencv-python` (QR code decoding).
  - `httpx` (Asynchronous HTTP client for ESP32 Wi-Fi bridge).
  - `pytest` (Automated testing).
- **Decision / Alternatives Considered / Why This One**:
  - *Decision:* BLE landmark zone association with 3-scan hysteresis + QR visual ground truth + Safe low-confidence suppression.
  - *Alternatives Considered:*
    - *Pure Wi-Fi fingerprinting:* Prone to signal drift from moving people and requires extensive periodic war-driving/calibration.
    - *Ultra-Wideband (UWB):* Requires expensive custom hardware transceivers ($>\$100$ per tag) not standard on college budgets.
    - *Dead reckoning / IMU pedometry:* Severe cumulative drift within $10–15\text{m}$ without frequent ground-truth corrections.
  - *Why This One:* Low-cost BLE beacons ($<\$3$ each) provide robust room-level zone accuracy when stabilized with 3-scan hysteresis. QR markers provide zero-cost, zero-latency absolute calibration. The safety suppression principle ensures a blind user is never sent false directional commands when signal confidence is low.
- **Functionality & Data Flow**:
  - User walks into building $\rightarrow$ GPS lost $\rightarrow$ `LocalizationManager` switches to BLE mode.
  - ESP32 or phone scans BLE beacons $\rightarrow$ `BLELandmarkManager` smooths RSSI and establishes zone $\rightarrow$ confidence evaluated.
  - If confidence $\ge 0.50$ $\rightarrow$ `IndoorRouter` computes route to target room $\rightarrow$ Wi-Fi/Bluetooth dispatches turn pulses to wristband.
  - If confidence $<0.50$ $\rightarrow$ Motors silenced, voice prompts user to scan QR marker $\rightarrow$ Camera reads QR $\rightarrow$ Position reset to $100\%$ confidence $\rightarrow$ Navigation resumes.
  - Caregiver observes live position on 2D blueprint via WebSocket.
- **Inputs & Outputs**:
  - *Input:* BLE beacon RSSI dictionary, QR code payload strings, destination room ID.
  - *Output:* Indoor turn instructions, ESP32 haptic motor commands, WebSocket UI state.
- **Known Limitations**:
  - BLE beacon batteries require periodic replacement (typically $1–2$ years).
  - QR marker scanning requires the user to point the camera generally towards doorframes or signboards.
