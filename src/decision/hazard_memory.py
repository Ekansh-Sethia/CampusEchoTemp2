"""
Hazard Memory: In-memory exponential decay model for obstacle persistence.
Tracks confirmed hazards, decays their weights over time, and syncs with
the campus graph edge penalties.
"""
import math
import time
import uuid
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class HazardRecord(BaseModel):
    """A single hazard entry tracked in memory."""
    obstacle_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    edge_id: str                          # Graph edge ID this hazard blocks
    label: str                            # Obstacle class (e.g., 'pothole', 'car')
    confidence: float                     # Original detection confidence
    first_seen: float                     # Unix timestamp of first detection
    last_confirmed: float                 # Unix timestamp of most recent confirmation
    decay_tau_s: float = 90.0            # Exponential decay time constant (seconds)
    active_weight: float = 300.0         # Current penalty weight applied to edge
    initial_weight: float = 300.0        # Starting penalty weight
    reported_by: str = "local"           # User/device that reported the obstacle


class HazardMemory:
    """
    In-memory store for confirmed hazard records with exponential time decay.

    Decay formula: W(t) = W_initial × e^(−Δt / τ)
    where Δt = time since last_confirmed, τ = decay_tau_s.

    When W(t) < floor (0.05 × W_initial), hazard is considered stale and is removed.
    """

    STALE_FLOOR_FRACTION = 0.05   # Below 5% of initial weight → stale

    def __init__(self):
        self._records: Dict[str, HazardRecord] = {}   # {obstacle_id: HazardRecord}
        # Callback invoked on each record update: (obstacle_id, new_weight) → None
        self._weight_changed_callbacks = []

    def on_weight_changed(self, callback):
        """Register a callback invoked when a hazard weight changes."""
        self._weight_changed_callbacks.append(callback)

    def _notify(self, obstacle_id: str, record: HazardRecord):
        for cb in self._weight_changed_callbacks:
            cb(obstacle_id, record)

    def add_or_refresh(
        self,
        edge_id: str,
        label: str,
        confidence: float,
        decay_tau_s: float = 90.0,
        penalty_weight: float = 300.0,
        reported_by: str = "local",
        obstacle_id: Optional[str] = None,
    ) -> HazardRecord:
        """
        Adds a new hazard record or refreshes an existing one if it's on the same edge and label.
        Refreshing resets last_confirmed, restoring the weight to initial_weight.
        """
        now = time.time()

        # Check for existing record on same edge+label to refresh
        existing = self._find_existing(edge_id, label)
        if existing:
            existing.last_confirmed = now
            existing.active_weight = penalty_weight
            existing.initial_weight = penalty_weight
            existing.confidence = max(existing.confidence, confidence)
            self._notify(existing.obstacle_id, existing)
            return existing

        # New record
        record = HazardRecord(
            obstacle_id=obstacle_id or (str(uuid.uuid4())[:8]),
            edge_id=edge_id,
            label=label,
            confidence=confidence,
            first_seen=now,
            last_confirmed=now,
            decay_tau_s=decay_tau_s,
            active_weight=penalty_weight,
            initial_weight=penalty_weight,
            reported_by=reported_by,
        )
        self._records[record.obstacle_id] = record
        self._notify(record.obstacle_id, record)
        return record

    def _find_existing(self, edge_id: str, label: str) -> Optional[HazardRecord]:
        """Find an existing live record on the same edge and label."""
        for rec in self._records.values():
            if rec.edge_id == edge_id and rec.label == label:
                return rec
        return None

    def decay_all(self, now: Optional[float] = None) -> List[str]:
        """
        Applies exponential decay to all active records.
        Returns list of obstacle_ids that have become stale and been removed.
        """
        current_time = now or time.time()
        stale_ids = []

        for obstacle_id, record in list(self._records.items()):
            delta_t = current_time - record.last_confirmed
            decayed = record.initial_weight * math.exp(-delta_t / record.decay_tau_s)
            floor = record.initial_weight * self.STALE_FLOOR_FRACTION

            if decayed < floor:
                stale_ids.append(obstacle_id)
                del self._records[obstacle_id]
            else:
                record.active_weight = round(decayed, 3)
                self._notify(obstacle_id, record)

        return stale_ids

    def get_active_hazards(self) -> List[HazardRecord]:
        """Returns all currently active hazard records."""
        return list(self._records.values())

    def get_record(self, obstacle_id: str) -> Optional[HazardRecord]:
        return self._records.get(obstacle_id)

    def remove(self, obstacle_id: str) -> bool:
        """Manually remove a hazard (e.g., user confirms path is clear)."""
        if obstacle_id in self._records:
            del self._records[obstacle_id]
            return True
        return False

    def clear(self):
        """Clear all hazard records."""
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)
