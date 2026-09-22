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

---

## Phase 3: EasyOCR Sign Reading & Landmark Localization Engine

*(To be filled upon completion of Phase 3)*

- **What Was Built**:
- **Technology & Libraries Used**:
- **Decision / Alternatives Considered / Why This One**:
- **Functionality & Data Flow**:
- **Inputs & Outputs**:
- **Known Limitations**:

---

## Phase 4: 3-Tier Confidence Policy, Decaying Memory & Dynamic Rerouting

*(To be filled upon completion of Phase 4)*

- **What Was Built**:
- **Technology & Libraries Used**:
- **Decision / Alternatives Considered / Why This One**:
- **Functionality & Data Flow**:
- **Inputs & Outputs**:
- **Known Limitations**:

---

## Phase 5: Shared Obstacle Database & Multi-User Synchronization

*(To be filled upon completion of Phase 5)*

- **What Was Built**:
- **Technology & Libraries Used**:
- **Decision / Alternatives Considered / Why This One**:
- **Functionality & Data Flow**:
- **Inputs & Outputs**:
- **Known Limitations**:

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
