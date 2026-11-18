"""Automated test suite for NetPulse AI latency and packet-loss monitoring (Issue #3)."""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from database.db import insert_measurements, query_measurements
from monitoring.collector import Collector
from monitoring.monitor import NetworkMonitor
from monitoring.rules import (
    Breach,
    ThresholdConfig,
    evaluate_measurement,
    get_target_tier,
)
from monitoring.trends import RollingTrendTracker
from network.simulator import Simulator


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Fixture providing a temporary SQLite database path."""
    return tmp_path / "test_monitor.db"


# ============================================================================
# 1. Threshold Rules & Tier Inference Tests
# ============================================================================


def test_get_target_tier_inference():
    """Verify get_target_tier accurately categorizes nodes and links into tiers."""
    assert get_target_tier("core_1", "node") == "core"
    assert get_target_tier("core_2", "node") == "core"
    assert get_target_tier("dist_1", "node") == "distribution"
    assert get_target_tier("access_3", "node") == "access"
    assert get_target_tier("cust_5", "node") == "customer"

    assert get_target_tier("core_1-core_2", "link") == "core"
    assert get_target_tier("core_1-dist_1", "link") == "distribution"
    assert get_target_tier("dist_1-access_1", "link") == "access"
    assert get_target_tier("access_1-cust_1", "link") == "customer"


def test_threshold_config_tier_thresholds_and_overrides():
    """Verify ThresholdConfig returns expected defaults per tier and respects overrides."""
    cfg = ThresholdConfig(
        custom_thresholds={
            "custom_link": {"latency_warn_ms": 12.0, "latency_crit_ms": 25.0}
        }
    )

    core_rules = cfg.get_thresholds_for_target("core_1-core_2", "link", "core")
    assert core_rules["latency_warn_ms"] == 10.0
    assert core_rules["latency_crit_ms"] == 20.0
    assert core_rules["loss_warn_pct"] == 2.0
    assert core_rules["loss_crit_pct"] == 5.0

    dist_rules = cfg.get_thresholds_for_target("core_1-dist_1", "link", "distribution")
    assert dist_rules["latency_warn_ms"] == 30.0
    assert dist_rules["latency_crit_ms"] == 60.0

    access_rules = cfg.get_thresholds_for_target("dist_1-access_1", "link", "access")
    assert access_rules["latency_warn_ms"] == 50.0
    assert access_rules["latency_crit_ms"] == 100.0

    node_rules = cfg.get_thresholds_for_target("dist_1", "node", "distribution")
    assert node_rules["latency_warn_ms"] == 5.0
    assert node_rules["latency_crit_ms"] == 10.0

    custom_rules = cfg.get_thresholds_for_target("custom_link", "link")
    assert custom_rules["latency_warn_ms"] == 12.0
    assert custom_rules["latency_crit_ms"] == 25.0


def test_evaluate_measurement_healthy():
    """Verify healthy telemetry produces zero breaches."""
    m = {
        "timestamp": "2026-11-18T12:00:00Z",
        "target_type": "link",
        "target_id": "core_1-dist_1",
        "latency_ms": 15.2,
        "loss_pct": 0.1,
        "status": "up",
    }
    breaches = evaluate_measurement(m)
    assert len(breaches) == 0


def test_evaluate_measurement_latency_warning_and_critical():
    """Verify latency breaches are flagged with correct severity and thresholds."""
    # Distribution baseline ~15ms, warning threshold 30ms, critical 60ms
    m_warn = {
        "timestamp": "2026-11-18T12:00:00Z",
        "target_type": "link",
        "target_id": "core_1-dist_1",
        "latency_ms": 35.0,
        "loss_pct": 0.1,
        "status": "up",
    }
    breaches_warn = evaluate_measurement(m_warn)
    assert len(breaches_warn) == 1
    assert breaches_warn[0].metric == "latency"
    assert breaches_warn[0].severity == "WARNING"
    assert breaches_warn[0].threshold_value == 30.0
    assert breaches_warn[0].current_value == 35.0

    # Critical breach (>= 60ms)
    m_crit = {
        "timestamp": "2026-11-18T12:00:10Z",
        "target_type": "link",
        "target_id": "core_1-dist_1",
        "latency_ms": 75.0,
        "loss_pct": 0.1,
        "status": "up",
    }
    breaches_crit = evaluate_measurement(m_crit)
    assert len(breaches_crit) == 1
    assert breaches_crit[0].metric == "latency"
    assert breaches_crit[0].severity == "CRITICAL"
    assert breaches_crit[0].threshold_value == 60.0
    assert breaches_crit[0].current_value == 75.0


def test_evaluate_measurement_packet_loss_breaches():
    """Verify packet loss triggers warning (>=2%) and critical (>=5%) breaches."""
    m_warn = {
        "timestamp": "2026-11-18T12:00:00Z",
        "target_type": "link",
        "target_id": "dist_1-access_1",
        "latency_ms": 30.0,
        "loss_pct": 3.0,
        "status": "up",
    }
    b_warn = evaluate_measurement(m_warn)
    assert any(b.metric == "packet_loss" and b.severity == "WARNING" for b in b_warn)

    m_crit = {
        "timestamp": "2026-11-18T12:00:10Z",
        "target_type": "link",
        "target_id": "dist_1-access_1",
        "latency_ms": 30.0,
        "loss_pct": 8.0,
        "status": "up",
    }
    b_crit = evaluate_measurement(m_crit)
    assert any(b.metric == "packet_loss" and b.severity == "CRITICAL" for b in b_crit)


def test_evaluate_measurement_status_down():
    """Verify target with status 'down' triggers CRITICAL status and packet_loss breaches."""
    m_down = {
        "timestamp": "2026-11-18T12:00:00Z",
        "target_type": "node",
        "target_id": "dist_1",
        "latency_ms": 0.0,
        "loss_pct": 100.0,
        "status": "down",
    }
    breaches = evaluate_measurement(m_down)
    metrics = {b.metric: b.severity for b in breaches}
    assert metrics.get("status") == "CRITICAL"
    assert metrics.get("packet_loss") == "CRITICAL"


# ============================================================================
# 2. Rolling Trend Tracker Tests
# ============================================================================


def test_rolling_trend_tracker_empty():
    """Verify RollingTrendTracker returns safe defaults for unobserved targets."""
    tracker = RollingTrendTracker(window_size=10)
    trend = tracker.get_trend("unknown_target")
    assert trend["count"] == 0
    assert trend["current_latency_ms"] is None
    assert trend["latency_trend"] == "stable"
    assert trend["history"] == []


def test_rolling_trend_tracker_validates_window_size():
    """Verify rolling window size rejects booleans and non-integer values."""
    with pytest.raises(ValueError, match="positive integer"):
        RollingTrendTracker(window_size=0)
    with pytest.raises(ValueError, match="positive integer"):
        RollingTrendTracker(window_size=True)
    with pytest.raises(ValueError, match="positive integer"):
        RollingTrendTracker(window_size=2.5)


def test_rolling_trend_tracker_window_limit():
    """Verify tracker keeps at most window_size entries in FIFO order."""
    tracker = RollingTrendTracker(window_size=5)
    for i in range(10):
        tracker.add_measurement(
            {
                "timestamp": f"2026-11-18T12:00:{i:02d}Z",
                "target_type": "node",
                "target_id": "core_1",
                "latency_ms": float(i),
                "loss_pct": 0.0,
                "status": "up",
            }
        )

    history = tracker.get_history("core_1")
    assert len(history) == 5
    assert [m["latency_ms"] for m in history] == [5.0, 6.0, 7.0, 8.0, 9.0]


def test_rolling_trend_tracker_statistics():
    """Verify accurate rolling mean, min, max calculation."""
    tracker = RollingTrendTracker(window_size=10)
    latencies = [10.0, 20.0, 30.0, 40.0]
    for lat in latencies:
        tracker.add_measurement(
            {
                "timestamp": "2026-11-18T12:00:00Z",
                "target_type": "link",
                "target_id": "link_1",
                "latency_ms": lat,
                "loss_pct": 0.5,
                "status": "up",
            }
        )

    trend = tracker.get_trend("link_1")
    assert trend["count"] == 4
    assert trend["current_latency_ms"] == 40.0
    assert trend["min_latency_ms"] == 10.0
    assert trend["max_latency_ms"] == 40.0
    assert trend["avg_latency_ms"] == pytest.approx(25.0)


def test_rolling_trend_direction_rising_and_falling():
    """Verify trend direction detection (rising, falling, stable)."""
    tracker = RollingTrendTracker(window_size=10)

    # Rising trend: 10, 10, 10 -> 25, 30, 35
    for lat in [10.0, 10.0, 10.0, 25.0, 30.0, 35.0]:
        tracker.add_measurement(
            {
                "timestamp": "2026-11-18T12:00:00Z",
                "target_type": "link",
                "target_id": "link_rising",
                "latency_ms": lat,
                "loss_pct": 0.0,
                "status": "up",
            }
        )
    assert tracker.get_trend("link_rising")["latency_trend"] == "rising"

    # Falling trend: 40, 38, 35 -> 15, 12, 10
    for lat in [40.0, 38.0, 35.0, 15.0, 12.0, 10.0]:
        tracker.add_measurement(
            {
                "timestamp": "2026-11-18T12:00:00Z",
                "target_type": "link",
                "target_id": "link_falling",
                "latency_ms": lat,
                "loss_pct": 0.0,
                "status": "up",
            }
        )
    assert tracker.get_trend("link_falling")["latency_trend"] == "falling"

    # Stable trend: 15.1, 14.9, 15.0, 15.2, 14.8
    for lat in [15.1, 14.9, 15.0, 15.2, 14.8]:
        tracker.add_measurement(
            {
                "timestamp": "2026-11-18T12:00:00Z",
                "target_type": "link",
                "target_id": "link_stable",
                "latency_ms": lat,
                "loss_pct": 0.0,
                "status": "up",
            }
        )
    assert tracker.get_trend("link_stable")["latency_trend"] == "stable"


# ============================================================================
# 3. Acceptance Criteria & NetworkMonitor Integration Tests
# ============================================================================


def test_acceptance_link_pushed_over_latency_threshold_appears_as_breaching_with_trend():
    """Acceptance criterion: a link pushed over its latency threshold appears as breaching,

    with its recent trend visible.
    """
    sim = Simulator(seed=42)
    monitor = NetworkMonitor(window_size=10)

    # 1. Warm up with 3 healthy ticks (core_1-dist_1 baseline is ~15ms)
    for _ in range(3):
        monitor.record_measurements(sim.tick())

    status_before = monitor.get_target_status("core_1-dist_1")
    assert status_before is not None
    assert status_before["is_breaching"] is False
    assert status_before["health"] == "HEALTHY"
    assert status_before["breaches"] == []

    # 2. Push link over its latency threshold (~75ms vs 60ms critical threshold)
    sim.inject_fault("congestion", ("core_1", "dist_1"), duration=3)
    monitor.record_measurements(sim.tick())

    # 3. Verify link appears as breaching with recent trend visible
    status_breaching = monitor.get_target_status("core_1-dist_1")
    assert status_breaching is not None
    assert status_breaching["is_breaching"] is True
    assert status_breaching["health"] == "CRITICAL"
    assert status_breaching["current_latency_ms"] > 60.0

    # Verify breach record exists
    latency_breach = next(
        (b for b in status_breaching["breaches"] if b["metric"] == "latency"), None
    )
    assert latency_breach is not None
    assert latency_breach["severity"] == "CRITICAL"
    assert latency_breach["threshold_value"] == 60.0
    assert latency_breach["current_value"] == pytest.approx(
        status_breaching["current_latency_ms"]
    )

    # Verify recent trend is visible
    assert status_breaching["latency_trend"] == "rising"
    assert len(status_breaching["recent_history"]) == 4
    assert status_breaching["rolling_avg_latency_ms"] > 20.0
    assert status_breaching["rolling_max_latency_ms"] == status_breaching["current_latency_ms"]

    # Verify link appears in breaching targets list
    breaching_list = monitor.get_breaching_targets()
    breaching_ids = [b["target_id"] for b in breaching_list]
    assert "core_1-dist_1" in breaching_ids

    # Verify network summary reflects critical breach
    net_status = monitor.get_network_status()
    assert net_status["overall_health"] == "CRITICAL"
    assert "core_1-dist_1" in net_status["breaching_targets"]
    assert net_status["critical_count"] >= 1


def test_network_monitor_healthy_network_status():
    """Verify healthy network reports HEALTHY overall with 0 breaches."""
    sim = Simulator(seed=42)
    monitor = NetworkMonitor()

    monitor.record_measurements(sim.tick())
    status = monitor.get_network_status()

    assert status["overall_health"] == "HEALTHY"
    assert status["total_targets"] == 59
    assert status["healthy_count"] == 59
    assert status["warning_count"] == 0
    assert status["critical_count"] == 0
    assert status["breaching_targets"] == []
    assert len(monitor.get_breaching_targets()) == 0


def test_network_monitor_node_down_fault_breaches():
    """Verify node_down fault results in node and attached link breaches."""
    sim = Simulator(seed=42)
    monitor = NetworkMonitor()

    sim.inject_fault("node_down", "dist_1", duration=2)
    monitor.record_measurements(sim.tick())

    node_status = monitor.get_target_status("dist_1")
    assert node_status["is_breaching"] is True
    assert node_status["health"] == "CRITICAL"
    assert node_status["status"] == "down"

    # Attached link core_1-dist_1 is also down
    link_status = monitor.get_target_status("core_1-dist_1")
    assert link_status["is_breaching"] is True
    assert link_status["health"] == "CRITICAL"
    assert link_status["status"] == "down"


def test_network_monitor_recovery_after_fault():
    """Verify target recovers to HEALTHY when fault expires."""
    sim = Simulator(seed=42)
    monitor = NetworkMonitor(window_size=10)

    sim.inject_fault("congestion", ("core_1", "dist_1"), duration=1)
    monitor.record_measurements(sim.tick())
    assert monitor.get_target_status("core_1-dist_1")["is_breaching"] is True

    # Next tick fault is cleared
    monitor.record_measurements(sim.tick())
    status_recovered = monitor.get_target_status("core_1-dist_1")
    assert status_recovered["is_breaching"] is False
    assert status_recovered["health"] == "HEALTHY"


def test_network_monitor_load_from_db(temp_db: Path):
    """Verify NetworkMonitor.from_db and load_from_db populate state and trends from SQLite."""
    sim = Simulator(seed=42)
    collector = Collector(simulator=sim, poll_interval=1.0, db_path=temp_db)

    # Collect 3 ticks in DB
    collector.collect_once()
    collector.collect_once()

    # Inject fault on 3rd tick
    sim.inject_fault("congestion", ("core_1", "dist_1"), duration=2)
    collector.collect_once()

    # Load into NetworkMonitor from database only
    monitor = NetworkMonitor.from_db(db_path=temp_db, window_size=10)

    # Verify target status and breaches loaded correctly
    status = monitor.get_target_status("core_1-dist_1")
    assert status is not None
    assert status["is_breaching"] is True
    assert status["health"] == "CRITICAL"
    assert status["current_latency_ms"] > 60.0
    assert len(status["recent_history"]) == 3
    assert status["latency_trend"] == "rising"

    # Verify overall network status
    net_status = monitor.get_network_status()
    assert net_status["overall_health"] == "CRITICAL"
    assert "core_1-dist_1" in net_status["breaching_targets"]


def test_network_monitor_reset():
    """Verify reset() clears all target states, active breaches, and rolling trends."""
    sim = Simulator(seed=42)
    monitor = NetworkMonitor()

    monitor.record_measurements(sim.tick())
    assert len(monitor.get_network_status()["targets"]) > 0

    monitor.reset()
    assert len(monitor.get_network_status()["targets"]) == 0
    assert monitor.get_target_status("core_1") is None
    assert monitor.get_all_breaches() == []
