"""Database module for CampusEcho's shared obstacle persistence."""
from .schema import db_init, DEFAULT_DB_PATH
from .obstacle_store import ObstacleStore

__all__ = ["db_init", "DEFAULT_DB_PATH", "ObstacleStore"]
