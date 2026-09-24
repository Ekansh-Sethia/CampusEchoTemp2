"""
SQLite schema and initialization for CampusEcho's shared obstacle database.
Uses WAL journal mode for safe concurrent multi-user access.
"""
import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "obstacles.db"


CREATE_OBSTACLES_TABLE = """
CREATE TABLE IF NOT EXISTS obstacles (
    obstacle_id   TEXT PRIMARY KEY,
    edge_id       TEXT NOT NULL,
    label         TEXT NOT NULL,
    confidence    REAL NOT NULL,
    initial_weight REAL NOT NULL DEFAULT 300.0,
    active_weight REAL NOT NULL DEFAULT 300.0,
    decay_tau_s   REAL NOT NULL DEFAULT 90.0,
    first_seen    REAL NOT NULL,
    last_confirmed REAL NOT NULL,
    reported_by   TEXT NOT NULL DEFAULT 'local'
);
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_obstacles_edge ON obstacles(edge_id);
"""


def db_init(db_path: str = str(DEFAULT_DB_PATH)) -> None:
    """
    Initializes the SQLite database and creates required tables.
    Enables WAL journal mode for concurrent read/write access by multiple users.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(CREATE_OBSTACLES_TABLE)
        conn.execute(CREATE_INDEX)
        conn.commit()
    finally:
        conn.close()
