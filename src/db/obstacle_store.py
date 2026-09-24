"""
ObstacleStore: Synchronous SQLite persistence layer for CampusEcho's shared
obstacle database. Handles upsert, retrieval, exponential decay, and pruning.
"""
import math
import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from src.decision.hazard_memory import HazardRecord
from .schema import DEFAULT_DB_PATH, db_init


class ObstacleStore:
    """
    Thread-safe SQLite obstacle persistence using WAL mode.
    Each method opens a short-lived connection to avoid blocking.
    """

    STALE_FLOOR_FRACTION = 0.05

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(DEFAULT_DB_PATH)
        db_init(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def upsert(self, record: HazardRecord) -> None:
        """
        Inserts or updates a hazard record. If an obstacle_id already exists,
        refreshes last_confirmed and active_weight.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO obstacles
                    (obstacle_id, edge_id, label, confidence, initial_weight,
                     active_weight, decay_tau_s, first_seen, last_confirmed, reported_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(obstacle_id) DO UPDATE SET
                    last_confirmed = excluded.last_confirmed,
                    active_weight  = excluded.active_weight,
                    confidence     = MAX(confidence, excluded.confidence)
                """,
                (
                    record.obstacle_id,
                    record.edge_id,
                    record.label,
                    record.confidence,
                    record.initial_weight,
                    record.active_weight,
                    record.decay_tau_s,
                    record.first_seen,
                    record.last_confirmed,
                    record.reported_by,
                ),
            )

    def get_active(self, threshold_fraction: float = 0.05) -> List[HazardRecord]:
        """
        Retrieves all obstacles whose active_weight is above the stale floor.
        The floor is threshold_fraction × initial_weight.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM obstacles
                WHERE active_weight >= (initial_weight * ?)
                ORDER BY last_confirmed DESC
                """,
                (threshold_fraction,),
            ).fetchall()

        return [self._row_to_record(r) for r in rows]

    def decay_tick(self, now: Optional[float] = None) -> List[str]:
        """
        Applies exponential decay to all records in the database.
        Removes records that have decayed below the stale floor.
        Returns list of obstacle_ids that were pruned.
        """
        current_time = now or time.time()
        pruned_ids: List[str] = []

        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM obstacles").fetchall()
            for row in rows:
                obstacle_id = row["obstacle_id"]
                delta_t = current_time - row["last_confirmed"]
                tau = row["decay_tau_s"]
                initial_w = row["initial_weight"]
                decayed = initial_w * math.exp(-delta_t / tau)
                floor = initial_w * self.STALE_FLOOR_FRACTION

                if decayed < floor:
                    conn.execute("DELETE FROM obstacles WHERE obstacle_id = ?", (obstacle_id,))
                    pruned_ids.append(obstacle_id)
                else:
                    conn.execute(
                        "UPDATE obstacles SET active_weight = ? WHERE obstacle_id = ?",
                        (round(decayed, 3), obstacle_id),
                    )

        return pruned_ids

    def remove(self, obstacle_id: str) -> bool:
        """Manually remove an obstacle (e.g., path confirmed clear by user)."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM obstacles WHERE obstacle_id = ?", (obstacle_id,)
            )
            return cursor.rowcount > 0

    def clear_edge(self, edge_id: str) -> int:
        """Removes all obstacles on a given edge. Returns count removed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM obstacles WHERE edge_id = ?", (edge_id,)
            )
            return cursor.rowcount

    def clear_all(self) -> None:
        """Wipes all obstacle records (for testing)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM obstacles")

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM obstacles").fetchone()[0]

    @staticmethod
    def _row_to_record(row) -> HazardRecord:
        return HazardRecord(
            obstacle_id=row["obstacle_id"],
            edge_id=row["edge_id"],
            label=row["label"],
            confidence=row["confidence"],
            initial_weight=row["initial_weight"],
            active_weight=row["active_weight"],
            decay_tau_s=row["decay_tau_s"],
            first_seen=row["first_seen"],
            last_confirmed=row["last_confirmed"],
            reported_by=row["reported_by"],
        )
