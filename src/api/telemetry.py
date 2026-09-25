"""
WebSocket telemetry event definitions for the CampusEcho dashboard.
All events are JSON objects with a top-level 'event' key.
"""

# ── Outbound event types (server → dashboard) ─────────────────────────────────

EVENT_SNAPSHOT         = "snapshot"          # Initial hazard state on WS connect
EVENT_OBSTACLE_REPORTED= "obstacle_reported" # New obstacle posted to DB
EVENT_OBSTACLE_CLEARED = "obstacle_cleared"  # Obstacle manually cleared
EVENT_DECAY_TICK       = "decay_tick"        # Periodic decay update
EVENT_VOICE_SPEAK      = "voice_speak"       # Browser should speak this text
EVENT_HAPTIC_CMD       = "haptic_cmd"        # Browser/ESP32 should fire haptic
EVENT_NAV_EVENT        = "nav_event"         # Navigation waypoint/arrival event
EVENT_FRAME_RESULT     = "frame_result"      # Per-frame perception result
EVENT_ESCALATION       = "escalation"        # Tier 3 escalation alert
EVENT_MODE_CHANGE      = "mode_change"       # Output mode toggled
EVENT_WALK_START       = "walk_start"        # Navigation walk started
EVENT_WALK_END         = "walk_end"          # Walk ended, post-walk report ready
EVENT_PONG             = "pong"              # Ping response
EVENT_STATUS_RESPONSE  = "status_response"   # Status query response

# ── Inbound command types (dashboard → server) ────────────────────────────────

CMD_PING               = "ping"
CMD_STATUS             = "status"
CMD_SET_MODE           = "set_mode"          # {"cmd": "set_mode", "mode": "DUAL"}
CMD_START_WALK         = "start_walk"        # {"cmd": "start_walk", "start": "...", "dest": "..."}
CMD_END_WALK           = "end_walk"
CMD_CLEAR_OBSTACLE     = "clear_obstacle"    # {"cmd": "clear_obstacle", "obstacle_id": "..."}


def make_voice_event(text: str, priority: str = "normal") -> dict:
    return {"event": EVENT_VOICE_SPEAK, "text": text, "priority": priority}


def make_haptic_event(cmd: str) -> dict:
    return {"event": EVENT_HAPTIC_CMD, "cmd": cmd}


def make_escalation_event(text: str, obstacle_label: str,
                          confidence: float, distance_m: float) -> dict:
    return {
        "event": EVENT_ESCALATION,
        "spoken_instruction": text,
        "obstacle_label": obstacle_label,
        "confidence": confidence,
        "distance_m": distance_m,
    }


def make_nav_event(event_type: str, voice_instruction: str,
                   remaining_distance_m: float, node_label: str) -> dict:
    return {
        "event": EVENT_NAV_EVENT,
        "event_type": event_type,
        "voice_instruction": voice_instruction,
        "remaining_distance_m": remaining_distance_m,
        "node_label": node_label,
    }


def make_frame_result_event(obstacles: list, path_clear: bool,
                            fps: float, processing_ms: float) -> dict:
    return {
        "event": EVENT_FRAME_RESULT,
        "obstacle_count": len(obstacles),
        "path_clear": path_clear,
        "fps": round(fps, 1),
        "processing_ms": round(processing_ms, 1),
        "obstacles": [
            {
                "label": o.get("label", ""),
                "confidence": o.get("confidence", 0.0),
                "distance_m": o.get("distance_m", 0.0),
                "in_walking_lane": o.get("in_walking_lane", False),
                "horizontal_position": o.get("horizontal_position", "center"),
                "urgency": o.get("urgency", "low"),
            }
            for o in obstacles
        ],
    }
