"""Centroid tracking, kinematic approach velocity estimation, and parked vs moving state classifier."""
import time
from typing import Dict, List, Optional, Tuple
import numpy as np
from .models import DetectedObstacle


class TrackedObject:
    """Stores track history and kinematics for an obstacle."""

    def __init__(self, track_id: int, obstacle: DetectedObstacle, timestamp: float):
        self.track_id = track_id
        self.label = obstacle.label
        self.last_seen = timestamp
        self.history: List[Tuple[float, float, float, float]] = []  # (t, cx, cy, distance_m)
        self.velocity_mps: float = 0.0
        self.is_moving: bool = False
        self.state: str = "static"  # "static", "parked", "moving"
        self.update(obstacle, timestamp)

    def update(self, obstacle: DetectedObstacle, timestamp: float) -> None:
        self.last_seen = timestamp
        xmin, ymin, xmax, ymax = obstacle.bbox
        cx = (xmin + xmax) / 2.0
        cy = (ymin + ymax) / 2.0
        dist = obstacle.distance_m

        self.history.append((timestamp, cx, cy, dist))
        if len(self.history) > 10:
            self.history.pop(0)

        # Calculate approach velocity (positive = approaching user, negative = moving away)
        if len(self.history) >= 2:
            t_old, _, _, dist_old = self.history[0]
            dt = timestamp - t_old
            if dt > 0.12:  # Minimum time delta to compute meaningful speed
                self.velocity_mps = round((dist_old - dist) / dt, 2)
                # Consider moving if approach/recede speed >= 0.35 m/s
                self.is_moving = abs(self.velocity_mps) >= 0.35

        # Classify state: parked vs moving vs static
        lbl = obstacle.label.lower()
        is_vehicle = lbl in ("two_wheeler", "four_wheeler", "bicycle", "motorcycle", "car", "bus", "truck", "van", "scooter")

        if is_vehicle:
            if self.is_moving:
                self.state = "moving"
            else:
                self.state = "parked"
        else:
            self.state = "moving" if self.is_moving else "static"


class CentroidTracker:
    """Associates detections across consecutive frames and tracks dynamic movement."""

    def __init__(self, max_disappeared_sec: float = 1.0, max_match_dist_px: float = 140.0):
        self.max_disappeared_sec = max_disappeared_sec
        self.max_match_dist_px = max_match_dist_px
        self.next_id: int = 1
        self.tracks: Dict[int, TrackedObject] = {}

    def update(self, obstacles: List[DetectedObstacle], timestamp: Optional[float] = None) -> None:
        """
        Matches incoming detections to existing tracks and updates velocity/moving state.
        Modifies DetectedObstacle instances in-place with tracking_id, is_moving, velocity_mps, and state.
        """
        now = timestamp or time.time()

        # Prune dead tracks
        dead_ids = [
            tid for tid, track in self.tracks.items()
            if (now - track.last_seen) > self.max_disappeared_sec
        ]
        for tid in dead_ids:
            del self.tracks[tid]

        if not obstacles:
            return

        # If no active tracks, initialize all detections
        if not self.tracks:
            for obs in obstacles:
                tid = self.next_id
                self.next_id += 1
                new_track = TrackedObject(tid, obs, now)
                self.tracks[tid] = new_track
                obs.tracking_id = tid
                obs.is_moving = new_track.is_moving
                obs.velocity_mps = new_track.velocity_mps
                obs.state = new_track.state
            return

        # Compute centroid distance matrix between existing tracks and new obstacles
        track_ids = list(self.tracks.keys())
        track_centroids = []
        for tid in track_ids:
            _, cx, cy, _ = self.tracks[tid].history[-1]
            track_centroids.append((cx, cy))

        obs_centroids = []
        for obs in obstacles:
            xmin, ymin, xmax, ymax = obs.bbox
            obs_centroids.append(((xmin + xmax) / 2.0, (ymin + ymax) / 2.0))

        # Greedy distance matching
        matched_tracks = set()
        matched_obs = set()

        for obs_idx, (ox, oy) in enumerate(obs_centroids):
            obs = obstacles[obs_idx]
            best_tid = None
            min_dist = float("inf")

            for t_idx, tid in enumerate(track_ids):
                if tid in matched_tracks:
                    continue
                # Only match obstacles with compatible labels
                if self.tracks[tid].label != obs.label:
                    continue

                tx, ty = track_centroids[t_idx]
                dist = np.hypot(ox - tx, oy - ty)
                if dist < min_dist and dist <= self.max_match_dist_px:
                    min_dist = dist
                    best_tid = tid

            if best_tid is not None:
                matched_tracks.add(best_tid)
                matched_obs.add(obs_idx)
                track = self.tracks[best_tid]
                track.update(obs, now)
                obs.tracking_id = best_tid
                obs.is_moving = track.is_moving
                obs.velocity_mps = track.velocity_mps
                obs.state = track.state

                # Elevate urgency if vehicle is moving towards user
                if track.is_moving and track.velocity_mps > 0.4:
                    if obs.in_walking_lane:
                        obs.urgency = "critical"
                    else:
                        obs.urgency = "high"
                elif track.state == "parked" and obs.urgency == "critical":
                    obs.urgency = "high"

        # Initialize unmatched obstacles as new tracks
        for obs_idx, obs in enumerate(obstacles):
            if obs_idx not in matched_obs:
                tid = self.next_id
                self.next_id += 1
                new_track = TrackedObject(tid, obs, now)
                self.tracks[tid] = new_track
                obs.tracking_id = tid
                obs.is_moving = new_track.is_moving
                obs.velocity_mps = new_track.velocity_mps
                obs.state = new_track.state
