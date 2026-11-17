"""Automated tests for NetPulse AI SQLite storage layer (database/db.py)."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import sqlite3
import pytest

from database.db import (
    DEFAULT_DB_PATH,
    get_connection,
    init_db,
    insert_measurements,
    query_measurements,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Fixture providing a temporary SQLite database file path."""
    return tmp_path / "test_netpulse.db"


def test_init_db_creates_table_and_indexes(temp_db: Path):
    """Verify init_db creates measurements table and index structures in WAL mode."""
    init_db(temp_db)
    conn = get_connection(temp_db)
    try:
        cursor = conn.cursor()
        # Verify WAL mode
        cursor.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0].lower() == "wal"

        # Verify table existence
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='measurements'")
        assert cursor.fetchone() is not None

        # Verify columns
        cursor.execute("PRAGMA table_info(measurements)")
        columns = {row["name"]: row["type"] for row in cursor.fetchall()}
        expected = {
            "id": "INTEGER",
            "timestamp": "TEXT",
            "target_type": "TEXT",
            "target_id": "TEXT",
            "latency_ms": "REAL",
            "loss_pct": "REAL",
            "status": "TEXT",
        }
        for col, col_type in expected.items():
            assert col in columns
            assert columns[col] == col_type

        # Verify indexes (including unique index on target_id, timestamp, target_type)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        index_names = {row["name"] for row in cursor.fetchall()}
        assert "idx_measurements_target_time" in index_names
        assert "idx_measurements_timestamp" in index_names
    finally:
        conn.close()


def test_insert_empty_returns_zero(temp_db: Path):
    """Verify insert_measurements on empty list returns 0 without error."""
    assert insert_measurements([], temp_db) == 0


def test_insert_and_query_measurements_round_trip(temp_db: Path):
    """Verify inserting and querying measurements returns expected data."""
    sample_rows = [
        {
            "timestamp": "2026-11-18T01:00:00+00:00",
            "target_type": "node",
            "target_id": "core_1",
            "latency_ms": 1.05,
            "loss_pct": 0.0,
            "status": "up",
        },
        {
            "timestamp": "2026-11-18T01:00:00+00:00",
            "target_type": "link",
            "target_id": "core_1-dist_1",
            "latency_ms": 15.2,
            "loss_pct": 0.1,
            "status": "up",
        },
    ]

    count = insert_measurements(sample_rows, temp_db)
    assert count == 2

    results = query_measurements(path=temp_db)
    assert len(results) == 2

    # Check fields
    r0 = results[0]
    assert r0["id"] == 1
    assert r0["timestamp"] == "2026-11-18T01:00:00+00:00"
    assert r0["target_type"] == "node"
    assert r0["target_id"] == "core_1"
    assert r0["latency_ms"] == pytest.approx(1.05)
    assert r0["loss_pct"] == pytest.approx(0.0)
    assert r0["status"] == "up"

    r1 = results[1]
    assert r1["id"] == 2
    assert r1["target_type"] == "link"
    assert r1["target_id"] == "core_1-dist_1"


def test_insert_idempotent_duplicate_batch_stored_once(temp_db: Path):
    """Verify inserting the exact same batch twice stores it once and returns 0 on duplicate."""
    sample_rows = [
        {
            "timestamp": "2026-11-18T01:00:00Z",
            "target_type": "node",
            "target_id": "core_1",
            "latency_ms": 1.05,
            "loss_pct": 0.0,
            "status": "up",
        },
        {
            "timestamp": "2026-11-18T01:00:00Z",
            "target_type": "link",
            "target_id": "core_1-dist_1",
            "latency_ms": 15.2,
            "loss_pct": 0.1,
            "status": "up",
        },
    ]

    # First insert stores 2 rows
    inserted_first = insert_measurements(sample_rows, temp_db)
    assert inserted_first == 2

    # Second insert of identical batch is ignored (idempotent)
    inserted_second = insert_measurements(sample_rows, temp_db)
    assert inserted_second == 0

    # Total rows in DB remain 2
    all_rows = query_measurements(path=temp_db)
    assert len(all_rows) == 2


