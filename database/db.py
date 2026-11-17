"""SQLite storage layer for NetPulse AI.

Provides unified database access for telemetry measurements.
No other module should write SQL directly.
"""

from datetime import datetime
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

CREATE INDEX IF NOT EXISTS idx_measurements_target_time 
    ON measurements (target_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_measurements_timestamp 
    ON measurements (timestamp);
"""


def _resolve_path(path: Optional[Union[str, Path]] = None) -> Union[str, Path]:
    """Resolve database path, defaulting to DEFAULT_DB_PATH."""
    if path is None:
        return DEFAULT_DB_PATH
    return path


def get_connection(path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Open and return a SQLite connection with Row factory configured.

    Automatically creates parent directory if necessary.
    """
    resolved = _resolve_path(path)
    if isinstance(resolved, Path) or (
        isinstance(resolved, str) and resolved != ":memory:"
    ):
        p = Path(resolved)
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p))
    else:
        conn = sqlite3.connect(str(resolved))

    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Optional[Union[str, Path]] = None) -> None:
    """Initialize SQLite database schema and indexes."""
    conn = get_connection(path)
    try:
        with conn:
            conn.executescript(SCHEMA_SQL)
    finally:
        conn.close()


def insert_measurements(
    rows: List[Dict[str, Any]],
    path: Optional[Union[str, Path]] = None,
) -> int:
    """Insert telemetry measurement rows into the database.

    Args:
        rows: List of dicts with keys:
              timestamp, target_type, target_id, latency_ms, loss_pct, status.
        path: Optional database path. Defaults to DEFAULT_DB_PATH.

    Returns:
        Number of rows inserted.
    """
    if not rows:
        return 0

    init_db(path)
    conn = get_connection(path)
    insert_sql = """
    INSERT INTO measurements (
        timestamp, target_type, target_id, latency_ms, loss_pct, status
    ) VALUES (
        :timestamp, :target_type, :target_id, :latency_ms, :loss_pct, :status
    )
    """
    try:
        with conn:
            # Prepare rows, ensuring timestamp is string format
            prepared = []
            for r in rows:
                ts = r["timestamp"]
                if isinstance(ts, datetime):
                    ts = ts.isoformat()
                prepared.append(
                    {
                        "timestamp": str(ts),
                        "target_type": str(r["target_type"]),
                        "target_id": str(r["target_id"]),
                        "latency_ms": r.get("latency_ms"),
                        "loss_pct": r.get("loss_pct"),
                        "status": str(r["status"]),
                    }
                )
            cursor = conn.executemany(insert_sql, prepared)
            return cursor.rowcount
    finally:
        conn.close()


def query_measurements(
    target_id: Optional[str] = None,
    start: Optional[Union[str, datetime]] = None,
    end: Optional[Union[str, datetime]] = None,
    path: Optional[Union[str, Path]] = None,
) -> List[Dict[str, Any]]:
    """Query telemetry measurements with optional target_id and timestamp filtering.

    Args:
        target_id: Filter by target identifier (node or link ID).
        start: Earliest timestamp (inclusive), as ISO string or datetime.
        end: Latest timestamp (inclusive), as ISO string or datetime.
        path: Optional database path. Defaults to DEFAULT_DB_PATH.

    Returns:
        List of measurement dicts ordered by timestamp ASC, id ASC.
    """
    init_db(path)
    conn = get_connection(path)

    query = ["SELECT id, timestamp, target_type, target_id, latency_ms, loss_pct, status FROM measurements"]
    conditions = []
    params: List[Any] = []

    if target_id is not None:
        conditions.append("target_id = ?")
        params.append(str(target_id))

    if start is not None:
        start_str = start.isoformat() if isinstance(start, datetime) else str(start)
        conditions.append("timestamp >= ?")
        params.append(start_str)

    if end is not None:
        end_str = end.isoformat() if isinstance(end, datetime) else str(end)
        conditions.append("timestamp <= ?")
        params.append(end_str)

    if conditions:
        query.append("WHERE " + " AND ".join(conditions))

    query.append("ORDER BY timestamp ASC, id ASC")
    full_sql = " ".join(query)

    try:
        cursor = conn.cursor()
        cursor.execute(full_sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
