"""
Navigation Instruction Generator.
Translates route graph steps into high-level turn-by-turn guidance:
LEFT, RIGHT, FORWARD, ARRIVED, STOP, UNKNOWN.
Implements safe low-confidence suppression.
"""
import math
from typing import Dict, List, Optional, Any, Tuple
from backend.navigation.map import IndoorMap


class InstructionGenerator:
    """
    Evaluates current position, route, and destination to issue next navigation command.
    Ensures safe low-confidence behavior by withholding directional instructions
    when confidence is inadequate (< 0.50).
    """

    CONFIDENCE_MIN_NAV = 0.50

    # Haptic profile mappings (Spec Section 19)
    # LEFT: Left Strong (PWM 255), Right Off (PWM 0)
    # RIGHT: Left Off (PWM 0), Right Strong (PWM 255)
    # FORWARD: Both Strong (PWM 255)
    # ARRIVED: Both short pulse
    # UNKNOWN: Double short pulse
    # STOP: Both Off (PWM 0)
    HAPTIC_MAPPINGS = {
        "LEFT": {
            "side": "L",
            "left_pwm": 255,
            "right_pwm": 0,
            "endpoint": "/left",
            "pattern": "left_strong",
        },
        "RIGHT": {
            "side": "R",
            "left_pwm": 0,
            "right_pwm": 255,
            "endpoint": "/right",
            "pattern": "right_strong",
        },
        "FORWARD": {
            "side": "B",
            "left_pwm": 255,
            "right_pwm": 255,
            "endpoint": "/forward",
            "pattern": "both_strong",
        },
        "ARRIVED": {
            "side": "B",
            "left_pwm": 150,
            "right_pwm": 150,
            "endpoint": "/arrived",
            "pattern": "pulse_short",
        },
        "UNKNOWN": {
            "side": "B",
            "left_pwm": 100,
            "right_pwm": 100,
            "endpoint": "/unknown",
            "pattern": "double_pulse",
        },
        "STOP": {
            "side": "O",
            "left_pwm": 0,
            "right_pwm": 0,
            "endpoint": "/stop",
            "pattern": "off",
        },
    }

    def __init__(self, indoor_map: IndoorMap):
        self.indoor_map = indoor_map

    def generate_instruction(
        self,
        current_location: Optional[Dict[str, Any]],
        destination_id: Optional[str],
        full_route: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Determines the next action, verbal instruction, and haptic payload.
        """
        # 1. Check for missing destination
        if not destination_id:
            return self._build_response(
                command="STOP",
                instruction="No destination selected.",
                status="IDLE",
                safe_mode=False,
            )

        destination_id = destination_id.upper()
        dest_landmark = self.indoor_map.get_landmark(destination_id)
        dest_name = dest_landmark.get("name", destination_id) if dest_landmark else destination_id

        # 2. Check for missing or uncertain location (Spec Section 16)
        if not current_location:
            return self._build_response(
                command="UNKNOWN",
                instruction="Localization uncertain. Move toward a marked landmark or scan QR.",
                status="LOCALIZATION_UNCERTAIN",
                safe_mode=True,
                destination=destination_id,
            )

        conf = current_location.get("confidence", 0.0)
        source = current_location.get("source", "UNKNOWN")
        current_node = current_location.get("landmark_id")

        # Safe Low-Confidence Rule: confidence < 0.50 or source == UNKNOWN
        if conf < self.CONFIDENCE_MIN_NAV or source == "UNKNOWN" or not current_node:
            return self._build_response(
                command="UNKNOWN",
                instruction="Localization uncertain. Move toward a marked landmark or scan QR.",
                status="LOCALIZATION_UNCERTAIN",
                safe_mode=True,
                destination=destination_id,
                current_node=current_node,
                confidence=conf,
                source=source,
            )

        # 3. Check if arrived at destination
        if current_node == destination_id:
            return self._build_response(
                command="ARRIVED",
                instruction=f"You have arrived at {dest_name}!",
                status="ARRIVED",
                safe_mode=False,
                destination=destination_id,
                current_node=current_node,
                confidence=conf,
                source=source,
                route=[current_node],
            )

        # 4. Determine next step in route
        route = full_route or []
        if not route or current_node not in route:
            # Need to find or update route from current_node to destination_id
            from backend.navigation.router import IndoorRouter
            router = IndoorRouter(self.indoor_map)
            route = router.find_route(current_node, destination_id) or []

        if not route or len(route) < 2:
            return self._build_response(
                command="STOP",
                instruction="No valid route to destination.",
                status="ROUTE_ERROR",
                safe_mode=False,
                destination=destination_id,
                current_node=current_node,
            )

        # Find position of current_node in route
        try:
            curr_idx = route.index(current_node)
        except ValueError:
            curr_idx = 0

        if curr_idx >= len(route) - 1:
            # At or past the end of route
            return self._build_response(
                command="ARRIVED",
                instruction=f"You have reached {dest_name}!",
                status="ARRIVED",
                safe_mode=False,
                destination=destination_id,
                current_node=current_node,
                confidence=conf,
                source=source,
                route=route,
            )

        next_node = route[curr_idx + 1]
        next_lm = self.indoor_map.get_landmark(next_node) or {}
        next_name = next_lm.get("name", next_node)

        # 5. Compute direction (LEFT, RIGHT, FORWARD)
        prev_node = route[curr_idx - 1] if curr_idx > 0 else None
        direction = self._calculate_direction(prev_node, current_node, next_node)

        action_phrase = {
            "FORWARD": f"Continue straight toward {next_name}",
            "LEFT": f"Turn left toward {next_name}",
            "RIGHT": f"Turn right toward {next_name}",
        }.get(direction, f"Proceed toward {next_name}")

        return self._build_response(
            command=direction,
            instruction=action_phrase,
            status="NAVIGATING",
            safe_mode=False,
            destination=destination_id,
            current_node=current_node,
            next_node=next_node,
            confidence=conf,
            source=source,
            route=route[curr_idx:],
        )

    def _calculate_direction(
        self,
        prev_node: Optional[str],
        current_node: str,
        next_node: str,
    ) -> str:
        """
        Calculates whether the transition from current_node to next_node
        requires turning LEFT, turning RIGHT, or continuing FORWARD.
        """
        # Vector from current to next
        dx, dy = self.indoor_map.get_vector(current_node, next_node)

        # Specific topological rules for the standard B1-B5 test layout:
        # B1(0,0) -> B2(5,0): dx=5, dy=0 (East / Forward from Entrance)
        # B2(5,0) -> B3(10,0): dx=5, dy=0 (East / Forward down Corridor)
        # B2(5,0) -> B4(5,5): dx=0, dy=5 (North / Left turn from Corridor to Staircase)
        # B4(5,5) -> B5(10,5): dx=5, dy=0 (East / Right turn from Staircase into Library)
        # B3(10,0) -> B2(5,0): dx=-5, dy=0 (West / Forward back up Corridor)
        # B4(5,5) -> B2(5,0): dx=0, dy=-5 (South / Right turn down from Staircase)
        # B5(10,5) -> B4(5,5): dx=-5, dy=0 (West / Straight back to Staircase)

        if prev_node is not None:
            # We have preceding motion vector
            p_dx, p_dy = self.indoor_map.get_vector(prev_node, current_node)
            # Cross product (2D): p_dx * dy - p_dy * dx
            # Dot product: p_dx * dx + p_dy * dy
            cross = (p_dx * dy) - (p_dy * dx)
            dot = (p_dx * dx) + (p_dy * dy)

            # Angle between vectors in radians (-pi to +pi)
            angle = math.atan2(cross, dot)
            deg = math.degrees(angle)

            if -30.0 <= deg <= 30.0:
                return "FORWARD"
            elif deg > 30.0:
                return "LEFT"
            else:
                return "RIGHT"

        # If starting without previous node, derive initial heading relative to corridor
        # Corridor runs along +X axis (B1 -> B2 -> B3).
        # Heading towards B4 (+Y) is turning LEFT.
        # Heading towards -Y is turning RIGHT.
        if abs(dy) > abs(dx):
            return "LEFT" if dy > 0 else "RIGHT"
        elif dx < 0 and current_node == "B3":
            # Leaving Computer Lab back to Corridor
            return "FORWARD"
        elif dx > 0:
            return "FORWARD"

        return "FORWARD"

    def _build_response(
        self,
        command: str,
        instruction: str,
        status: str,
        safe_mode: bool,
        destination: Optional[str] = None,
        current_node: Optional[str] = None,
        next_node: Optional[str] = None,
        confidence: float = 0.0,
        source: str = "UNKNOWN",
        route: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        haptic = self.HAPTIC_MAPPINGS.get(command, self.HAPTIC_MAPPINGS["UNKNOWN"])
        return {
            "command": command,
            "instruction": instruction,
            "status": status,
            "safe_mode": safe_mode,
            "destination": destination,
            "current_node": current_node,
            "next_node": next_node,
            "confidence": round(confidence, 2),
            "source": source,
            "route": route or [],
            "haptic_profile": haptic,
        }