def test_timestamp_normalization_to_utc_iso(temp_db: Path):
    """Verify naive, Z-suffix, and offset timestamps are all normalised to UTC ISO strings."""
    rows = [
        # Naive string -> treated as UTC
        {"timestamp": "2026-11-18T01:00:00", "target_type": "node", "target_id": "n1", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"},
        # Z suffix -> normalised to +00:00
        {"timestamp": "2026-11-18T02:00:00Z", "target_type": "node", "target_id": "n2", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"},
        # Offset +05:00 (07:00:00+05:00 == 02:00:00 UTC, but different node)
        {"timestamp": "2026-11-18T07:00:00+05:00", "target_type": "node", "target_id": "n3", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"},
    ]
    insert_measurements(rows, temp_db)

    results = query_measurements(path=temp_db)
    assert len(results) == 3
    assert results[0]["timestamp"] == "2026-11-18T01:00:00+00:00"
    assert results[1]["timestamp"] == "2026-11-18T02:00:00+00:00"
    assert results[2]["timestamp"] == "2026-11-18T02:00:00+00:00"

    # Query with naive bounds matches normalised UTC
    res_naive = query_measurements(start="2026-11-18T01:30:00", path=temp_db)
    assert len(res_naive) == 2


def test_query_filter_by_target_id(temp_db: Path):
    """Verify query_measurements filters accurately by target_id."""
    rows = [
        {"timestamp": "2026-11-18T01:00:00Z", "target_type": "node", "target_id": "dist_1", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"},
        {"timestamp": "2026-11-18T01:00:00Z", "target_type": "node", "target_id": "dist_2", "latency_ms": 1.1, "loss_pct": 0.0, "status": "up"},
        {"timestamp": "2026-11-18T01:00:10Z", "target_type": "node", "target_id": "dist_1", "latency_ms": 1.2, "loss_pct": 0.0, "status": "up"},
    ]
    insert_measurements(rows, temp_db)

    dist1_results = query_measurements(target_id="dist_1", path=temp_db)
    assert len(dist1_results) == 2
    assert all(r["target_id"] == "dist_1" for r in dist1_results)

    dist2_results = query_measurements(target_id="dist_2", path=temp_db)
    assert len(dist2_results) == 1
    assert dist2_results[0]["target_id"] == "dist_2"

    none_results = query_measurements(target_id="nonexistent", path=temp_db)
    assert len(none_results) == 0


def test_query_filter_by_time_range_strings(temp_db: Path):
    """Verify query_measurements filters by start and end timestamp strings."""
    rows = [
        {"timestamp": "2026-11-18T01:00:00+00:00", "target_type": "node", "target_id": "core_1", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"},
        {"timestamp": "2026-11-18T01:00:10+00:00", "target_type": "node", "target_id": "core_1", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"},
        {"timestamp": "2026-11-18T01:00:20+00:00", "target_type": "node", "target_id": "core_1", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"},
        {"timestamp": "2026-11-18T01:00:30+00:00", "target_type": "node", "target_id": "core_1", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"},
    ]
    insert_measurements(rows, temp_db)

    # Start filter only
    res_start = query_measurements(start="2026-11-18T01:00:15+00:00", path=temp_db)
    assert len(res_start) == 2
    assert [r["timestamp"] for r in res_start] == [
        "2026-11-18T01:00:20+00:00",
        "2026-11-18T01:00:30+00:00",
    ]

    # End filter only
    res_end = query_measurements(end="2026-11-18T01:00:15+00:00", path=temp_db)
    assert len(res_end) == 2
    assert [r["timestamp"] for r in res_end] == [
        "2026-11-18T01:00:00+00:00",
        "2026-11-18T01:00:10+00:00",
    ]

    # Both start and end
    res_window = query_measurements(
        start="2026-11-18T01:00:10+00:00",
        end="2026-11-18T01:00:20+00:00",
        path=temp_db,
    )
    assert len(res_window) == 2


def test_query_filter_by_datetime_objects(temp_db: Path):
    """Verify query_measurements accepts datetime objects for start and end."""
    base = datetime(2026, 11, 18, 1, 0, 0, tzinfo=timezone.utc)
    rows = [
        {"timestamp": (base + timedelta(seconds=i * 10)).isoformat(), "target_type": "node", "target_id": "core_1", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"}
        for i in range(4)
    ]
    insert_measurements(rows, temp_db)

    start_dt = base + timedelta(seconds=10)
    end_dt = base + timedelta(seconds=20)

    res = query_measurements(start=start_dt, end=end_dt, path=temp_db)
    assert len(res) == 2
    assert res[0]["timestamp"] == (base + timedelta(seconds=10)).isoformat()
    assert res[1]["timestamp"] == (base + timedelta(seconds=20)).isoformat()


def test_query_ordering_is_chronological(temp_db: Path):
    """Verify query results are ordered by timestamp ASC, id ASC."""
    rows = [
        {"timestamp": "2026-11-18T01:00:20Z", "target_type": "node", "target_id": "A", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"},
        {"timestamp": "2026-11-18T01:00:10Z", "target_type": "node", "target_id": "B", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"},
        {"timestamp": "2026-11-18T01:00:10Z", "target_type": "node", "target_id": "C", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"},
    ]
    insert_measurements(rows, temp_db)

    res = query_measurements(path=temp_db)
    assert [r["target_id"] for r in res] == ["B", "C", "A"]


def test_insert_datetime_object_in_row(temp_db: Path):
    """Verify insert_measurements converts row datetime objects to ISO strings."""
    dt = datetime(2026, 11, 18, 2, 30, 0, tzinfo=timezone.utc)
    rows = [
        {"timestamp": dt, "target_type": "node", "target_id": "dist_1", "latency_ms": 1.0, "loss_pct": 0.0, "status": "up"}
    ]
    insert_measurements(rows, temp_db)

    res = query_measurements(path=temp_db)
    assert len(res) == 1
    assert res[0]["timestamp"] == dt.isoformat()


def test_auto_creates_parent_directory(tmp_path: Path):
    """Verify get_connection creates non-existent parent directories."""
    deep_path = tmp_path / "deep" / "nested" / "subfolder" / "netpulse.db"
    assert not deep_path.parent.exists()

    init_db(deep_path)
    assert deep_path.exists()


def test_reject_memory_path():
    """Verify get_connection rejects ':memory:' with a clear ValueError."""
    with pytest.raises(ValueError, match="In-memory SQLite databases"):
        get_connection(":memory:")
