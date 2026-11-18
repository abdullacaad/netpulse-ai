"""SQLite storage layer for NetPulse AI.

Provides unified database access for telemetry measurements.
No other module should write SQL directly.
"""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Union

DEFAULT_DB_PATH = Path("data/netpulse.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    latency_ms REAL,
    loss_pct REAL,
    status TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_measurements_target_time 
    ON measurements (target_id, timestamp, target_type);

CREATE INDEX IF NOT EXISTS idx_measurements_timestamp 
    ON measurements (timestamp);
"""


def _resolve_path(path: Optional[Union[str, Path]] = None) -> Union[str, Path]:
    """Resolve database path, defaulting to DEFAULT_DB_PATH."""
    if path is None:
        return DEFAULT_DB_PATH
    return path


def _to_utc_iso(v: Union[str, datetime]) -> str:
    """Normalise timestamp string or datetime object to UTC ISO-8601 string.

    Naive timestamps are treated as UTC.
    """
    if isinstance(v, str):
        v = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.astimezone(timezone.utc).isoformat()


def get_connection(path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Open and return a SQLite connection with Row factory configured.

    Automatically creates parent directory if necessary.
    In-memory databases (':memory:') are not supported and raise ValueError.
    """
    resolved = _resolve_path(path)
    if resolved == ":memory:":
        raise ValueError("In-memory SQLite databases (':memory:') are not supported; use a file path.")

    p = Path(resolved)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def _open(path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Open a SQLite connection in WAL mode and ensure schema is initialized."""
    conn = get_connection(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL)
    return conn


def init_db(path: Optional[Union[str, Path]] = None) -> None:
    """Initialize SQLite database schema and indexes."""
    conn = _open(path)
    conn.close()


def insert_measurements(
    rows: List[Dict[str, Any]],
    path: Optional[Union[str, Path]] = None,
) -> int:
    """Insert telemetry measurement rows into the database.

    Inserts are idempotent using INSERT OR IGNORE based on unique constraint
    (target_id, timestamp, target_type).

    Args:
        rows: List of dicts with keys:
              timestamp, target_type, target_id, latency_ms, loss_pct, status.
        path: Optional database path. Defaults to DEFAULT_DB_PATH.

    Returns:
        Number of rows actually inserted.
    """
    if not rows:
        return 0

    conn = _open(path)
    insert_sql = """
    INSERT OR IGNORE INTO measurements (
        timestamp, target_type, target_id, latency_ms, loss_pct, status
    ) VALUES (
        :timestamp, :target_type, :target_id, :latency_ms, :loss_pct, :status
    )
    """
    try:
        with conn:
            before = conn.total_changes
            prepared = [
                {
                    "timestamp": _to_utc_iso(r["timestamp"]),
                    "target_type": str(r["target_type"]),
                    "target_id": str(r["target_id"]),
                    "latency_ms": r.get("latency_ms"),
                    "loss_pct": r.get("loss_pct"),
                    "status": str(r["status"]),
                }
                for r in rows
            ]
            conn.executemany(insert_sql, prepared)
            return conn.total_changes - before
    finally:
        conn.close()


def query_measurements(
    target_id: Optional[str] = None,
    start: Optional[Union[str, datetime]] = None,
    end: Optional[Union[str, datetime]] = None,
    path: Optional[Union[str, Path]] = None,
    order: str = "ASC",
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Query telemetry measurements with optional target_id, timestamp filtering, ordering, and limit.

    Args:
        target_id: Filter by target identifier (node or link ID).
        start: Earliest timestamp (inclusive), as ISO string or datetime.
        end: Latest timestamp (inclusive), as ISO string or datetime.
        path: Optional database path. Defaults to DEFAULT_DB_PATH.
        order: Sort order by timestamp ('ASC' or 'DESC'). Default 'ASC'.
        limit: Optional maximum number of rows to return.

    Returns:
        List of measurement dicts ordered by timestamp, id.
    """
    conn = _open(path)
    query = ["SELECT id, timestamp, target_type, target_id, latency_ms, loss_pct, status FROM measurements"]
    conditions = []
    params: List[Any] = []

    if target_id is not None:
        conditions.append("target_id = ?")
        params.append(str(target_id))

    if start is not None:
        conditions.append("timestamp >= ?")
        params.append(_to_utc_iso(start))

    if end is not None:
        conditions.append("timestamp <= ?")
        params.append(_to_utc_iso(end))

    if conditions:
        query.append("WHERE " + " AND ".join(conditions))

    sort_order = "DESC" if str(order).strip().upper() == "DESC" else "ASC"
    query.append(f"ORDER BY timestamp {sort_order}, id {sort_order}")

    if limit is not None:
        query.append("LIMIT ?")
        params.append(int(limit))

    full_sql = " ".join(query)

    try:
        cursor = conn.cursor()
        cursor.execute(full_sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
