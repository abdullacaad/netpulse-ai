"""Automated tests for NetPulse AI telemetry collector (monitoring/collector.py)."""

import logging
from pathlib import Path
import time
import pytest

from database.db import query_measurements
from monitoring.collector import Collector
from network.simulator import Simulator


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Fixture providing a temporary SQLite database path."""
    return tmp_path / "test_collector.db"


def test_collector_init(temp_db: Path):
    """Verify collector initialization and configuration defaults."""
    sim = Simulator(seed=42)
    collector = Collector(simulator=sim, poll_interval=2.5, db_path=temp_db)

    assert collector.simulator is sim
    assert collector.poll_interval == 2.5
    assert collector.db_path == temp_db
    assert temp_db.exists()


def test_collect_once_stores_simulator_measurements(temp_db: Path):
    """Verify collect_once polls simulator and writes all measurements to DB."""
    sim = Simulator(seed=42, base_time="2026-11-18T00:00:00Z")
    collector = Collector(simulator=sim, poll_interval=1.0, db_path=temp_db)

    rows = collector.collect_once()
    assert len(rows) == 59  # 30 nodes + 29 links

    # Read back from database
    stored = query_measurements(path=temp_db)
    assert len(stored) == 59

    # Verify individual target measurements match between returned and stored
    stored_by_target = {r["target_id"]: r for r in stored}
    for row in rows:
        tid = row["target_id"]
        assert tid in stored_by_target
        s = stored_by_target[tid]
        assert s["timestamp"] == row["timestamp"]
        assert s["target_type"] == row["target_type"]
        assert s["status"] == row["status"]
        assert s["latency_ms"] == pytest.approx(row["latency_ms"])
        assert s["loss_pct"] == pytest.approx(row["loss_pct"])


def test_collect_once_accumulates_history(temp_db: Path):
    """Verify consecutive collect_once calls accumulate historical measurements."""
    sim = Simulator(seed=42, base_time="2026-11-18T00:00:00Z", step_interval_seconds=10)
    collector = Collector(simulator=sim, poll_interval=1.0, db_path=temp_db)

    collector.collect_once()
    collector.collect_once()
    collector.collect_once()

    stored = query_measurements(path=temp_db)
    assert len(stored) == 59 * 3

    # Query specific target history
    core_link_history = query_measurements(target_id="core_1-core_2", path=temp_db)
    assert len(core_link_history) == 3
    # Verify timestamps are chronological
    ts_list = [r["timestamp"] for r in core_link_history]
    assert ts_list == sorted(ts_list)


def test_collector_records_injected_faults(temp_db: Path):
    """Verify collector accurately records injected faults in SQLite history."""
    sim = Simulator(seed=42, base_time="2026-11-18T00:00:00Z")
    collector = Collector(simulator=sim, poll_interval=1.0, db_path=temp_db)

    # 1. Normal baseline poll
    collector.collect_once()

    # 2. Inject congestion and node_down
    sim.inject_fault("congestion", ("core_1", "dist_1"), duration=2)
    sim.inject_fault("node_down", "dist_2", duration=2)

    # 3. Faulty poll
    collector.collect_once()

    # Verify congestion in database
    cong_rows = query_measurements(target_id="core_1-dist_1", path=temp_db)
    assert len(cong_rows) == 2
    assert cong_rows[0]["latency_ms"] == pytest.approx(15.0, abs=3.0)  # Baseline
    assert cong_rows[1]["latency_ms"] > 60.0  # Congestion (~5x)
    assert cong_rows[1]["status"] == "up"

    # Verify node_down in database
    down_node_rows = query_measurements(target_id="dist_2", path=temp_db)
    assert len(down_node_rows) == 2
    assert down_node_rows[0]["status"] == "up"
    assert down_node_rows[1]["status"] == "down"
    assert down_node_rows[1]["loss_pct"] == 100.0


def test_collector_error_resilience_on_failed_poll(temp_db: Path, caplog: pytest.LogCaptureFixture):
    """Verify collector catches simulator errors, logs them, and does not crash."""
    class BrokenSimulator:
        def tick(self):
            raise RuntimeError("Hardware connection lost or simulator failure")

    collector = Collector(simulator=BrokenSimulator(), poll_interval=1.0, db_path=temp_db)

    with caplog.at_level(logging.ERROR, logger="netpulse.collector"):
        rows = collector.collect_once()

    # Must return empty list instead of crashing
    assert rows == []
    # Must have logged the error
    assert any("Error during telemetry collection poll" in record.message for record in caplog.records)
    # Database remains empty
    assert len(query_measurements(path=temp_db)) == 0


def test_collector_run_loops_for_fixed_duration(temp_db: Path):
    """Verify run() executes repeated polls for approximately duration_seconds."""
    sim = Simulator(seed=42)
    collector = Collector(simulator=sim, poll_interval=0.05, db_path=temp_db)

    start = time.monotonic()
    total_polls = collector.run(duration_seconds=0.25)
    elapsed = time.monotonic() - start

    assert total_polls >= 3
    assert elapsed >= 0.20

    stored = query_measurements(path=temp_db)
    assert len(stored) == 59 * total_polls


def test_collector_stop_terminates_run(temp_db: Path):
    """Verify stop() method terminates run() loop early."""
    sim = Simulator(seed=42)
    collector = Collector(simulator=sim, poll_interval=0.05, db_path=temp_db)

    # Immediately stop
    collector.stop()
    polls = collector.run(duration_seconds=5.0)
    assert polls == 0


def test_collector_run_resilient_to_intermittent_error(temp_db: Path, caplog: pytest.LogCaptureFixture):
    """Verify run loop continues collecting after an intermittent poll failure."""
    class IntermittentSimulator:
        def __init__(self):
            self.count = 0
            self.sim = Simulator(seed=42)

        def tick(self):
            self.count += 1
            if self.count == 2:
                raise RuntimeError("Transient glitch on tick 2")
            return self.sim.tick()

    intermittent_sim = IntermittentSimulator()
    collector = Collector(simulator=intermittent_sim, poll_interval=0.02, db_path=temp_db)

    with caplog.at_level(logging.ERROR, logger="netpulse.collector"):
        total_polls = collector.run(duration_seconds=0.15)

    assert total_polls >= 3
    # At least one error logged for tick 2
    assert any("Transient glitch" in record.message for record in caplog.records)
    # Successful polls stored data in DB
    stored = query_measurements(path=temp_db)
    assert len(stored) >= 59 * 2
