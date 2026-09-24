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

*(To be filled upon completion of Phase 6)*

- **What Was Built**:
- **Technology & Libraries Used**:
- **Decision / Alternatives Considered / Why This One**:
- **Functionality & Data Flow**:
- **Inputs & Outputs**:
- **Known Limitations**:

---

## Phase 7: End-to-End Integration, Staged Demo Scenarios & Polish

*(To be filled upon completion of Phase 7)*

- **What Was Built**:
- **Technology & Libraries Used**:
- **Decision / Alternatives Considered / Why This One**:
- **Functionality & Data Flow**:
- **Inputs & Outputs**:
- **Known Limitations**:
