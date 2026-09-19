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

*(To be filled upon completion of Phase 2)*

- **What Was Built**:
- **Technology & Libraries Used**:
- **Decision / Alternatives Considered / Why This One**:
- **Functionality & Data Flow**:
- **Inputs & Outputs**:
- **Known Limitations**:

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
